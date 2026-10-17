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
    cards = {"A0": _card(cost=0.05), "A2": _card(cost=0.20), "A3": _card(cost=0.10)}
    per = {"A0": _per_article(), "A2": _per_article(coverage=0.80), "A3": _per_article()}
    out = aggregate.decide(cards, per)
    assert out["ranking"][0] == "A2"   # 충실도 동률(차이 없음) → 커버리지 우위
    assert out["ranking"][1:] == ["A0", "A3"]                     # 그다음은 비용이 낮은 순
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
              "first_sentence_new": True, "fidelity": {"1": ["부풀림-확신도"]}, "bypass": []}]
    facts = {"s0": [KeyFact("K1", "출시", "q", 0.1, "앞", "새 사실", True), KeyFact("K2", "단서", "q", 0.9, "뒤", "단서", False)]}
    src = {"s0": FrozenSource("s0", "https://www.aitimes.com/news/x", "가 출시", "원문 본문이다.", "2026-10-17T00:00:00Z")}
    card = aggregate.scorecard("A2", runs, final, {}, "gpt-6-sol", keyfacts=facts, sources=src)
    assert card["failure_rate"] == pytest.approx(0.5) and card["failure_rate_f2_adjusted"] == pytest.approx(0.0)
    assert card["coverage"] == pytest.approx(0.5) and card["coverage_by_tercile"] == {"앞": 1.0, "뒤": 0.0}
    assert card["ai_coverage"] == pytest.approx(1.0) and card["first_sentence_new_rate"] == pytest.approx(1.0)
    assert card["inflation_rate"] == pytest.approx(0.5)            # 2문장 중 1문장
    assert card["cost_per_card"] == pytest.approx(0.2) and card["latency_p95"] == pytest.approx(200_000)
    assert card["first_pass_rate"] == pytest.approx(0.5) and card["claims_mean"] == pytest.approx(1.0)
