"""채점 실행(설계 §8) — 판정자 검증 → 핵심 사실 목록 → 채점 → 가림 → 사람 확인 내보내기 → 참고 비교.

원시 판정은 judge/scores.jsonl({arm, source_id, rep, judge, kind, result, error}), 최종 판정은
judge/final.jsonl({arm, source_id, rep, covered, first_sentence_new, fidelity, bypass})에 쓴다(레저 결정).
판정자 둘이 같으면 그 값, 다르면 제3계열 판정으로 가린다. 확인 목록 우회(bypass)는 자유 서술이라 주 판정자 값을 쓴다.

실행: PYTHONPATH=scripts uv run python -m upgrade_eval.judging <gate|keyfacts|export-human-1|score|tiebreak|export-human-2|pairwise>
"""
from __future__ import annotations

import argparse
import json
import random
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict

from briefing.core.stores.source_store import SourceStore

from . import judge as J
from .common import EXP_ROOT, SEED, append_jsonl, done_keys, read_jsonl
from .metrics import split_sentences
from .select_articles import load_manifest

JUDGE_DIR = EXP_ROOT / "judge"
RESULTS = EXP_ROOT / "results"
STAGE_A = EXP_ROOT / "runs" / "stage_a" / "records.jsonl"
SCORES = JUDGE_DIR / "scores.jsonl"
FINAL = JUDGE_DIR / "final.jsonl"
_LOCK = threading.Lock()


# ── 순수 함수(테스트 대상) ──
def scoring_targets(records: list[dict]) -> list[dict]:
    """발행된 실행만 품질 채점 — 보류·오류는 발행 실패율로 따로 센다."""
    return [r for r in records if r.get("decision") == "PUBLISH"]


def median_length_rep(records: list[dict]) -> dict:
    """같은 조건·기사의 PUBLISH 반복 중 요약 길이가 중간인 것(짝수면 아래 중간, 동률이면 낮은 rep)."""
    pub = sorted(scoring_targets(records), key=lambda r: (len(r["summary"]), r["rep"]))
    return pub[(len(pub) - 1) // 2]


def fidelity_disagreements(a: dict[int, list[str]], b: dict[int, list[str]]) -> list[int]:
    return sorted(i for i in set(a) | set(b) if set(a.get(i, [])) != set(b.get(i, [])))


def align_disagreements(a: dict[str, bool], b: dict[str, bool]) -> list[str]:
    return sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))


def merge_final(main: dict, cross: dict, tie: dict | None) -> dict:
    """둘이 같으면 그 값, 다르면 가림 판정자의 값(없으면 주 판정자). bypass 는 주 판정자."""
    covered = {}
    for k in main["covered"]:
        same = main["covered"][k] == cross["covered"].get(k)
        covered[k] = main["covered"][k] if same or not tie else tie["covered"].get(k, main["covered"][k])
    first_same = main["first_sentence_new"] == cross["first_sentence_new"]
    first = main["first_sentence_new"] if first_same or not tie else tie["first_sentence_new"]
    fidelity = {}
    for i in set(main["fidelity"]) | set(cross["fidelity"]):
        a, b = main["fidelity"].get(i, []), cross["fidelity"].get(i, [])
        labels = a if set(a) == set(b) or not tie else tie["fidelity"].get(i, [])
        if labels:
            fidelity[i] = labels
    return {"covered": covered, "first_sentence_new": first, "fidelity": fidelity, "bypass": list(main.get("bypass", []))}


def is_infra_error(row: dict) -> bool:
    """호출 자체가 실패한 기록(쓰로틀·네트워크·읽기 시간 초과) — 판정자 실패가 아니므로 다시 돌린다."""
    return str(row.get("error") or "").startswith("호출 실패")


def done_ok(path, fields: tuple[str, ...]) -> set[tuple]:
    """'끝남' 키 — 호출 실패 기록은 빼서 다음 실행에서 다시 돈다(Stage A·B 의 인프라 오류 규칙과 같다)."""
    return done_keys(path, fields, where=lambda r: not is_infra_error(r))


_GATE_FACT_ID = "F1"


def gate_fact(item: J.PlantedSummary) -> J.KeyFact:
    """'뒤쪽 사실 삭제' 검사용 핵심 사실. 판정자가 id 를 JSON 키로 되받아 적으므로 짧은 id 를 쓴다
    (66–109자 문장을 키로 쓰면 글자 하나만 달라도 스키마 위반 → 놓침으로 세어졌다)."""
    return J.KeyFact(_GATE_FACT_ID, item.removed_fact, "", None, None, "새 사실", False)


def gate_uncovered(result: dict | None, item: J.PlantedSummary) -> set[str]:
    """align 결과 → 빠졌다고 본 사실. score_gate 는 removed_fact 문장으로 대조한다."""
    return {item.removed_fact} if (result or {}).get("covered", {}).get(_GATE_FACT_ID) is False else set()


# ── 입출력 도우미 ──
def _sources() -> SourceStore:
    return SourceStore(str(EXP_ROOT / "sources"))


def _keyfacts() -> dict[str, list[J.KeyFact]]:
    out = {}
    for r in read_jsonl(JUDGE_DIR / "keyfacts.jsonl"):
        out[r["source_id"]] = [J.KeyFact(**f) for f in r["facts"]]
    return out


def _judges() -> dict:
    return json.loads((RESULTS / "judges.json").read_text(encoding="utf-8"))


def _model(name: str) -> str:
    return {**J.JUDGES, **J.THIRD}[name]


def _write(path, rec: dict) -> None:
    with _LOCK:
        append_jsonl(path, rec)


def _fidelity_ints(d: dict) -> dict[int, list[str]]:
    return {int(k): v for k, v in d.items()}


def _judge_summary(name: str, source_text: str, summary: str, facts: list[J.KeyFact], claims: list[str], kinds: tuple) -> dict:
    """한 요약을 판정자 하나로 — align/fidelity/bypass 중 요청한 것만."""
    sents = split_sentences(summary)
    out = {}
    if "align" in kinds:
        ids = [f.id for f in facts]
        call = J.converse_json(_model(name), *J.align_messages(source_text, facts, sents),
                               validate=lambda o: J.parse_align(o, ids, len(sents)))
        out["align"] = (call, J.parse_align(call.obj, ids, len(sents)) if call.obj else None)
    if "fidelity" in kinds:
        call = J.converse_json(_model(name), *J.fidelity_messages(source_text, sents),
                               validate=lambda o: J.parse_fidelity(o, len(sents)))
        out["fidelity"] = (call, J.parse_fidelity(call.obj, len(sents)) if call.obj else None)
    if "bypass" in kinds:
        call = J.converse_json(_model(name), *J.bypass_messages(sents, claims), validate=J.parse_bypass)
        out["bypass"] = (call, J.parse_bypass(call.obj) if call.obj else None)
    return out


def _result_json(kind: str, parsed) -> object:
    if parsed is None:
        return None
    if kind == "align":
        covered, first = parsed
        return {"covered": covered, "first_sentence_new": first}
    return parsed


# ── 하위 명령 ──
def cmd_gate(judges: list[str], score_only: bool) -> None:
    items = [J.PlantedSummary(**r) for r in read_jsonl(JUDGE_DIR / "planted_summaries.jsonl")]
    store = _sources()
    raw = JUDGE_DIR / "gate_raw.jsonl"
    if not score_only:
        done = done_ok(raw, ("judge", "item_id", "kind"))
        tasks = [(j, it, k) for j in judges for it in items
                 for k in (("fidelity", "align") if it.defect == "뒤쪽 사실 삭제" else ("fidelity",)) if (j, it.item_id, k) not in done]

        def work(t):
            j, it, kind = t
            src = store.get_source(it.source_id).text
            facts = [gate_fact(it)] if kind == "align" else []
            call, parsed = _judge_summary(j, src, it.summary, facts, [], (kind,))[kind]
            _write(raw, {"judge": j, "item_id": it.item_id, "kind": kind, "result": _result_json(kind, parsed),
                         "error": call.error, "usage": call.usage})

        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(work, tasks))
    rows = read_jsonl(raw)
    ok_path = JUDGE_DIR / "adjudicated_ok.json"
    adjudicated = {tuple(x) for x in json.loads(ok_path.read_text(encoding="utf-8"))} if ok_path.exists() else set()
    gates, to_check = {}, []
    for j in judges:
        mine = [r for r in rows if r["judge"] == j]
        flags = {r["item_id"]: _fidelity_ints(r["result"] or {}) for r in mine if r["kind"] == "fidelity"}
        by_id = {it.item_id: it for it in items}
        uncovered = {r["item_id"]: gate_uncovered(r["result"], by_id[r["item_id"]]) for r in mine if r["kind"] == "align"}
        gates[j] = J.score_gate(flags, uncovered, items, adjudicated_ok=adjudicated)
        for it in items:
            for idx, labels in flags.get(it.item_id, {}).items():
                if labels and not (it.defect and idx == it.sentence_idx):
                    to_check.append(f"- [{j}] {it.item_id} 문장 {idx}: {labels} — {split_sentences(it.summary)[idx][:100]}")
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "judge_gates.json").write_text(json.dumps({j: asdict(g) for j, g in gates.items()}, ensure_ascii=False, indent=2),
                                              encoding="utf-8")
    (RESULTS / "gate_flags_to_adjudicate.md").write_text("# 결함 없는 문장에 대한 지적 — 원문 확인 필요\n\n" + "\n".join(sorted(set(to_check))) + "\n",
                                                         encoding="utf-8")
    winner = json.loads((RESULTS / "stage_b_scores.json").read_text(encoding="utf-8"))["winner"]
    third = sorted([j for j in judges if j in J.THIRD], key=lambda j: (not gates[j].passed, -gates[j].detection, gates[j].false_flag_rate))
    try:
        main, cross, tie = J.select_judges(winner, gates, third)
        (RESULTS / "judges.json").write_text(json.dumps({"main": main, "cross": cross, "tiebreak": tie, "stage_b_winner": winner},
                                                        ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"gates": {j: asdict(g) for j, g in gates.items()}, "selected": [main, cross, tie]}, ensure_ascii=False))
    except J.GateStop as exc:
        print(f"GateStop: {exc} — 채점을 시작하지 말고 사용자에게 보고")
        raise SystemExit(2)


def cmd_keyfacts() -> None:
    sel = _judges()
    store = _sources()
    kf_path, review_path = JUDGE_DIR / "keyfacts.jsonl", JUDGE_DIR / "keyfacts_review.jsonl"
    have = {r["source_id"] for r in read_jsonl(kf_path) if not is_infra_error(r)}
    for a in load_manifest():
        sid = a["source_id"]
        if sid in have:
            continue
        text = store.get_source(sid).text
        call = J.converse_json(_model(sel["main"]), *J.keyfacts_messages(text), validate=lambda o, t=text: J.parse_keyfacts(o, t))
        if not call.obj:
            _write(kf_path, {"source_id": sid, "facts": [], "judge": sel["main"], "error": call.error})
            continue
        facts = J.parse_keyfacts(call.obj, text)
        _write(kf_path, {"source_id": sid, "facts": [asdict(f) for f in facts], "judge": sel["main"], "error": None})
        rv = J.converse_json(_model(sel["cross"]), *J.review_messages(text, facts))
        _write(review_path, {"source_id": sid, "review": rv.obj, "judge": sel["cross"], "error": rv.error})


def cmd_export_human_1() -> None:
    review = {r["source_id"]: r.get("review") for r in read_jsonl(JUDGE_DIR / "keyfacts_review.jsonl")}
    kf = {r["source_id"]: r for r in read_jsonl(JUDGE_DIR / "keyfacts.jsonl")}
    lines = ["# 사람 확인 1 — 핵심 사실 목록(약 10분)", "",
             "각 목록이 원문의 핵심을 빠짐없이·정확하게 담았는지 봐 주세요. 빠진 사실, 틀린 사실, 범주가 틀린 것을 알려 주시면 반영합니다.", ""]
    for a in load_manifest():
        if not a["human_check"]:
            continue
        r = kf.get(a["source_id"], {})
        lines += [f"## {a['kind']} — {a['title']}", f"- 원문: {a['url']}", ""]
        for f in r.get("facts", []):
            pos = f"{f['tercile']}" if f.get("tercile") else "위치 못 찾음"
            lines.append(f"- **{f['id']}** [{f['category']}{', AI' if f['ai_related'] else ''} · {pos}] {f['text']}")
        lines += ["", f"교차 판정자 검토: `{json.dumps(review.get(a['source_id']), ensure_ascii=False)}`", ""]
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "human_check_1.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(RESULTS / "human_check_1.md")


def cmd_score() -> None:
    sel = _judges()
    store = _sources()
    facts_by = _keyfacts()
    targets = scoring_targets(read_jsonl(STAGE_A))
    done = done_ok(SCORES, ("arm", "source_id", "rep", "judge", "kind"))
    tasks = [(r, j, k) for r in targets for j in (sel["main"], sel["cross"]) for k in ("align", "fidelity", "bypass")
             if (r["arm"], r["source_id"], r["rep"], j, k) not in done]
    random.Random(SEED).shuffle(tasks)
    print(f"score: {len(tasks)} calls (skipped {len(done)})", flush=True)

    def work(t):
        r, j, kind = t
        claims = [c["text"] for c in r["claims"]]
        call, parsed = _judge_summary(j, store.get_source(r["source_id"]).text, r["summary"], facts_by.get(r["source_id"], []),
                                      claims, (kind,))[kind]
        _write(SCORES, {"arm": r["arm"], "source_id": r["source_id"], "rep": r["rep"], "judge": j, "kind": kind,
                        "result": _result_json(kind, parsed), "error": call.error, "usage": call.usage})

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(work, tasks))


def _by_target(rows: list[dict]) -> dict[tuple, dict]:
    out: dict[tuple, dict] = {}
    for r in rows:
        if r["result"] is None:
            continue
        out.setdefault((r["arm"], r["source_id"], r["rep"]), {}).setdefault(r["judge"], {})[r["kind"]] = r["result"]
    return out


def _view(d: dict) -> dict | None:
    if not all(k in d for k in ("align", "fidelity")):
        return None
    return {"covered": d["align"]["covered"], "first_sentence_new": d["align"]["first_sentence_new"],
            "fidelity": _fidelity_ints(d["fidelity"]), "bypass": d.get("bypass", [])}


def _disputed(main: dict, cross: dict) -> tuple[list[int], list[str], bool]:
    return (fidelity_disagreements(main["fidelity"], cross["fidelity"]), align_disagreements(main["covered"], cross["covered"]),
            main["first_sentence_new"] != cross["first_sentence_new"])


def tiebreak_targets(grouped: dict, sel: dict, done: set) -> list[tuple]:
    """주·교차가 갈린 카드 중 가림 판정(align·fidelity)이 아직 없는 것. 한쪽 판정이 없으면 판정 누락이라 가리지 않는다."""
    out = []
    for key, by_judge in sorted(grouped.items()):
        main, cross = _view(by_judge.get(sel["main"], {})), _view(by_judge.get(sel["cross"], {}))
        if not main or not cross or not any(_disputed(main, cross)):
            continue
        if not all((*key, sel["tiebreak"], k) in done for k in ("align", "fidelity")):
            out.append(key)
    return out


def cmd_tiebreak() -> None:
    sel = _judges()
    store = _sources()
    facts_by = _keyfacts()
    records = {(r["arm"], r["source_id"], r["rep"]): r for r in scoring_targets(read_jsonl(STAGE_A))}
    grouped = _by_target(read_jsonl(SCORES))
    pending = tiebreak_targets(grouped, sel, done_ok(SCORES, ("arm", "source_id", "rep", "judge", "kind")))
    print(f"tiebreak: {len(pending)} cards to judge with {sel['tiebreak']}", flush=True)

    def work(key):
        res = _judge_summary(sel["tiebreak"], store.get_source(key[1]).text, records[key]["summary"], facts_by.get(key[1], []),
                             [], ("align", "fidelity"))
        for kind, (call, parsed) in res.items():
            _write(SCORES, {"arm": key[0], "source_id": key[1], "rep": key[2], "judge": sel["tiebreak"], "kind": kind,
                            "result": _result_json(kind, parsed), "error": call.error, "usage": call.usage})

    with ThreadPoolExecutor(max_workers=6) as pool:              # 가림 판정자(Kimi)는 호출당 ≈60–100초 — 순차면 몇 시간
        list(pool.map(work, pending))
    ties = _by_target(read_jsonl(SCORES))
    disputes, finals = [], []
    for key, by_judge in sorted(grouped.items()):
        main, cross = _view(by_judge.get(sel["main"], {})), _view(by_judge.get(sel["cross"], {}))
        if not main or not cross:
            continue                                             # 판정 실패 — 집계에서 빼고 개수만 보고
        fid, cov, first_diff = _disputed(main, cross)
        tie = None
        if fid or cov or first_diff:
            tie = _view(ties.get(key, {}).get(sel["tiebreak"], {}))
            disputes.append({"key": list(key), "fidelity_idx": fid, "facts": cov, "first": first_diff})
        final = merge_final(main, cross, tie)
        finals.append({"arm": key[0], "source_id": key[1], "rep": key[2], **final})
    FINAL.write_text("".join(json.dumps(f, ensure_ascii=False) + "\n" for f in finals), encoding="utf-8")
    (JUDGE_DIR / "disputes.json").write_text(json.dumps(disputes, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"final {len(finals)}, disputes {len(disputes)}")


def cmd_export_human_2(n: int) -> None:
    disputes = json.loads((JUDGE_DIR / "disputes.json").read_text(encoding="utf-8"))
    records = {(r["arm"], r["source_id"], r["rep"]): r for r in read_jsonl(STAGE_A)}
    grouped = _by_target(read_jsonl(SCORES))
    sel = _judges()
    pick = random.Random(SEED).sample(disputes, min(n, len(disputes)))
    lines = ["# 사람 확인 2 — 판정자끼리 갈린 항목(약 10분)", "",
             "각 항목에서 어느 판정이 원문에 맞는지 골라 주세요(주 / 교차 / 가림 / 모두 틀림).", ""]
    for i, d in enumerate(pick, 1):
        key = tuple(d["key"])
        r, by = records[key], grouped.get(key, {})
        sents = split_sentences(r["summary"])
        lines += [f"## {i}. {key[0]} · {key[1][:10]} · rep{key[2]}", f"- 요약: {r['summary']}"]
        for idx in d["fidelity_idx"]:
            labels = {name: _fidelity_ints(by.get(sel[role], {}).get("fidelity", {})).get(idx, [])
                      for role, name in (("main", "주"), ("cross", "교차"), ("tiebreak", "가림"))}
            lines.append(f"- 문장 {idx} 「{sents[idx] if idx < len(sents) else '?'}」 → {labels}")
        for fid in d["facts"]:
            vals = {name: by.get(sel[role], {}).get("align", {}).get("covered", {}).get(fid)
                    for role, name in (("main", "주"), ("cross", "교차"), ("tiebreak", "가림"))}
            lines.append(f"- 핵심 사실 {fid} 포함 여부 → {vals}")
        if d["first"]:
            lines.append("- 첫 문장이 새 사실인가에 대한 판정이 갈림")
        lines.append("")
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "human_check_2.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(RESULTS / "human_check_2.md")


def cmd_pairwise() -> None:
    sel = _judges()
    store = _sources()
    recs = read_jsonl(STAGE_A)
    out = JUDGE_DIR / "pairwise.jsonl"
    done = done_ok(out, ("arm", "source_id", "judge", "order"))
    groups: dict[tuple, list[dict]] = {}
    for r in recs:
        groups.setdefault((r["arm"], r["source_id"]), []).append(r)
    tasks = []
    for (arm, sid), rs in groups.items():
        if arm == "A0" or not scoring_targets(rs) or not scoring_targets(groups.get(("A0", sid), [])):
            continue
        cand, base = median_length_rep(rs), median_length_rep(groups[("A0", sid)])
        for j in (sel["main"], sel["cross"]):
            for order in ("arm_first", "a0_first"):
                if (arm, sid, j, order) not in done:
                    tasks.append((arm, sid, j, order, cand["summary"], base["summary"]))

    def work(t):
        arm, sid, j, order, cand, base = t
        first, second = (cand, base) if order == "arm_first" else (base, cand)
        call = J.converse_json(_model(j), *J.pairwise_messages(store.get_source(sid).text, first, second), validate=J.parse_pairwise)
        better = J.parse_pairwise(call.obj) if call.obj else None
        winner = None if better is None else ("tie" if better == "tie" else
                                              ("arm" if (better == "first") == (order == "arm_first") else "A0"))
        _write(out, {"arm": arm, "source_id": sid, "judge": j, "order": order, "winner": winner, "error": call.error,
                     "usage": call.usage})

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(work, tasks))


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="judging")
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("gate")
    g.add_argument("--judges", default="astra,sol61,grok,kimi,glm,nova")
    g.add_argument("--score-only", action="store_true")
    sub.add_parser("keyfacts")
    sub.add_parser("export-human-1")
    sub.add_parser("score")
    sub.add_parser("tiebreak")
    h2 = sub.add_parser("export-human-2")
    h2.add_argument("--n", type=int, default=10)
    sub.add_parser("pairwise")
    args = ap.parse_args(argv)
    {"gate": lambda: cmd_gate(args.judges.split(","), args.score_only), "keyfacts": cmd_keyfacts,
     "export-human-1": cmd_export_human_1, "score": cmd_score, "tiebreak": cmd_tiebreak,
     "export-human-2": lambda: cmd_export_human_2(args.n), "pairwise": cmd_pairwise}[args.cmd]()


if __name__ == "__main__":
    main()
