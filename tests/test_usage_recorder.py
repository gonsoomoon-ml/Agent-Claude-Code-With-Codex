import pytest

from briefing.core.stores.usage import UsageRecorder, certify_cost_usd


def test_recorder_accumulates_and_snapshots():
    r = UsageRecorder()
    assert r.total() == 0.0
    r.add(0.039)
    r.add(0.016)
    assert round(r.total(), 3) == 0.055


def test_certify_cost_from_codex_usage():
    """codex `turn.completed.usage` → 달러. 캐시 읽기·쓰기 단가는 몰라 입력 단가로 센다(보수적)."""
    usage = {"input_tokens": 10964, "cached_input_tokens": 0, "cache_write_input_tokens": 10922,
             "output_tokens": 88, "reasoning_output_tokens": 39}
    assert certify_cost_usd("openai.gpt-6-luna", usage) == pytest.approx((10964 * 0.10 + 88 * 0.50) / 1e6)
    assert certify_cost_usd("openai.gpt-9", usage) is None   # 단가 미상
