"""render — 검증 명세서 메일: 헤더(인장·날짜·관점)·카드 2섹션(요약→해석, depth)·검증줄(다른 AI 에이전트 N건)·분야 밴드·다크모드·푸터."""
from types import SimpleNamespace

from briefing.core.authoring.author import Claim, DraftCard
from briefing.core.verification.certifier import CertVerdict
from briefing.core.gate import GatedCard
from briefing.core.render import format_briefing_date, render_email


def _user(depth="full", lens="engineer", send_hour=7):
    return SimpleNamespace(id="u-secret-id", depth=depth, lens=lens, send_hour=send_hour)


def _card(source_id="sid", headline="헤드라인", summary="요약문장.", why="해석문장.", claims=None):
    claims = claims or (Claim("C1", "원자주장", "entailment", "core"),)
    return DraftCard(source_id, headline, summary, why, claims)


def _gated(decision="PUBLISH", verdicts=None, **kw):
    verdicts = verdicts or (CertVerdict("C1", "VERIFIED", "ev"),)
    return GatedCard(_card(**kw), verdicts, decision, 1)


# ── 헤더 ──────────────────────────────────────────────
def test_header_shows_brand_and_seal_and_hides_user_id():
    out = render_email([_gated()], _user(), None)
    assert "오늘의 브리핑" in out
    assert "AI 에이전트 원문 대조" in out     # 검증 인장 — 누가 검증했는지(차별점) 포함
    assert "u-secret-id" not in out          # 내부 user.id 노출 제거


def test_header_shows_date_when_today_given():
    out = render_email([_gated()], _user(), None, today="6월 29일 (월)")
    assert "6월 29일 (월)" in out


def test_subtitle_shows_count_lens_without_duplicating_verification():
    out = render_email([_gated()], _user(lens="engineer"), None)
    assert "소식 1개" in out
    assert "engineer 관점 해석" in out        # 2층화: lens 는 '해석'을 소유(요약은 공통 사실)
    assert "관점 요약" not in out             # 옛 카피('{lens} 관점 요약')는 거짓이 됨 — 제거
    assert out.count("원문 대조") == 1        # 헤더 인장에만 1회 — 부제의 "원문 대조" 중복 제거
    assert "개 분야" not in out               # 1개 분야면 분야 표기 안 함


# ── 카드 2섹션 + depth 매핑 ──────────────────────────────
def test_full_depth_shows_summary_and_interpretation():
    out = render_email([_gated(summary="요약본문.", why="해석본문.")], _user(depth="full"), None)
    assert "요약본문." in out
    assert "나에게 왜 중요한가" in out
    assert "해석본문." in out


def test_summary_depth_shows_summary_and_interpretation():
    # mockup §4: summary(standard) = 요약 + 왜 중요한가 (둘 다). title-only 만 해석 생략.
    out = render_email([_gated(summary="요약본문.", why="해석본문.")], _user(depth="summary"), None)
    assert "요약본문." in out
    assert "나에게 왜 중요한가" in out
    assert "해석본문." in out


def test_title_only_depth_shows_summary_without_interpretation():
    out = render_email(
        [_gated(headline="헤드만", summary="요약본문.", why="해석본문.")], _user(depth="title-only"), None
    )
    assert "헤드만" in out and "요약본문." in out          # title-only 도 요약은 노출
    assert "나에게 왜 중요한가" not in out and "해석본문." not in out  # 해석만 생략


# ── 검증줄(다른 AI 에이전트 + 숫자 + 근거) ──────────────────
def test_trust_line_credits_other_agent_with_figure_and_hides_claims():
    gated = _gated(
        verdicts=(CertVerdict("C1", "VERIFIED", "ev"), CertVerdict("C2", "VERIFIED", "ev")),
        claims=(Claim("C1", "비밀주장하나", "entailment", "core"),
                Claim("C2", "비밀주장둘", "arithmetic", "core")),
    )
    out = render_email([gated], _user(), None)
    assert "다른 AI 에이전트가 요약의 사실 2건 검증" in out   # 검증 범위 정직화 — 배지는 '요약'만 커버
    assert "근거 보기" not in out             # ii: 펼침 제거 — 정직한 한 줄만
    assert "비밀주장" not in out              # 개별 claim 텍스트 비노출(불변식 유지)


def test_trust_line_marks_held_when_blocked_present():
    gated = _gated(
        decision="PUBLISH",
        verdicts=(CertVerdict("C1", "VERIFIED", "ev"), CertVerdict("C2", "BLOCKED", "ev")),
        claims=(Claim("C1", "x", "entailment", "core"), Claim("C2", "y", "arithmetic", "supporting")),
    )
    out = render_email([gated], _user(), None)
    assert "사실 1건 검증" in out
    assert "제외 1건" in out          # BLOCKED = 본문에서 제외(dropped)


# ── QUARANTINE 제외 / 폴백 ─────────────────────────────
def test_quarantine_excluded_and_fallback_when_empty():
    out = render_email([_gated(decision="QUARANTINE", headline="격리카드")], _user(), None)
    assert "격리카드" not in out
    assert "없습니다" in out


# ── 출처 줄(도메인·날짜·원문 링크) ──────────────────────────
def test_source_line_has_domain_date_and_original_link(tmp_path):
    from briefing.core.stores.source_store import SourceStore

    store = SourceStore(str(tmp_path / "s"))
    fs = store.freeze(url="https://www.aitimes.com/a", title="원본제목", raw_text="본문",
                      fetched_at="2026-06-27T06:00:00Z")
    # 제목=기사 원제목(사실층 앵커)은 h2 로 노출 — draft_card 가 headline=source.title 세팅하는 걸 모사.
    gated = GatedCard(_card(source_id=fs.source_id, headline="원본제목"), (CertVerdict("C1", "VERIFIED", "ev"),), "PUBLISH", 1)
    out = render_email([gated], _user(), None, store)
    assert "aitimes.com" in out               # 출처줄 = 도메인·날짜·원문 링크(provenance)
    assert 'href="https://www.aitimes.com/a"' in out
    assert "2026-06-27" in out
    assert "원문" in out
    assert "원본제목" in out                  # 원제목 = h2(카드 제목)


def test_source_line_omits_title_now_that_it_is_the_h2(tmp_path):
    # 아키텍처: 제목=기사 원제목이 h2 로 승격 → 출처줄엔 제목 병기·말줄임 없음(중복·2줄 스캔 제거).
    from briefing.core.stores.source_store import SourceStore

    store = SourceStore(str(tmp_path / "s"))
    fs = store.freeze(url="https://x.com/a", title="원본제목XYZ", raw_text="본문",
                      fetched_at="2026-06-27T06:00:00Z")
    gated = GatedCard(_card(source_id=fs.source_id, headline="다른헤드라인"), (CertVerdict("C1", "VERIFIED", "ev"),), "PUBLISH", 1)
    out = render_email([gated], _user(), None, store)
    assert "원본제목XYZ" not in out            # 출처줄이 source.title 을 더는 병기하지 않음(h2=card.headline)
    assert "다른헤드라인" in out and "x.com" in out  # h2=card.headline · 출처줄=도메인


# ── 분야(Area) 밴드: 2개 이상일 때만 ──────────────────────
def test_area_bands_render_when_two_or_more_categories():
    g1 = _gated(headline="가카드", source_id="s1")
    g2 = _gated(headline="나카드", source_id="s2")
    cats = {"s1": "AI 뉴스", "s2": "프런티어 AI 랩"}
    out = render_email([g1, g2], _user(), None, source_categories=cats)
    assert "AI 뉴스" in out and "프런티어 AI 랩" in out
    assert "2개 분야" in out
    assert out.index("AI 뉴스") < out.index("프런티어 AI 랩")   # 첫 등장 순서 유지


def test_no_bands_when_single_category():
    g1 = _gated(source_id="s1")
    g2 = _gated(source_id="s2")
    cats = {"s1": "AI 뉴스", "s2": "AI 뉴스"}
    out = render_email([g1, g2], _user(), None, source_categories=cats)
    assert "개 분야" not in out
    assert "◆" not in out


# ── 다크모드 캔버스 / 푸터 차별점 ──────────────────────────
def test_dark_mode_canvas_anchored():
    out = render_email([_gated()], _user(), None)
    assert "background-color" in out
    assert "color-scheme" in out


def test_footer_explains_decorrelation_plainly():
    out = render_email([_gated()], _user(lens="engineer"), None)
    assert "요약을 만들지 않은 다른 AI 에이전트가 그 요약을 원문과 대조" in out
    assert "확인된 요약 위에 engineer 관점의 해석" in out   # 2층 구조를 정직하게 설명(검증=요약, 해석=관점)
    assert "확인되지 않은 내용은 보내지 않습니다" in out


# ── 2층화 카드 라벨 (card-layering §5): 요약=공통 사실, 해석=lens 소유 ──────


def test_card_labels_split_fact_and_lens_interpretation():
    out = render_email([_gated()], _user(lens="engineer"), None)
    assert "요약 · 원문 사실" in out                       # 요약 라벨에서 lens 제거(공통 사실층)
    assert "나에게 왜 중요한가 · engineer 관점" in out      # 개인화 재정박 = 해석 블록(UX 채택 조건)


# ── 날짜 포맷터(헤더용) ──────────────────────────────────
def test_format_briefing_date_korean():
    assert format_briefing_date("2026-06-29") == "6월 29일 (월)"          # 2026-06-29 = 월요일
    assert format_briefing_date("2026-06-29T07:00:00Z") == "6월 29일 (월)"  # ISO 타임스탬프도 OK


def test_format_briefing_date_empty_or_invalid_is_blank():
    assert format_briefing_date("") == ""
    assert format_briefing_date("nope") == ""
