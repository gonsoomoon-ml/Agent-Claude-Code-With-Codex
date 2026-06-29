"""supervisor.render_briefing — 분야 맵(source_categories)·날짜(run_date)를 _CTX 에서 render 로 전달하는 배선 검증.

@tool 객체의 원함수(`_tool_func`)를 직접 호출 — Strands Agent/LLM 없이 도구 로직만 결정론 테스트.
"""
from types import SimpleNamespace

from briefing.runtime import supervisor
from briefing.shared.gate import GatedCard
from briefing.shared.harness.author import Claim, DraftCard
from briefing.shared.harness.certifier import CertVerdict


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
    assert "2개 분야" in email                                  # 분야 카운트
    assert "AI 뉴스" in email and "프런티어 AI 랩" in email       # 분야 밴드
    assert "6월 29일" in email                                  # run_date → 헤더 날짜
