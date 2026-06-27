"""render — PUBLISH-only + verdict chip + graceful degradation(BLOCKED 드롭 + '보류' 표시)."""
from types import SimpleNamespace

from briefing.shared.author import Claim, DraftCard
from briefing.shared.certifier import CertVerdict
from briefing.shared.gate import GatedCard
from briefing.shared.render import render_email


def _user(depth="full"):
    return SimpleNamespace(id="u", depth=depth)


def _gated(decision, verdicts, claims):
    return GatedCard(DraftCard("sid", "헤드라인", "요약", "왜중요", claims), verdicts, decision, 1)


def test_render_drops_blocked_and_adds_note():
    claims = (Claim("C1", "검증된 항목", "entailment", "core"),
              Claim("C2", "미검증 항목", "arithmetic", "supporting"))
    gated = _gated("PUBLISH", (CertVerdict("C1", "VERIFIED", "ev"), CertVerdict("C2", "BLOCKED", "ev")), claims)
    out = render_email([gated], _user(), None)
    assert "검증된 항목" in out and "검증됨" in out   # C1 발행 + 칩
    assert "미검증 항목" not in out                    # C2 BLOCKED → 드롭(graceful degradation)
    assert "보류" in out                               # 드롭 표시(show your work)


def test_render_excludes_quarantine_and_falls_back_when_empty():
    gated = _gated("QUARANTINE", (CertVerdict("C1", "BLOCKED", "ev"),),
                   (Claim("C1", "x", "entailment", "core"),))
    out = render_email([gated], _user(), None)
    assert "헤드라인" not in out  # QUARANTINE 카드는 사용자 이메일에서 제외
    assert "없습니다" in out       # 0건 발행 → 빈 메일 금지 폴백
