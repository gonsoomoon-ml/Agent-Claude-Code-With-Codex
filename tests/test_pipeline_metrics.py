"""pipeline metrics — UserBriefing.cost_usd/duration_ms carrier 필드 회귀 테스트."""
from briefing.core.pipeline import UserBriefing


def test_userbriefing_has_cost_and_duration_defaults():
    b = UserBriefing(user_id="u", recipient="r", cards=(), email="", published=0, quarantined=0)
    assert b.cost_usd == 0.0
    assert b.duration_ms == 0
