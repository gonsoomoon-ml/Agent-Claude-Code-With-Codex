"""업그레이드 비교 실험 — 리포트 테스트: 절 구성·'미확인'·'차이 없음'·탈락 사유·빈 값 표기."""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from upgrade_eval import report  # noqa: E402

ARMS = {"A0": {"model_id": "global.anthropic.claude-sonnet-5", "cli_version": "2.1.195", "effort": None},
        "A2": {"model_id": "global.anthropic.claude-sonnet-5-5", "cli_version": "2.1.301", "effort": "medium"},
        "A3": {"model_id": "global.anthropic.claude-sonnet-5-5", "cli_version": "2.1.301", "effort": "high"}}


def _card(**kw):
    card = {"n_runs": 36, "n_published": 34, "n_judged": 33, "failure_rate": 0.06, "failure_rate_f2_adjusted": 0.03,
            "f2_quarantines": 1, "errors": 0, "bypass_rate": 0.05, "code_bypass_rate": 0.02, "quote_mismatch_rate": 0.0,
            "fidelity": 0.08, "inflation_rate": 0.05, "oversoftening_rate": 0.02, "attribution_rate": 0.01,
            "opinion_rate": 0.0, "coverage": 0.62, "coverage_by_tercile": {"앞": 0.8, "중": 0.5, "뒤": 0.3},
            "coverage_by_category": {"새 사실": 0.9, "단서": 0.4}, "coverage_per_sentence": 0.9,
            "first_sentence_new_rate": 0.9, "ai_coverage": 0.7, "sentences_mean": 4.2, "long_sentence_ratio": 0.1,
            "hedge_rate": 0.8, "depth_mean": 0.7, "translit_rate": 0.0, "claims_mean": 12.0, "title_repeat_rate": 0.1,
            "why_new_numbers_rate": 0.05, "first_pass_rate": 0.7, "latency_p50": 150_000, "latency_p95": 260_000,
            "n_sequential": 12, "cost_per_card": 0.21, "cost_verified": False,
            "rep_sd": {"bypass_rate": 0.0, "quote_mismatch_rate": 0.0, "fidelity": 0.0, "coverage": 0.0}}
    card.update(kw)
    return card


CARDS = {"A0": _card(), "A2": _card(coverage=0.71), "A3": _card(failure_rate_f2_adjusted=0.12, ai_coverage=math.nan)}
DECISION = {"baseline": "A0", "eliminated": {"A3": ["발행 실패율 12.0% ≥ A0 3.0% + 5%p"]}, "ranking": ["A2", "A0"],
            "comparisons": {
                "A2": {"bypass_rate": [0.01, -0.02, 0.04, True, 12], "quote_mismatch_rate": [0.0, 0.0, 0.0, True, 12],
                       "fidelity": [-0.01, -0.03, 0.01, True, 12], "coverage": [0.09, 0.04, 0.14, False, 12]},
                "A3": {"bypass_rate": [0.0, -0.01, 0.01, True, 11], "quote_mismatch_rate": [0.0, 0.0, 0.0, True, 11],
                       "fidelity": [0.0, -0.02, 0.02, True, 11], "coverage": [math.nan, math.nan, math.nan, True, 0]}},
            "pairwise": {"A0 vs A2": {"winner": "A2", "by": "coverage"}}}
_SCORE = {"catch_rate": 0.9, "catch_blocked_rate": 0.8, "fp_rate": 0.05, "fp_blocked": 0.03, "fp_demoted": 0.02,
          "consistency": 0.95, "cost_per_claim": 0.03, "cost_verified": False, "p50_ms": 9000, "p95_ms": 20000,
          "timeouts": 0, "n_true": 60, "n_uncertain": 13, "error_rate": 0.0, "errors": {}, "n_pairs": 90, "n_seq": 30}
STAGE_B = {"winner": "gpt-6-sol", "winner_healthy": "gpt-6-sol", "models": ["gpt-6-sol", "gpt-5.5"],
           "scores": {"gpt-6-sol": _SCORE, "gpt-5.5": _SCORE | {"cost_per_claim": 0.05, "consistency": 0.85}},
           "warnings": ["gpt-6-sol: 인프라 오류 시도 2회 · 2차 90/115 · 처리 시간 측정 30건"],
           "stage_a_certifier_cost_projection": {"literal": 12.3, "healthy": 12.3}, "entailment_claims_per_card": 6.1}
COSTS_UNVERIFIED = {"period": ["2026-09-17", "2026-10-17"],
                    "by_region_model": {"USE1": {"anthropic.claude-sonnet-5": 119.6, "openai.gpt-5.5": 0.0}},
                    "gpt55_list_price_equivalent": {"usd": 234.6, "price_verified": False, "price_source": "2차 출처"},
                    "notes": ["OpenAI(mantle) 청구액 $0 — 이유 미확인."]}
META = {"date": "2026-10-18", "n_articles": 12, "reps": 3, "arms": ARMS, "stage_a_verifier": "gpt-6-sol",
        "judges": {"main": "gpt-6-astra", "cross": "gpt-6.1-sol", "tiebreak": "grok-4.7"}, "cards_per_day": 19.0,
        "prices": {"gpt-6-astra": True, "gpt-6-sol": False, "global.anthropic.claude-sonnet-5-5": True}}


def test_report_sections_and_marks():
    md = report.render_report(DECISION, CARDS, STAGE_B, COSTS_UNVERIFIED, META)
    for h in ("## 결론", "## 요약 품질", "## 검증 AI", "## 비용", "## 처리 시간", "## 한계", "## 사례 모음", "## 다음 단계"):
        assert h in md
    assert "미확인" in md and "차이 없음" in md
    assert "A3" in md and "발행 실패율" in md          # 탈락 사유가 드러난다


def test_report_never_prints_nan_and_counts_missing_judgments():
    md = report.render_report(DECISION, CARDS, STAGE_B, COSTS_UNVERIFIED, META)
    assert "nan" not in md.lower()
    assert "비교 불가" in md                            # 짝이 없는 비교는 숫자 대신 그렇게 적는다
    assert "판정 누락" in md                            # 채점에서 빠진 실행 수를 보고(Review Focus 3)
    assert "사실 오류" in md


def test_report_marks_tied_ranks_as_joint():
    dec = DECISION | {"ranking": ["A2", "A0"], "ranks": {"A2": 1, "A0": 1}}
    md = report.render_report(dec, CARDS, STAGE_B, COSTS_UNVERIFIED, META)
    assert "공동 1위" in md and "A2 = A0" in md
