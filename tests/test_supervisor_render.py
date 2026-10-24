"""supervisor.render_briefing — 분야 맵(source_categories)·날짜(run_date)를 _CTX 에서 render 로 전달하는 배선 검증.

@tool 객체의 원함수(`_tool_func`)를 직접 호출 — Strands Agent/LLM 없이 도구 로직만 결정론 테스트.
"""
from types import SimpleNamespace

from briefing.runtime import supervisor
from briefing.core.gate import GatedCard
from briefing.core.authoring.author import Claim, DraftCard
from briefing.core.verification.certifier import CertVerdict


def _gated(sid, n):
    claims = tuple(Claim(f"C{j}", "f", "entailment", "core") for j in range(n))
    verds = tuple(CertVerdict(f"C{j}", "VERIFIED", "ev") for j in range(n))
    return GatedCard(DraftCard(sid, "헤드라인", "요약", "왜중요", claims), verds, "PUBLISH", 1)


def test_render_briefing_passes_area_map_and_date():
    supervisor._CTX.clear()
    user = SimpleNamespace(id="u", depth="full", lens="engineer", send_hour=7)
    supervisor._CTX.update(
        settings=None, store=None, user=user,
        cards=[_gated("s1", 19), _gated("s2", 20)],
        source_categories={"s1": "AI 뉴스", "s2": "프런티어 AI 랩"},
        run_date="2026-06-29",
    )
    supervisor.render_briefing._tool_func()  # @tool 원함수 직접 호출
    email = supervisor._CTX["email"]
    assert "요약 2건" in email                                  # 부제 요약(카드) 수
    assert "◆" not in email                                     # supervisor 는 라벨 미배선 → 평평(발행처 밴드 없음, 2026-10-24)
    assert "출처 ·" not in email                                # 테스트 category 는 카탈로그 밖 → 집계 줄 생략
    assert "6월 29일" in email                                  # run_date → 헤더 날짜
