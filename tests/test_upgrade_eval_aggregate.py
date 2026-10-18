"""업그레이드 비교 실험 — 집계·결정 테스트: 탈락 규칙·순위(차이 없음이면 다음 단계)·성적표 기본 비율."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from upgrade_eval import aggregate  # noqa: E402
from upgrade_eval.judge import KeyFact  # noqa: E402

from briefing.core.stores.source_store import FrozenSource  # noqa: E402

ARTICLES = [f"s{i}" for i in range(12)]
METRICS = ("bypass_rate", "quote_mismatch_rate", "fidelity", "coverage")


def _card(failure=0.05, cost=0.10, p95=100_000):
    return {"failure_rate_f2_adjusted": failure, "cost_per_card": cost, "latency_p95": p95,
            "rep_sd": {m: 0.0 for m in METRICS}}


def _per_article(**overrides):
    base = {"bypass_rate": 0.0, "quote_mismatch_rate": 0.0, "fidelity": 0.10, "coverage": 0.60}
    base.update(overrides)
    return {sid: dict(base) for sid in ARTICLES}


def test_decide_eliminates_failure_rate_and_worse_fidelity():
    cards = {"A0": _card(), "A3": _card(failure=0.12), "A4": _card()}
    per = {"A0": _per_article(), "A3": _per_article(), "A4": _per_article(fidelity=0.30)}
    out = aggregate.decide(cards, per)
    assert "발행 실패율" in " ".join(out["eliminated"]["A3"])      # A3: 0.12 vs A0 0.05
    assert "충실도" in " ".join(out["eliminated"]["A4"])          # A4: 부풀림↑, 구간 > 0
    assert out["ranking"] == ["A0"]


def test_decide_ranks_with_ties_falling_through():
    cards = {"A0": _card(), "A2": _card(), "A3": _card()}
    per = {"A0": _per_article(cost_per_card=0.05), "A2": _per_article(coverage=0.80, cost_per_card=0.20),
           "A3": _per_article(cost_per_card=0.10)}
    out = aggregate.decide(cards, per)
    assert out["ranking"][0] == "A2"   # 충실도 동률(차이 없음) → 커버리지 우위
    assert out["ranking"][1:] == ["A0", "A3"]                     # 그다음은 기사 짝 비용이 낮은 순(차이 있음)
    assert out["comparisons"]["A2"]["coverage"][3] is False       # 차이 있음
    assert out["comparisons"]["A3"]["fidelity"][3] is True        # 차이 없음


def test_decide_missing_articles_pair_on_intersection():
    cards = {"A0": _card(), "A2": _card()}
    per = {"A0": _per_article(), "A2": {sid: v for sid, v in _per_article(coverage=0.9).items() if sid != "s0"}}
    out = aggregate.decide(cards, per)
    assert out["comparisons"]["A2"]["coverage"][4] == 11        # s0 은 짝이 없어 빠진다(0 으로 채우지 않음)


def test_scorecard_basic_rates():
    runs = [
        {"arm": "A2", "source_id": "s0", "rep": 1, "sequential": True, "decision": "PUBLISH", "attempts": 1,
         "summary": "가는 출시했다고 밝혔다. 나는 늘었다.", "why": "의의다.", "claims": [{"id": "C1", "text": "가는 출시했다고 밝혔다"}],
         "verdicts": [], "author_runs": [{"cost_usd": 0.1}], "codex_calls": [], "duration_ms": 200_000, "over_360": False},
        {"arm": "A2", "source_id": "s0", "rep": 2, "sequential": False, "decision": "QUARANTINE", "attempts": 2,
         "summary": "다는 줄었다.", "why": "", "claims": [{"id": "C1", "text": "2분기부터 늘었다", "claim_type": "arithmetic",
                                                           "importance": "core"}],
         "verdicts": [{"claim_id": "C1", "verdict": "BLOCKED", "evidence": "원문에 없는 수치: 수량=[2.0]"}],
         "author_runs": [{"cost_usd": 0.3}], "codex_calls": [], "duration_ms": 300_000, "over_360": False},
    ]
    final = [{"arm": "A2", "source_id": "s0", "rep": 1, "covered": {"K1": True, "K2": False},
              "first_sentence_new": True, "fidelity": {"1": ["부풀림-확신도"], "0": ["사실 오류"]}, "bypass": []}]
    facts = {"s0": [KeyFact("K1", "출시", "q", 0.1, "앞", "새 사실", True), KeyFact("K2", "단서", "q", 0.9, "뒤", "단서", False)]}
    src = {"s0": FrozenSource("s0", "https://www.aitimes.com/news/x", "가 출시", "원문 본문이다.", "2026-10-17T00:00:00Z")}
    card = aggregate.scorecard("A2", runs, final, {}, "gpt-6-sol", keyfacts=facts, sources=src)
    assert card["failure_rate"] == pytest.approx(0.5) and card["failure_rate_f2_adjusted"] == pytest.approx(0.0)
    assert card["coverage"] == pytest.approx(0.5) and card["coverage_by_tercile"] == {"앞": 1.0, "뒤": 0.0}
    assert card["ai_coverage"] == pytest.approx(1.0) and card["first_sentence_new_rate"] == pytest.approx(1.0)
    assert card["inflation_rate"] == pytest.approx(0.5)            # 2문장 중 1문장
    assert card["factual_error_rate"] == pytest.approx(0.5) and card["fidelity"] == pytest.approx(1.0)
    assert card["cost_per_card"] == pytest.approx(0.2) and card["latency_p95"] == pytest.approx(200_000)
    assert card["first_pass_rate"] == pytest.approx(0.5) and card["claims_mean"] == pytest.approx(1.0)


def test_scorecard_uses_latest_non_infra_record_per_key():
    base = {"arm": "A2", "source_id": "s0", "rep": 1, "sequential": False, "attempts": 1, "summary": "가는 출시했다.",
            "why": "", "claims": [], "verdicts": [], "author_runs": [], "codex_calls": [], "duration_ms": 1, "over_360": False}
    runs = [base | {"decision": "ERROR", "error": "rc=1: throttled"}, base | {"decision": "PUBLISH", "error": None},
            base | {"rep": 2, "decision": "ERROR", "error": "rc=1: throttled"}]
    card = aggregate.scorecard("A2", runs, [], {}, "gpt-6-luna", keyfacts={}, sources={})
    assert card["n_runs"] == 1 and card["failure_rate"] == 0.0     # 재시도 전 인프라 오류는 발행 실패가 아니다
    assert card["infra_only"] == 1                                 # 인프라 오류만 남은 키는 빠진 것으로 보고


def test_cost_step_uses_no_difference_and_ties_share_rank():
    # 품질이 같고 기사별 비용 차이가 반복 표준편차보다 작으면 동률 — 카드당 $0.0014 로 순위를 가르지 않는다(계획 Task 12)
    cards = {"A0": _card(), "A2": _card(), "A3": _card()}
    for c in cards.values():
        c["rep_sd"]["cost_per_card"] = 0.004
    per = {"A0": _per_article(cost_per_card=0.10), "A2": _per_article(cost_per_card=0.0499),
           "A3": _per_article(cost_per_card=0.0485)}
    out = aggregate.decide(cards, per)
    assert out["pairwise"]["A2 vs A3"]["winner"] is None                       # 차이 없음 → 끝까지 동률
    assert out["pairwise"]["A0 vs A2"] == {"winner": "A2", "by": "cost_per_card"}  # 차이 $0.05 > 문턱
    assert out["ranks"] == {"A2": 1, "A3": 1, "A0": 3}                          # 공동 1위


def test_latency_step_uses_paired_sequential_durations():
    cards = {"A0": _card(), "A2": _card(), "A3": _card()}
    per = {"A0": _per_article(latency_seq=60_000), "A2": _per_article(latency_seq=20_000),
           "A3": _per_article(latency_seq=25_000)}
    out = aggregate.decide(cards, per)
    assert out["pairwise"]["A2 vs A3"] == {"winner": "A2", "by": "latency_seq"}   # 비용이 같으면 기사마다 더 빠른 쪽


def test_per_article_and_rep_sd_carry_cost_and_sequential_latency():
    def run(rep, seq, ms, cost):
        return {"arm": "A2", "source_id": "s0", "rep": rep, "sequential": seq, "decision": "PUBLISH", "attempts": 1,
                "summary": "가는 출시했다.", "why": "", "claims": [], "verdicts": [], "author_runs": [{"cost_usd": cost}],
                "codex_calls": [], "duration_ms": ms, "over_360": False}
    runs = [run(1, True, 20_000, 0.04), run(2, False, 50_000, 0.06)]
    src = {"s0": FrozenSource("s0", "https://www.aitimes.com/news/x", "가 출시", "원문 본문이다.", "2026-10-17T00:00:00Z")}
    per = aggregate.per_article("A2", runs, [], keyfacts={}, sources=src, prices={}, verifier="gpt-6-luna")
    assert per["s0"]["cost_per_card"] == pytest.approx(0.05)
    assert per["s0"]["latency_seq"] == pytest.approx(20_000)                    # 순차 회차만(동시 실행은 지연을 부풀린다)
    card = aggregate.scorecard("A2", runs, [], {}, "gpt-6-luna", keyfacts={}, sources=src)
    assert card["rep_sd"]["cost_per_card"] == pytest.approx(0.0141421356, rel=1e-6)


# ── S1(2026-10-18): 조건·기준선·출력 이름을 고른다(기본 = 원래 Stage A 6조건, 원래 파일 이름) ──────────

def test_cli_defaults_reproduce_original_stage_a():
    from upgrade_eval import aggregate
    args = aggregate.parse_args([])
    assert args.arms.split(",") == ["A0", "A1", "A2", "A3", "A4", "A5"] and args.baseline == "A0" and args.out_prefix == ""


def test_cli_s1_options_write_separate_files():
    from upgrade_eval import aggregate
    args = aggregate.parse_args(["--arms", "S1C,S1A", "--baseline", "S1C", "--out-prefix", "s1_"])
    assert aggregate.out_names(args.out_prefix) == ("s1_scorecards.json", "s1_decision.json")
