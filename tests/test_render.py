"""render — PUBLISH-only · 출처 도메인 reference·발행일·렌즈 · 집계 trust(개별 claim 비노출)."""
from types import SimpleNamespace

from briefing.shared.harness.author import Claim, DraftCard
from briefing.shared.harness.certifier import CertVerdict
from briefing.shared.gate import GatedCard
from briefing.shared.render import render_email


def _user(depth="full"):
    return SimpleNamespace(id="u", depth=depth, lens="engineer")


def _gated(decision, verdicts, claims):
    return GatedCard(DraftCard("sid", "헤드라인", "요약", "왜중요", claims), verdicts, decision, 1)


def test_render_hides_claims_shows_aggregate_and_lens():
    gated = _gated("PUBLISH",
                   (CertVerdict("C1", "VERIFIED", "ev"), CertVerdict("C2", "BLOCKED", "ev")),
                   (Claim("C1", "검증된 항목", "entailment", "core"),
                    Claim("C2", "미검증 항목", "arithmetic", "supporting")))
    out = render_email([gated], _user(), None)
    assert "검증된 항목" not in out and "미검증 항목" not in out   # 개별 claim 텍스트 비노출(debug-time)
    assert "사실 1건 독립 검증" in out and "보류 1건" in out        # 집계 trust 라인
    assert "engineer 관점" in out                                  # lens


def test_render_excludes_quarantine_and_falls_back_when_empty():
    gated = _gated("QUARANTINE", (CertVerdict("C1", "BLOCKED", "ev"),),
                   (Claim("C1", "x", "entailment", "core"),))
    out = render_email([gated], _user(), None)
    assert "헤드라인" not in out  # QUARANTINE 카드는 사용자 이메일에서 제외
    assert "없습니다" in out       # 0건 발행 → 빈 메일 금지 폴백


def test_render_includes_domain_title_url_date_from_store(tmp_path):
    from briefing.shared.stores.source_store import SourceStore
    store = SourceStore(str(tmp_path / "s"))
    fs = store.freeze(url="https://www.aitimes.com/a", title="원본 제목", raw_text="본문",
                      fetched_at="2026-06-27T06:00:00Z")
    card = DraftCard(fs.source_id, "헤드라인", "요약", "왜중요", (Claim("C1", "x", "entailment", "core"),))
    gated = GatedCard(card, (CertVerdict("C1", "VERIFIED", "ev"),), "PUBLISH", 1)
    out = render_email([gated], _user(), None, store)
    assert "aitimes.com" in out                                    # 도메인 reference (www. 제거)
    assert "원본 제목" in out and 'href="https://www.aitimes.com/a"' in out and "2026-06-27" in out
