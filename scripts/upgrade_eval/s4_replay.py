"""S4 재생 실험 — 막힌 claim 다시 쓰기: 지금 방식(R0) vs 고칠 문장만(R4 = S4 지시 + 범위 가드).

운영 card-cache 에서 다시 쓰기를 거치고도 막힌 사실층 카드(v3.4 시절 46장)를 그대로 가져와, 그 카드를 '이전 초안',
막힌 claim 을 '실패 claim' 으로 삼아 두 방식으로 한 번씩 다시 쓰게 한다. DDB 는 읽기만 한다.
- R0 지시 = main 40f9838 의 `_build_revise_prompt` 사본(아래 old_revise_prompt) — S4 브랜치에선 함수가 바뀌어 여기 얼려 둔다.
- R4 지시 = 지금 브랜치의 `author._build_revise_prompt`, 결과는 `gate.revise_within_targets` 가드를 거친다
  (범위 밖을 바꾸면 버리고 이전 카드를 그대로 ⚠ — 운영 gate 와 같은 규칙).
- 요약 AI = Sonnet 5.5 medium · CLI 2.1.301(Stage A 의 A2, U8 ② 운영 예정 구성), 검증 = Luna(숫자 claim 은 코드 검사만 —
  실험 도구에 codex 2차 판정 없음, 두 방식 같은 조건).
- 막힌 claim 은 대부분 F2 이전 숫자 검사 오탐이었다 — 이 실험은 '실패 표시를 받았을 때 어떻게 고치나'를 본다(맞는 사실을
  지우지 않고 다시 쓰는가, 다른 문장을 건드리지 않는가).

실행: PYTHONPATH=scripts uv run python -m upgrade_eval.s4_replay run [--limit N] · summary
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import date

from briefing.core.authoring.author import (
    DraftCard, _build_revise_prompt, _parse_card_json, _to_draft_card, _tokens, build_system_prompt,
    revise_targets, summary_sentences,
)
from briefing.core.gate import reroute_claim_types, revise_within_targets
from briefing.core.lenses import resolve_lens
from briefing.core.pipeline import _FACT_USER
from briefing.core.stores.cache import _deserialize
from briefing.core.verification import numeric

from .author_runner import ARMS, EVAL_TODAY, run_author
from .codex_runner import VERIFIERS
from .common import EXP_ROOT, append_jsonl, done_keys, read_jsonl
from .stage_a import make_verify_fn

RECORDS = EXP_ROOT / "runs" / "s4" / "records.jsonl"
ARM = ARMS["A2"]
METHODS = ("R0", "R4")
_MODIFIED_OVERLAP = 0.5   # 고칠 문장과 낱말이 이만큼 겹치는 새 문장이 있으면 '고침', 없으면 '지움'
_EN_NAME = re.compile(r"(?<![A-Za-z0-9])[A-Z][A-Za-z0-9.\-]*[A-Za-z0-9]")


def old_revise_prompt(source, prior: DraftCard, failed_ids: tuple[str, ...], *, today: str | None = None) -> str:
    """R0 — S4 이전 운영 다시 쓰기 지시(main 40f9838 `_build_revise_prompt`) 그대로. 이전 요약을 보여 주지 않는다."""
    failed = set(failed_ids)
    prior_lines = "\n".join(
        f'- {c.id} [{"재도출 필요" if c.id in failed else "유지"}]: {c.text}' for c in prior.claims
    )
    today = today or date.today().isoformat()
    return (
        f"오늘 날짜: {today} (원문에 없는 날짜 생성 금지).\n\n"
        "이전 초안의 일부 claim 이 독립 검증에 실패했다. **실패로 표시된 claim 만** 원문에서 다시 도출하고 "
        "'유지' claim 은 그대로 둬라(왜 실패인지는 주어지지 않는다 — 원문만 다시 보라).\n\n"
        f"이전 claims:\n{prior_lines}\n\n"
        f"동일 JSON 형식으로 전체 카드를 다시 출력하라. 동결 원문:\n\n{source.text}"
    )


def _norm(s: str) -> str:
    return " ".join(s.split())


def _nums(text: str) -> set[float]:
    n = numeric.scan(text or "")
    return set(n.values) | set(n.percents)


def scope_metrics(prior: DraftCard, revised: DraftCard, failed_ids: tuple[str, ...]) -> dict:
    """다시 쓴 카드가 고칠 문장 밖을 건드렸나(두 방식 같은 자로) — 가드 통과 여부, 대상 아닌 문장 보존률,
    고칠 문장의 처리(그대로·고침·지움), 이전 요약에 없던 숫자·영문 이름, why 변경."""
    targets = set(revise_targets(prior, failed_ids))
    before = [_norm(s) for s in summary_sentences(prior.summary)]
    after = [_norm(s) for s in summary_sentences(revised.summary)]
    rest = [s for i, s in enumerate(before) if i not in targets]
    outcomes = []
    for i in sorted(targets):
        t = before[i]
        if t in after:
            outcomes.append("unchanged")
            continue
        want = _tokens(t)
        best = max((len(want & _tokens(a)) / len(want) for a in after), default=0.0) if want else 0.0
        outcomes.append("modified" if best >= _MODIFIED_OVERLAP else "deleted")
    prior_nums = _nums(prior.summary)
    prior_names = set(_EN_NAME.findall(prior.summary))
    return {
        "in_scope": revise_within_targets(prior, revised, failed_ids),
        "kept_rate": (sum(s in after for s in rest) / len(rest)) if rest else None,
        "targets": outcomes,
        "new_numbers": sorted(v for v in _nums(revised.summary) if not numeric.contains(v, prior_nums)),
        "new_names": sorted({n for n in _EN_NAME.findall(revised.summary) if n not in prior_names}),
        "why_changed": _norm(revised.why_it_matters) != _norm(prior.why_it_matters),
        "sentences": (len(before), len(after)),
        "claims": (len(prior.claims), len(revised.claims)),
    }


def load_cases(table) -> list[dict]:
    """card-cache → 다시 쓰기를 거치고도 막힌 사실층 카드(QUARANTINE · attempts ≥ 2 · BLOCKED 있음)."""
    out, start = [], None
    while True:
        kw = {"ProjectionExpression": "cache_key, card_json"}
        if start:
            kw["ExclusiveStartKey"] = start
        resp = table.scan(**kw)
        for it in resp["Items"]:
            g = _deserialize(json.loads(it["card_json"]))
            failed = tuple(v.claim_id for v in g.verdicts if v.verdict == "BLOCKED")
            if not g.card.based_on and g.decision == "QUARANTINE" and g.attempts >= 2 and failed:
                out.append({"cache_key": it["cache_key"], "prior": g.card, "failed_ids": failed})
        start = resp.get("LastEvaluatedKey")
        if not start:
            return sorted(out, key=lambda c: c["cache_key"])


def run_case(case: dict, method: str, *, store, verify, runner=run_author) -> dict:
    """한 카드 × 한 방식 → 기록. R4 는 가드를 통과해야 검증하고, 못 하면 이전 카드를 ⚠ 로 둔다(운영 gate 와 같다)."""
    prior, failed = case["prior"], case["failed_ids"]
    source = store.get_source(prior.source_id)
    system = build_system_prompt(lens_guidance=resolve_lens(_FACT_USER.lens).guidance, skill_md=_FACT_USER.skill_md)
    build = old_revise_prompt if method == "R0" else _build_revise_prompt
    rec = {"cache_key": case["cache_key"], "source_id": prior.source_id, "method": method, "failed_ids": list(failed)}
    run = runner(system, build(source, prior, failed, today=EVAL_TODAY), ARM, timeout_s=600)
    rec.update(duration_ms=run.duration_ms, cost_usd=run.cost_usd, error=run.error)
    if run.error:
        return rec | {"decision": "ERROR"}
    try:
        revised = reroute_claim_types(_to_draft_card(prior.source_id, prior.headline, _parse_card_json(run.text)))
    except ValueError as exc:
        return rec | {"decision": "ERROR", "error": f"카드 형식: {exc}"}
    rec.update(scope_metrics(prior, revised, failed), summary=revised.summary, prior_summary=prior.summary)
    if method == "R4" and not rec["in_scope"]:
        return rec | {"decision": "QUARANTINE", "guard_rejected": True, "verdicts": []}
    verdicts = verify(revised)
    blocked = sum(v.verdict == "BLOCKED" for v in verdicts)
    return rec | {"decision": "QUARANTINE" if blocked else "PUBLISH", "guard_rejected": False,
                  "verdicts": [asdict(v) for v in verdicts]}


def run_all(*, limit: int | None = None, concurrency: int = 4) -> None:
    import boto3

    from briefing.core.config import load_settings
    from briefing.core.stores.dynamo import DynamoSourceStore

    st = load_settings()
    cases = load_cases(boto3.resource("dynamodb", region_name=st.region).Table(st.cache_table))[:limit]
    store = DynamoSourceStore(st.source_table, region=st.region)
    done = done_keys(RECORDS, ("cache_key", "method"), where=lambda r: r.get("decision") != "ERROR")
    tasks = [(c, m) for c in cases for m in METHODS if (c["cache_key"], m) not in done]   # 카드마다 두 방식을 이어서
    print(f"s4_replay: cases {len(cases)}, tasks {len(tasks)}, skipped {len(done)}", flush=True)
    lock = threading.Lock()

    def work(t):
        case, method = t
        log: list[dict] = []
        rec = run_case(case, method, store=store, verify=make_verify_fn(VERIFIERS["gpt-6-luna"], store, log))
        rec["codex_calls"] = len(log)
        with lock:
            append_jsonl(RECORDS, rec)

    t0 = time.monotonic()
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        list(pool.map(work, tasks))
    print(f"done in {int(time.monotonic() - t0)}s", flush=True)


def summarize(records: list[dict]) -> str:
    """방식별 표 — 같은 카드에 두 방식이 모두 끝난 것만 센다(짝 비교)."""
    by = {}
    for r in records:
        by[(r["cache_key"], r["method"])] = r                     # 마지막 기록
    keys = {k for k, m in by if all((k, mm) in by and by[(k, mm)]["decision"] != "ERROR" for mm in METHODS)}
    rows = []
    for m in METHODS:
        rs = [by[(k, m)] for k in sorted(keys)]
        tg = [o for r in rs for o in r["targets"]]
        kept = [r["kept_rate"] for r in rs if r["kept_rate"] is not None]
        lat = sorted(r["duration_ms"] / 1000 for r in rs)
        rows.append((m, len(rs), sum(r["in_scope"] for r in rs), statistics.mean(kept) if kept else 0.0,
                     tg.count("modified"), tg.count("unchanged"), tg.count("deleted"),
                     sum(bool(r["new_numbers"] or r["new_names"]) for r in rs), sum(r["why_changed"] for r in rs),
                     sum(r["decision"] == "PUBLISH" for r in rs), sum(r.get("guard_rejected", False) for r in rs),
                     statistics.median(lat) if lat else 0, lat[int(0.95 * (len(lat) - 1))] if lat else 0,
                     sum((r["cost_usd"] or 0) for r in rs)))
    head = ("| 방식 | 카드 | 범위 안(가드 통과) | 대상 아닌 문장 보존 | 고칠 문장: 고침 / 그대로 / 지움 | 새 숫자·이름 생긴 카드 "
            "| why 바뀐 카드 | 발행 | 가드 거부 | 시간 p50 / p95 | 요약 비용 |")
    out = [head, "|" + "---|" * 11]
    for m, n, ins, kr, mo, un, de, nw, wy, pub, gr, p50, p95, cost in rows:
        out.append(f"| {m} | {n} | {ins} ({ins / n:.0%}) | {kr:.0%} | {mo} / {un} / {de} | {nw} | {wy} | "
                   f"{pub} ({pub / n:.0%}) | {gr} | {p50:.0f}초 / {p95:.0f}초 | ${cost:.2f} |" if n else f"| {m} | 0 |")
    errors = sum(r["decision"] == "ERROR" for r in by.values())
    return "\n".join(out) + f"\n\n짝이 맞은 카드 {len(keys)}장 · 오류 기록 {errors}건\n"


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="s4_replay")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--limit", type=int)
    r.add_argument("--concurrency", type=int, default=4)
    sub.add_parser("summary")
    args = ap.parse_args(argv)
    if args.cmd == "run":
        run_all(limit=args.limit, concurrency=args.concurrency)
    print(summarize(read_jsonl(RECORDS)))


if __name__ == "__main__":
    main()
