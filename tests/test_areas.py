"""areas — 메일 전체(헤드라인 칸·카드 밴드·라벨 프롬프트)가 공유하는 분야 6칸(2026-10-24 사용자 결정)."""
from briefing.core import areas


def test_areas_are_the_six_user_approved_names_in_mail_order():
    assert areas.AREAS == ("AI Agents", "Applied AI", "Models & Releases", "Inference & Hardware",
                           "Safety, Security & Policy", "Industry & Business")   # 2026-10-24 사용자 결정 — 메일 순서


def test_area_definitions_mention_every_area_and_the_five_rules():
    for a in areas.AREAS:
        assert a in areas.AREA_DEFINITIONS and a in areas.AREA_DEFINITIONS_HEADLINES
    assert "availability" in areas.AREA_DEFINITIONS          # 규칙 ② 플랫폼 제공 → Models & Releases
    assert "named" in areas.AREA_DEFINITIONS                 # 규칙 ⑤ named org 사례 → Applied AI
