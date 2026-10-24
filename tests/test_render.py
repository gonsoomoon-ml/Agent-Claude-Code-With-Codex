"""render — 검증 명세서 메일: 헤더(인장·날짜·관점)·카드 2섹션(요약→해석, depth)·검증줄(다른 AI 에이전트 N건)·분야 밴드·다크모드·푸터."""
from types import SimpleNamespace

from briefing.core.authoring.author import Claim, DraftCard
from briefing.core.verification.certifier import CertVerdict
from briefing.core.gate import GatedCard
from briefing.core.render import format_briefing_date, render_email
from briefing.core.retrieval.headlines import Headline


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
    assert "✓ 요약은 다른 AI 에이전트가 원문 대조" in out   # 인장 = 검증 범위(요약) + 누가(다른 AI — 차별점)
    assert "u-secret-id" not in out          # 내부 user.id 노출 제거


def test_header_shows_date_when_today_given():
    out = render_email([_gated()], _user(), None, today="6월 29일 (월)")
    assert "6월 29일 (월)" in out


def test_subtitle_shows_count_lens_without_duplicating_verification():
    out = render_email([_gated()], _user(lens="engineer"), None)
    assert "요약 1건" in out and "소식 " not in out and "카드 " not in out   # "소식"은 헤드라인도 뜻해 모호, "카드"는 내부 용어
                                                                         # → 인장("요약은…")·카드 라벨("요약 · 원문 사실")과 같은 말
    assert "Engineer 관점 해석" in out        # 2층화: lens 는 '해석'을 소유. 표시 = lenses.yaml 영문 이름
    assert "관점 요약" not in out             # 옛 카피('{lens} 관점 요약')는 거짓이 됨 — 제거
    assert out.count("원문 대조") == 1        # 헤더 인장에만 1회 — 부제의 "원문 대조" 중복 제거
    assert "개 분야" not in out               # 1개 분야면 분야 표기 안 함


# ── 카드 2섹션 + depth 매핑 ──────────────────────────────
def test_full_depth_shows_summary_and_interpretation():
    out = render_email([_gated(summary="요약본문.", why="해석본문.")], _user(depth="full"), None)
    assert "요약본문." in out
    assert "사실들을 엮으면" in out
    assert "해석본문." in out


def test_summary_depth_shows_summary_and_interpretation():
    # mockup §4: summary(standard) = 요약 + 왜 중요한가 (둘 다). title-only 만 해석 생략.
    out = render_email([_gated(summary="요약본문.", why="해석본문.")], _user(depth="summary"), None)
    assert "요약본문." in out
    assert "사실들을 엮으면" in out
    assert "해석본문." in out


def test_title_only_depth_shows_summary_without_interpretation():
    out = render_email(
        [_gated(headline="헤드만", summary="요약본문.", why="해석본문.")], _user(depth="title-only"), None
    )
    assert "헤드만" in out and "요약본문." in out          # title-only 도 요약은 노출
    assert "사실들을 엮으면" not in out and "해석본문." not in out  # 해석만 생략


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


# ── 격리(QUARANTINE) 카드도 싣는다 — ⚠ 표시(N5) / 폴백 ─────────────────────
# 2026-10-18 사용자 결정: 검증에서 막힌 기사도 메일에 넣는다 — 법률·금융·보안이 아닌 비중요 브리핑이라
# 빼는 쪽이 손해(30일 감사: 숫자 검사가 막은 claim 64건 중 틀린 것 0건). 대신 검증된 카드처럼 보이면 안 된다.
def _quarantined(**kw):
    return _gated(decision="QUARANTINE",
                  verdicts=(CertVerdict("C1", "BLOCKED", "ev"), CertVerdict("C2", "VERIFIED", "ev")),
                  claims=(Claim("C1", "막힌 주장", "arithmetic", "core"),
                          Claim("C2", "확인된 주장", "entailment", "supporting")), **kw)


def test_quarantined_card_is_shown_with_warning():
    out = render_email([_quarantined(headline="격리카드")], _user(), None)
    assert "격리카드" in out
    assert "⚠ 요약의 사실 1건을 원문에서 확인하지 못함" in out
    assert "다른 AI 에이전트가 요약의 사실" not in out     # '✓ … 검증' 문구는 격리 카드에 붙지 않는다
    assert "해석문장." in out                                # 관점 해석 칸도 싣는다
    assert "없습니다" not in out                             # 폴백 아님


def test_quarantined_card_never_goes_to_top_picks():
    """오늘의 핵심 3 은 검증된 카드만 — 격리 카드 id 가 와도 핵심 칸에 올리지 않는다."""
    cards = [_gated(source_id="p1", headline="검증1"), _quarantined(source_id="q1", headline="격리1")]
    assert "오늘의 핵심" not in render_email(cards, _user(), None, top_picks=["q1"])
    out = render_email(cards, _user(), None, top_picks=["q1", "p1"])
    assert "오늘의 핵심" in out and out.count("격리1") == 1
    assert out.index("검증1") < out.index("격리1")          # 핵심 칸(검증1) 다음에 나머지(격리1)


def test_subtitle_counts_quarantined_cards_too():
    out = render_email([_gated(source_id="p1"), _quarantined(source_id="q1")], _user(), None)
    assert "요약 2건" in out


def test_footer_no_longer_claims_unverified_is_withheld():
    out = render_email([_gated()], _user(), None)
    assert "확인되지 않은 내용은 보내지 않습니다" not in out
    assert "⚠" in out.split("이 브리핑은 어떻게 만드나요?", 1)[1]   # 꼬리말이 ⚠ 표시의 뜻을 밝힌다


def test_fallback_only_when_no_cards():
    assert "없습니다" in render_email([], _user(), None)


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
    assert "개 분야" not in out                 # 부제에서 분야 수 제거 — 헤드라인 칸의 분야(AI Agents…)와 뜻이 겹친다
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
    # 2층 구조를 정직하게 설명(검증=요약, 해석=관점). '확인된 요약 위에'는 격리 카드(N5)엔 맞지 않아
    # '확인된 사실을 근거로'로 — 해석은 VERIFIED claim 만 근거로 쓴다(based_on lint).
    assert "확인된 사실을 근거로 Engineer 관점의 해석" in out
    assert "원문에서 확인하지 못한 사실이 있는 요약에는 ⚠ 표시" in out   # N5: 막힌 기사도 싣고 표시한다


# ── 2층화 카드 라벨 (card-layering §5): 요약=공통 사실, 해석=lens 소유 ──────


def test_card_labels_split_fact_and_lens_interpretation():
    out = render_email([_gated()], _user(lens="engineer"), None)
    assert "요약 · 원문 사실" in out                       # 요약 라벨에서 lens 제거(공통 사실층)
    assert "사실들을 엮으면 · Engineer 관점" in out      # 개인화 재정박 = 해석 블록(UX 채택 조건)


# ── 날짜 포맷터(헤더용) ──────────────────────────────────
def test_format_briefing_date_korean():
    assert format_briefing_date("2026-06-29") == "6월 29일 (월)"          # 2026-06-29 = 월요일
    assert format_briefing_date("2026-06-29T07:00:00Z") == "6월 29일 (월)"  # ISO 타임스탬프도 OK


def test_format_briefing_date_empty_or_invalid_is_blank():
    assert format_briefing_date("") == ""
    assert format_briefing_date("nope") == ""


# ── 헤드라인 칸(제목·링크 전용 소스): 검증 카드 아래, "요약·검증 없음" 명시 ──────
def _hl(title="국내 AI <칩> 공개", url="https://www.aitimes.com/a?x=1&y=2", group="", area=""):
    return Headline("aitimes", "AI Times", title, url, "2026-10-17T01:00:00+00:00", group, area)


def test_headlines_section_above_cards_and_labelled_unverified():
    out = render_email([_gated()], _user(), None, headlines=[_hl()])
    assert "요약·검증 없음" in out
    assert 'href="https://www.aitimes.com/a?x=1&amp;y=2"' in out     # URL 이스케이프
    assert "국내 AI &lt;칩&gt; 공개" in out                          # 제목 이스케이프(원제목 그대로)
    assert out.index("요약·검증 없음") < out.index("요약문장.")      # 카드 위 — 메일 맨 위(아침에 먼저 훑는 칸)
    assert "헤드라인 1건 · 요약 1건" in out                          # 부제 = 메일 순서대로 헤드라인 → 요약


def test_headlines_show_media_once_in_section_title():
    out = render_email([_gated()], _user(), None, headlines=[_hl(), _hl(title="두 번째 AI 소식")])
    assert out.count("AI Times") == 1                                # 줄마다 반복하지 않고 칸 제목에 한 번


def test_seal_scopes_verification_to_summaries_with_or_without_headlines():
    """인장 = "요약은" — 요약이 있는 것은 카드뿐이라 헤드라인(요약·검증 없음)이 위에 있어도 범위가 저절로 맞고,
    해석(관점)까지 원문 대조한 것처럼 읽히지 않는다(검증줄 "요약의 사실 N건"과 같은 범위)."""
    out = render_email([_gated()], _user(), None, headlines=[_hl()])
    plain = render_email([_gated()], _user(), None)
    for o in (out, plain):
        assert "✓ 요약은 다른 AI 에이전트가 원문 대조" in o and "아래 카드는" not in o
    assert "헤드라인 칸은 요약·검증 없이" in out                      # 위치("맨 위") 대신 칸 이름 — 순서가 바뀌어도 맞다
    assert "헤드라인 칸" not in plain and "헤드라인 " not in plain.split("</h1>")[1].split("</p>")[0]   # 부제에도 없음


def test_headlines_not_rendered_without_published_cards():
    out = render_email([], _user(), None, headlines=[_hl()])
    assert "요약·검증 없음" not in out and "없습니다" in out       # 헤드라인만으로는 브리핑이 아니다


def test_headline_with_non_http_url_is_dropped():
    out = render_email([_gated()], _user(), None, headlines=[_hl(url="javascript:alert(1)")])
    assert "javascript:" not in out


def _box(out):
    return out.split("요약·검증 없음")[1].split("</div>")[0]


def test_headlines_grouped_by_area_in_fixed_order_and_empty_hidden():
    out = render_email([_gated()], _user(), None, headlines=[
        _hl("정책 소식", area="Safety, Security & Policy"), _hl("에이전트 소식 A", area="AI Agents"),
        _hl("에이전트 소식 B", area="AI Agents")])
    box = _box(out)
    assert box.index("AI Agents 2") < box.index("에이전트 소식 A") < box.index("에이전트 소식 B") \
        < box.index("Safety, Security &amp; Policy 1") < box.index("정책 소식")          # 분야 순서 고정, 분야 안은 선별 순서
    assert "Inference" not in box and "Models" not in box                      # 빈 분야는 소제목째 숨김


def test_headlines_without_area_render_as_one_list():
    box = _box(render_email([_gated()], _user(), None,
                            headlines=[_hl("소식 A", area="AI Agents"), _hl("소식 B")]))   # 하나라도 분야 없음
    assert "AI Agents" not in box and "소식 A" in box and "소식 B" in box      # 소제목 없이 한 목록(섞여 보이지 않게)


def test_headlines_show_no_region_marks():
    """지역(국내/해외)은 화면에 내지 않는다 — 소제목도, 줄 끝 표시(KR)도 없음(2026-10-18 사용자 결정).
    지역 판정은 선별 안에서만 쓴다(상한 초과 시 해외 끝에서 잘라 국내를 남김)."""
    box = _box(render_email([_gated()], _user(), None,
                            headlines=[_hl("국내 소식", group="국내"), _hl("해외 소식", group="해외")]))
    assert "KR" not in box and "해외 1" not in box and "국내 1" not in box


def test_briefing_date_is_recipient_local_date_of_send_time():
    """05:00 KST 발송 = 전날 20:00 UTC — 머리 날짜는 받는 사람 시간대의 날짜다(10-18 일). run_date(발송 기록의 UTC 날짜
    키 10-17)를 그대로 찍으면 일요일 아침 메일에 "10월 17일 (토)"가 나간다(2026-10-18 실제 발송)."""
    from datetime import datetime, timezone

    from briefing.core.render import briefing_date
    sent = datetime(2026, 10, 17, 20, 0, tzinfo=timezone.utc)
    assert briefing_date("2026-10-17", sent, "Asia/Seoul") == "10월 18일 (일)"
    assert briefing_date("2026-10-17", sent, "America/Los_Angeles") == "10월 17일 (토)"
    assert briefing_date("2026-10-17", datetime(2026, 10, 17, 20, 0), "Asia/Seoul") == "10월 18일 (일)"  # naive = UTC
    assert briefing_date("2026-10-17", None, "Asia/Seoul") == "10월 17일 (토)"   # 발송 시각이 없으면 run_date


# ── 오늘의 핵심 3 (top_picks) ───────────────────────────
def _six():
    """분야 3개에 걸친 발행 카드 6장 — a1·a2(News), b1·b2(AWS), c1·c2(Google)."""
    sids = ["a1", "a2", "b1", "b2", "c1", "c2"]
    cats = {"a1": "News & Media", "a2": "News & Media", "b1": "Amazon (AWS)", "b2": "Amazon (AWS)",
            "c1": "Google", "c2": "Google"}
    return [_gated(source_id=s, headline=f"제목-{s}") for s in sids], cats


def test_headlines_then_top_picks_then_bands():
    cards, cats = _six()
    out = render_email(cards, _user(), None, source_categories=cats, top_picks=["c1", "a1", "a2"],
                       headlines=[_hl()])
    top, heads, aws, google = (out.index(x) for x in ("오늘의 핵심", "요약·검증 없음", "◆ Amazon (AWS)", "◆ Google"))
    assert heads < top < aws < google                           # 헤드라인 칸 → 핵심 3 → 분야 섹션(2026-10-18 사용자 결정)
    assert "◆ News &amp; Media" not in out                      # News 카드가 전부 핵심으로 → 0건 밴드를 그리지 않음
    assert out.count("제목-c1") == 1 and top < out.index("제목-c1") < aws      # 핵심 카드는 원래 섹션에서 빠짐(중복 없음)
    assert out.index("제목-c1") < out.index("제목-a1") < out.index("제목-a2")  # 판정 순서 그대로
    assert "요약 6건" in out                                                   # 부제 = 발행 카드 전체 기준(핵심 포함)
    assert "◆ Google" in out and ">1건<" in out.split("◆ Google")[1][:200]     # 밴드 개수 = 남은 카드


def test_top_picks_keep_band_even_when_rest_is_one_category():
    cards = [_gated(source_id=f"s{i}", headline=f"제목{i}") for i in range(6)]
    cats = {f"s{i}": "Amazon (AWS)" for i in range(6)}
    out = render_email(cards, _user(), None, source_categories=cats, top_picks=["s3", "s4", "s5"])
    assert out.index("오늘의 핵심") < out.index("◆ Amazon (AWS)") < out.index("제목0")   # 핵심과 나머지를 밴드로 구분


def test_no_top_section_without_picks_and_unknown_ids_ignored():
    cards, cats = _six()
    assert "오늘의 핵심" not in render_email(cards, _user(), None, source_categories=cats)
    out = render_email(cards, _user(), None, source_categories=cats, top_picks=["zz"])
    assert "오늘의 핵심" not in out and "요약 6건" in out          # 모르는 id 는 무시 — 카드 유실 없음
