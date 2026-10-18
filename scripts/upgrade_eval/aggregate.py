"""집계와 결정(설계 §8-4) — Stage A 실행 기록·판정 결과·코드 지표 → 조건별 성적표, 탈락, 순위.

- 품질은 발행된(PUBLISH) 실행만 채점한다. 보류·오류·순차 실행의 360초 초과는 '발행 실패율'로 따로 센다.
- 알려진 F2(숫자 검사 오판) 표기로만 막힌 보류는 결정용 실패율에서 뺀다(원래 값도 함께 보고).
- 실행 1건의 지표는 rep_metrics 한 곳에서 만들고, 성적표(실행 평균)와 기사별 값(반복 평균)을 모두 거기서 파생한다.
- 결정: 기준선 A0 와 기사 단위로 짝지어 비교(짝 부트스트랩·'차이 없음', stats).
  안전(검증 우회·인용 불일치·발행 실패)이나 충실도가 나빠지면 탈락 → 남은 조건을 쌍마다
  충실도 → 커버리지 → 비용 → p95 순으로 겨루고(단계마다 '차이 없음'이면 다음 단계), 이긴 횟수로 순위를 매긴다.

실행: PYTHONPATH=scripts uv run python -m upgrade_eval.aggregate → results/scorecards.json, results/decision.json
"""
from __future__ import annotations

import json
import math
import statistics
import sys

from . import costs, metrics
from .common import EXP_ROOT, read_jsonl
from .judge import FIDELITY_LABELS, KeyFact
from .stage_a import is_infra_error
from .stats import no_difference, paired_bootstrap, rep_sd

RESULTS = EXP_ROOT / "results"
STAGE_A = EXP_ROOT / "runs" / "stage_a" / "records.jsonl"
JUDGE_DIR = EXP_ROOT / "judge"
FAILURE_MARGIN = 0.05            # 발행 실패율이 A0 + 5%p 이상이면 탈락(설계자 결정, 조정 가능)
DECISION_METRICS = ("bypass_rate", "quote_mismatch_rate", "fidelity", "coverage")
SAFETY = (("bypass_rate", "검증 우회"), ("quote_mismatch_rate", "인용 불일치"))
INFLATION = tuple(lab for lab in FIDELITY_LABELS if lab.startswith("부풀림"))
_JUDGED_KEYS = ("bypass_rate", "fidelity", "inflation", "oversoftening", "attribution", "opinion", "factual_error",
                "coverage", "coverage_per_sentence", "first_sentence_new", "ai_coverage")


# ── 실행 1건 ──
def _f2_only(run: dict) -> bool:
    """보류 사유가 알려진 F2 표기뿐인가 — BLOCKED 가 하나 이상이고 모두 F2(고치면 통과할 것)."""
    texts = {c.get("id"): c.get("text", "") for c in run.get("claims") or []}
    blocked = [v for v in run.get("verdicts") or [] if v.get("verdict") == "BLOCKED"]
    return bool(blocked) and all(metrics.is_known_f2_block(texts.get(v.get("claim_id"), ""), v.get("evidence", ""))
                                 for v in blocked)


def _failed(run: dict, *, f2_adjusted: bool) -> bool:
    slow = bool(run.get("sequential")) and bool(run.get("over_360"))     # 운영 360초 상한이면 시간 초과였을 실행
    if run.get("decision") == "PUBLISH":
        return slow
    if f2_adjusted and run.get("decision") == "QUARANTINE" and _f2_only(run):
        return slow
    return True


def rep_metrics(run: dict, judged: dict | None, facts: list[KeyFact], source) -> dict:
    """발행된 실행 1건의 지표. 판정 결과가 없으면 판정 지표는 None(평균에서 빠진다).
    문장 번호는 채점 때와 같은 metrics.split_sentences 기준(0부터)."""
    summary, why = run.get("summary") or "", run.get("why") or ""
    claims = [c.get("text", "") for c in run.get("claims") or []]
    sents = metrics.split_sentences(summary)
    n = len(sents) or 1
    text = source.text if source is not None else ""
    code_bypass = len(metrics.uncovered_numbers(summary, claims)) + len(metrics.uncovered_names(summary, claims))
    out = {
        "sentences": float(len(sents)),
        "long_sentence_ratio": metrics.long_sentence_ratio(sents),
        "hedge": float(metrics.has_hedge(summary)),
        "depth": metrics.deepest_position(text, summary) if text else None,
        "translit": float(bool(metrics.transliterated_names(summary))),
        "claims": float(len(claims)),
        "why_new_numbers": float(bool(metrics.why_new_numbers(why, summary, claims))),
        "title_repeat": float(metrics.repeats_title(source.title, sents[0])) if source is not None and sents else None,
        "quote_mismatch_rate": float(bool(metrics.quote_mismatches(summary, text))),
        "code_bypass_rate": code_bypass / n,
    }
    if judged is None:
        return out | dict.fromkeys(_JUDGED_KEYS)
    fid = {int(k): v for k, v in (judged.get("fidelity") or {}).items()}

    def share(pred) -> float:
        return sum(1 for i in range(len(sents)) if any(pred(lab) for lab in fid.get(i, []))) / n

    covered = judged.get("covered") or {}
    hit = [bool(covered.get(f.id)) for f in facts]
    ai = [bool(covered.get(f.id)) for f in facts if f.ai_related]
    return out | {
        "bypass_rate": (code_bypass + len(judged.get("bypass") or [])) / n,   # 문장당 검증 우회 항목(코드 숫자·이름 + 판정자)
        "fidelity": share(lambda lab: True),                                   # 결정용: 라벨이 하나라도 붙은 문장 비율
        "inflation": share(lambda lab: lab in INFLATION),
        "oversoftening": share(lambda lab: lab == "지나친 흐림"),
        "attribution": share(lambda lab: lab == "귀속 누락"),
        "opinion": share(lambda lab: lab == "의견→사실"),
        "factual_error": share(lambda lab: lab == "사실 오류"),
        "coverage": sum(hit) / len(hit) if hit else None,
        "coverage_per_sentence": sum(hit) / n if hit else None,
        "first_sentence_new": float(bool(judged.get("first_sentence_new"))),
        "ai_coverage": sum(ai) / len(ai) if ai else None,
    }


def _latest_runs(runs: list[dict]) -> tuple[list[dict], int]:
    """(조건, 기사, 회차)마다 인프라 오류가 아닌 마지막 기록 + 인프라 오류만 남은 키 수(빠진 것으로 보고)."""
    latest: dict[tuple, dict] = {}
    keys = set()
    for r in runs:
        k = (r.get("arm"), r.get("source_id"), r.get("rep"))
        keys.add(k)
        if not is_infra_error(r):
            latest[k] = r
    return list(latest.values()), len(keys - set(latest))


def _rep_rows(arm: str, runs: list[dict], judged: list[dict], keyfacts: dict, sources: dict) -> list[dict]:
    jmap = {(j["arm"], j["source_id"], j["rep"]): j for j in judged}
    rows = []
    for r in _latest_runs(runs)[0]:
        if r.get("arm") != arm or r.get("decision") != "PUBLISH":
            continue
        sid = r["source_id"]
        j = jmap.get((arm, sid, r["rep"]))
        rows.append({"source_id": sid, "rep": r["rep"], "judged": j} | rep_metrics(r, j, keyfacts.get(sid, []), sources.get(sid)))
    return rows


def _mean(xs) -> float:
    xs = [x for x in xs if x is not None and not math.isnan(x)]
    return statistics.fmean(xs) if xs else math.nan


def _pct(xs: list[float], q: int) -> float:
    if not xs:
        return math.nan
    return statistics.quantiles(xs, n=100, method="inclusive")[q - 1] if len(xs) > 1 else xs[0]


def _by_article(rows: list[dict], metric: str) -> dict[str, list[float]]:
    out: dict[str, list[float]] = {}
    for r in rows:
        v = r.get(metric)
        if v is not None and not math.isnan(v):
            out.setdefault(r["source_id"], []).append(v)
    return out


def _cost_latency_by_article(mine: list[dict], prices: dict | None, verifier: str | None) -> tuple[dict, dict]:
    """기사마다 실행별 카드 비용(모든 실행 — 실패한 실행도 돈이 든다)과 순차 회차 처리 시간(동시 실행은 지연을 부풀린다)."""
    cost: dict[str, list[float]] = {}
    latency: dict[str, list[float]] = {}
    for r in mine:
        sid = r["source_id"]
        if prices is not None and verifier:
            cost.setdefault(sid, []).append(costs.card_cost(r, prices, verifier)[0])
        if r.get("sequential") and r.get("duration_ms") is not None:
            latency.setdefault(sid, []).append(float(r["duration_ms"]))
    return cost, latency


def per_article(arm: str, runs: list[dict], judged: list[dict], *, keyfacts: dict, sources: dict,
                prices: dict | None = None, verifier: str | None = None) -> dict[str, dict[str, float]]:
    """기사마다 발행된 반복의 평균 — 결정(짝 비교)의 입력. 값이 없는 지표는 넣지 않는다(0 으로 채우지 않음).
    비용(cost_per_card)·순차 처리 시간(latency_seq)도 기사 짝으로 겨루도록 같이 담는다."""
    rows = _rep_rows(arm, runs, judged, keyfacts, sources)
    out: dict[str, dict[str, float]] = {}
    for metric in DECISION_METRICS:
        for sid, vals in _by_article(rows, metric).items():
            out.setdefault(sid, {})[metric] = statistics.fmean(vals)
    cost, latency = _cost_latency_by_article(_latest_runs([r for r in runs if r.get("arm") == arm])[0], prices, verifier)
    for key, by in (("cost_per_card", cost), ("latency_seq", latency)):
        for sid, vals in by.items():
            out.setdefault(sid, {})[key] = statistics.fmean(vals)
    return out


def _pooled(rows: list[dict], keyfacts: dict, attr: str) -> dict[str, float]:
    """위치(앞·중·뒤)·범주별 커버리지 — 판정된 실행 전체를 합쳐 센다(설명용)."""
    hit: dict[str, list[bool]] = {}
    for r in rows:
        if not r["judged"]:
            continue
        covered = r["judged"].get("covered") or {}
        for f in keyfacts.get(r["source_id"], []):
            key = getattr(f, attr)
            if key is not None:
                hit.setdefault(key, []).append(bool(covered.get(f.id)))
    return {k: sum(v) / len(v) for k, v in hit.items()}


def scorecard(arm: str, runs: list[dict], judged: list[dict], prices: dict, verifier: str, *,
              keyfacts: dict, sources: dict) -> dict:
    """조건 하나의 성적표. 발행·속도·비용은 모든 실행, 품질은 발행된 실행의 평균(판정 지표는 판정된 것만)."""
    mine, infra_only = _latest_runs([r for r in runs if r.get("arm") == arm])
    rows = _rep_rows(arm, mine, judged, keyfacts, sources)
    n = len(mine) or 1
    seq = sorted(float(r["duration_ms"]) for r in mine if r.get("sequential") and r.get("duration_ms") is not None)
    card_costs = [costs.card_cost(r, prices, verifier) for r in mine]

    def avg(key: str) -> float:
        return _mean(r.get(key) for r in rows)

    return {
        "arm": arm, "n_runs": len(mine), "n_published": len(rows), "n_judged": sum(1 for r in rows if r["judged"]),
        "infra_only": infra_only,
        # 발행
        "failure_rate": sum(_failed(r, f2_adjusted=False) for r in mine) / n,
        "failure_rate_f2_adjusted": sum(_failed(r, f2_adjusted=True) for r in mine) / n,
        "f2_quarantines": sum(1 for r in mine if r.get("decision") == "QUARANTINE" and _f2_only(r)),
        "errors": sum(1 for r in mine if r.get("decision") == "ERROR"),
        # 안전
        "bypass_rate": avg("bypass_rate"), "code_bypass_rate": avg("code_bypass_rate"),
        "quote_mismatch_rate": avg("quote_mismatch_rate"),
        # 충실도
        "fidelity": avg("fidelity"), "inflation_rate": avg("inflation"), "oversoftening_rate": avg("oversoftening"),
        "attribution_rate": avg("attribution"), "opinion_rate": avg("opinion"), "factual_error_rate": avg("factual_error"),
        # 커버리지
        "coverage": avg("coverage"), "coverage_by_tercile": _pooled(rows, keyfacts, "tercile"),
        "coverage_by_category": _pooled(rows, keyfacts, "category"),
        "coverage_per_sentence": avg("coverage_per_sentence"), "first_sentence_new_rate": avg("first_sentence_new"),
        "ai_coverage": avg("ai_coverage"),
        # 형식
        "sentences_mean": avg("sentences"), "long_sentence_ratio": avg("long_sentence_ratio"), "hedge_rate": avg("hedge"),
        "depth_mean": avg("depth"), "translit_rate": avg("translit"), "claims_mean": avg("claims"),
        "title_repeat_rate": avg("title_repeat"), "why_new_numbers_rate": avg("why_new_numbers"),
        "first_pass_rate": sum(1 for r in mine if r.get("decision") == "PUBLISH" and r.get("attempts") == 1) / n,
        # 속도·비용
        "latency_p50": _pct(seq, 50), "latency_p95": _pct(seq, 95), "n_sequential": len(seq),
        "cost_per_card": _mean(c for c, _ in card_costs), "cost_verified": all(v for _, v in card_costs),
        # 결정용 — 같은 조건 반복 사이 표준편차('차이 없음' 문턱). 순차 처리 시간은 기사당 1회라 0(구간만 본다).
        "rep_sd": {m: rep_sd(_by_article(rows, m)) for m in DECISION_METRICS}
                  | dict(zip(("cost_per_card", "latency_seq"), map(rep_sd, _cost_latency_by_article(mine, prices, verifier)))),
    }


# ── 결정 ──
def _compare(per: dict, cards: dict, x: str, y: str, metric: str) -> list:
    """x − y 를 기사마다 짝지어 [평균, 하한, 상한, 차이없음, 짝 수]. 문턱 = 두 조건 반복 표준편차의 평균."""
    diffs = {}
    for sid in sorted(set(per.get(x, {})) & set(per.get(y, {}))):
        a, b = per[x][sid].get(metric), per[y][sid].get(metric)
        if a is not None and b is not None:
            diffs[sid] = a - b
    ci = paired_bootstrap(diffs)
    sd = (cards[x].get("rep_sd", {}).get(metric, 0.0) + cards[y].get("rep_sd", {}).get(metric, 0.0)) / 2
    return [ci[0], ci[1], ci[2], no_difference(ci, sd), len(diffs)]


# -1: 낮을수록 좋다(결함·비용·시간), +1: 높을수록 좋다. 단계마다 '차이 없음'이면 다음 단계로(계획 Task 12).
_STEPS = (("fidelity", -1), ("coverage", +1), ("cost_per_card", -1), ("latency_seq", -1))


def _beats(x: str, y: str, cards: dict, per: dict) -> tuple[int, str]:
    """x 가 y 를 이기면 (1, 단계), 지면 (-1, 단계), 끝까지 '차이 없음'이면 (0, '')."""
    for metric, sign in _STEPS:
        mean, _, _, same, _ = _compare(per, cards, x, y, metric)
        if not same:
            return (1 if mean * sign > 0 else -1), metric
    return 0, ""


def _rank(arms: list[str], cards: dict, per: dict) -> tuple[list[str], dict, dict[str, int]]:
    """쌍마다 겨뤄 이긴 횟수(동률 0.5)로 순위 — '차이 없음'은 이행적이지 않아 정렬 비교함수 대신 쓴다.
    같은 점수는 공동 순위(ranks 가 같은 번호) — 잡음 수준의 원시 비용으로 다시 가르지 않는다. 목록 순서는 입력 순서."""
    score = dict.fromkeys(arms, 0.0)
    pairs = {}
    for i, x in enumerate(arms):
        for y in arms[i + 1:]:
            w, step = _beats(x, y, cards, per)
            if w > 0:
                score[x] += 1
            elif w < 0:
                score[y] += 1
            else:
                score[x] += 0.5
                score[y] += 0.5
            pairs[f"{x} vs {y}"] = {"winner": x if w > 0 else y if w < 0 else None, "by": step or "동률"}
    order = sorted(arms, key=lambda a: (-score[a], arms.index(a)))
    ranks = {a: 1 + sum(1 for b in arms if score[b] > score[a]) for a in arms}
    return order, pairs, ranks


def decide(cards: dict[str, dict], per_article: dict[str, dict[str, dict[str, float]]], *, baseline: str = "A0") -> dict:
    """탈락(기준선보다 안전·충실도가 나빠짐 — '차이 없음'이 아닌 악화, 또는 발행 실패율 +5%p 이상) → 남은 조건 순위."""
    arms = list(cards)
    base = cards[baseline]
    eliminated: dict[str, list[str]] = {}
    comparisons: dict[str, dict[str, list]] = {}
    for arm in arms:
        if arm == baseline:
            continue
        comp = {m: _compare(per_article, cards, arm, baseline, m) for m in DECISION_METRICS}
        comparisons[arm] = comp
        reasons = []
        fx, fb = cards[arm]["failure_rate_f2_adjusted"], base["failure_rate_f2_adjusted"]
        if fx >= fb + FAILURE_MARGIN - 1e-9:
            reasons.append(f"발행 실패율 {fx:.1%} ≥ {baseline} {fb:.1%} + {FAILURE_MARGIN:.0%}p")
        for metric, label in SAFETY + (("fidelity", "충실도 결함"),):
            mean, lo, hi, same, n = comp[metric]
            if not same and mean > 0:
                kind = "안전" if metric != "fidelity" else "충실도"
                reasons.append(f"{kind}: {label} 악화 +{mean:.3f} (95% 구간 [{lo:.3f}, {hi:.3f}], 기사 {n}건)")
        if reasons:
            eliminated[arm] = reasons
    ranking, pairwise, ranks = _rank([a for a in arms if a not in eliminated], cards, per_article)
    return {"baseline": baseline, "eliminated": eliminated, "ranking": ranking, "ranks": ranks, "comparisons": comparisons,
            "pairwise": pairwise}


# ── CLI ──
ORIGINAL_ARMS = "A0,A1,A2,A3,A4,A5"   # 원래 Stage A(설계 §7) — 기본값이 원래 성적표를 그대로 다시 만든다


def parse_args(argv: list[str] | None = None):
    import argparse
    ap = argparse.ArgumentParser(prog="aggregate")
    ap.add_argument("--arms", default=ORIGINAL_ARMS, help="콤마 구분 조건(기본 = 원래 Stage A 6조건)")
    ap.add_argument("--baseline", default="A0")
    ap.add_argument("--out-prefix", default="", help="결과 파일 이름 앞에 붙임(예 s1_) — 원래 성적표를 덮어쓰지 않게")
    return ap.parse_args(argv)


def out_names(prefix: str) -> tuple[str, str]:
    return f"{prefix}scorecards.json", f"{prefix}decision.json"


def main(argv: list[str] | None = None) -> None:
    from briefing.core.stores.source_store import SourceStore

    from .author_runner import ARMS

    need = [STAGE_A, JUDGE_DIR / "final.jsonl", JUDGE_DIR / "keyfacts.jsonl"]
    missing = [str(p) for p in need if not p.exists()]
    if missing:
        print("집계할 입력이 아직 없다 — Stage A 실행과 채점 뒤에 돈다: " + ", ".join(missing), file=sys.stderr)
        sys.exit(1)
    runs = read_jsonl(STAGE_A)
    args = parse_args(argv)
    wanted = args.arms.split(",")
    arms = [a for a in ARMS if a in wanted and any(r.get("arm") == a for r in runs)]
    runs = [r for r in runs if r.get("arm") in arms]
    judged = read_jsonl(JUDGE_DIR / "final.jsonl")
    keyfacts = {r["source_id"]: [KeyFact(**f) for f in r["facts"]] for r in read_jsonl(JUDGE_DIR / "keyfacts.jsonl")}
    store = SourceStore(str(EXP_ROOT / "sources"))
    sources = {sid: store.get_source(sid) for sid in sorted({r["source_id"] for r in runs})}
    verifiers = sorted({r.get("verifier") for r in runs})
    if len(verifiers) != 1:
        print(f"Stage A 검증기가 하나가 아니다: {verifiers}", file=sys.stderr)
        sys.exit(1)
    prices = costs.load_prices()
    cards = {a: scorecard(a, runs, judged, prices, verifiers[0], keyfacts=keyfacts, sources=sources) for a in arms}
    per = {a: per_article(a, runs, judged, keyfacts=keyfacts, sources=sources, prices=prices, verifier=verifiers[0])
           for a in arms}
    decision = decide(cards, per, baseline=args.baseline)
    RESULTS.mkdir(parents=True, exist_ok=True)
    sc_name, dec_name = out_names(args.out_prefix)
    (RESULTS / sc_name).write_text(json.dumps({"verifier": verifiers[0], "cards": cards, "per_article": per},
                                                        ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    (RESULTS / dec_name).write_text(json.dumps(decision, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"eliminated": decision["eliminated"], "ranking": decision["ranking"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
