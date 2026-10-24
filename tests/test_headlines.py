"""headlines — 제목·링크 전용 소스(AI타임스): 본문 미수집 · AI 판정자엔 제목만 · 검증 카드와 분리.

왜: AI타임스 기사마다 "무단전재 및 재배포, AI학습 및 활용 금지" 고지가 붙어 있다(2026-10-17 적법성 점검).
본문을 가져와 요약하는 대신, 기계가 읽으라고 공개한 RSS 의 제목·링크만 쓰고 Haiku 에는 제목만 넘긴다.
"""
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

import pytest

from briefing.core.retrieval import headlines as H
from briefing.core.retrieval import sources as S
from briefing.core.retrieval.curation import curate
from briefing.core.retrieval.sources import CATALOG, FetchedArticle, Source, _load_catalog
from briefing.core.stores.source_store import SourceStore


def _src(key="aitimes", *, require_ai=True, max_items=0, select="", url="https://aitimes/rss",
         headlines_only=True):
    return Source(key=key, name="AI Times", url=url, kind="rss", lang="ko", category="News & Media",
                  require_ai=require_ai, max_items=max_items, select=select, headlines_only=headlines_only)


def _arts(n, body="본문 전체 BODY"):
    return [FetchedArticle("aitimes", f"https://a/{i}", f"AI 기사 {i}", body, f"2026-10-17T0{i % 10}:00:00+00:00")
            for i in range(n)]


# ── catalog ──────────────────────────────────────────────
def test_catalog_marks_aitimes_headlines_only():
    by_key = {s.key: s for s in CATALOG}
    assert by_key["aitimes"].headlines_only is True
    # 제목별 관련성 판정 없이 Haiku 가 8건만 고른다 — 제목만으론 신제품명을 AI 로 못 알아본다(30일 소급: 4.5 오판 13건)
    assert by_key["aitimes"].require_ai is False and by_key["aitimes"].select == "llm"
    assert by_key["aitimes"].max_items == 15   # 메일 맨 위 칸(핵심 3 위) — 실무 핵심 + 국내 소식이 함께 들어가는 크기
    assert by_key["the-decoder"].headlines_only is False   # 기본값 = 기존 카드 경로


def test_catalog_rejects_non_bool_headlines_only(tmp_path):
    p = tmp_path / "catalog.yaml"
    p.write_text("- {key: k, name: n, url: 'https://x', kind: rss, lang: en, category: c, headlines_only: 'yes'}\n",
                 encoding="utf-8")
    with pytest.raises(ValueError, match="headlines_only"):
        _load_catalog(p)


# ── 제목만 AI 에 (고지 준수의 핵심 불변식) ─────────────────────
def test_ai_judges_receive_titles_only_never_body():
    seen: list[str] = []

    def rel(title, text):
        seen.append(text)
        return True

    def sel(arts, k, _covered):
        seen.extend(a.raw_text for a in arts)
        return [(a, "") for a in list(arts)[:k]]

    out = H.collect_headlines([_src(max_items=2, select="llm")], window_hours=24,
                              fetch_fn=lambda s, w: _arts(4), relevance_fn=rel, headline_select_fn=sel)
    assert seen and all(t == "" for t in seen)   # fetch 가 본문을 돌려줘도 판정자엔 빈 문자열
    assert len(out["aitimes"]) == 2


def test_require_ai_filters_by_title_with_default_keyword_judge():
    arts = [FetchedArticle("aitimes", "https://a/1", "딥시크, 추론 AI 모델 공개", "", "2026-10-17T00:00:00+00:00"),
            FetchedArticle("aitimes", "https://a/2", "여수세계섬박람회 현장 점검", "", "2026-10-17T00:00:00+00:00")]
    out = H.collect_headlines([_src()], window_hours=24, fetch_fn=lambda s, w: arts)
    assert [h.url for h in out["aitimes"]] == ["https://a/1"]


def test_cap_defaults_to_eight_latest_without_select():
    out = H.collect_headlines([_src()], window_hours=24, fetch_fn=lambda s, w: _arts(12),
                              relevance_fn=lambda t, x: True)
    assert [h.url for h in out["aitimes"]] == [f"https://a/{i}" for i in range(8)]


# ── 헤드라인 전용 선별자: 제목 + "이미 카드로 다룬 기사 제목"만 받고, 상한 이하로 고른다 ──
def test_headline_select_gets_titles_and_covered_titles_only():
    seen = {}

    def hsel(cands, k, covered):
        seen.update(texts=[a.raw_text for a in cands], k=k, covered=list(covered), n=len(cands))
        return [(a, "해외") for a in list(cands)[:3]]   # 상한(k) 미만도 허용 — 비AI 를 억지로 채우지 않는다

    out = H.collect_headlines([_src(require_ai=False, max_items=15, select="llm")], window_hours=24,
                              fetch_fn=lambda s, w: _arts(60), headline_select_fn=hsel,
                              covered_titles=["카드 기사 제목"])
    assert seen["texts"] and all(t == "" for t in seen["texts"])   # 본문은 판정자에 닿지 않는다
    assert seen["covered"] == ["카드 기사 제목"] and seen["k"] == 15
    assert seen["n"] == 50                                          # 후보 풀 = 피드 전체(최대 50)
    assert len(out["aitimes"]) == 3


def test_headline_select_fallback_is_keyword_titles_then_latest():
    arts = [FetchedArticle("aitimes", f"https://a/{i}", t, "", "2026-10-17T00:00:00+00:00")
            for i, t in enumerate(["이탈리아 태양광 82GW 전망", "딥시크 AI 모델 공개", "목포 도시기본계획", "엔비디아 AI 칩 출시"])]
    out = H.collect_headlines([_src(require_ai=False, max_items=15, select="llm")], window_hours=24,
                              fetch_fn=lambda s, w: arts)   # 선별자 미주입(로컬·테스트) = 결정론 폴백
    assert [h.url for h in out["aitimes"]] == ["https://a/1", "https://a/3"]   # 비AI 제목 제외, 최신순
    assert {h.group for h in out["aitimes"]} == {""}                            # 폴백은 해외/국내를 모른다 → 그룹 없음


def test_headline_group_is_carried_from_selector():
    arts = _arts(3)

    def hsel(cands, k, _covered):
        return [(cands[2], "해외"), (cands[0], "국내")]

    out = H.collect_headlines([_src(require_ai=False, max_items=15, select="llm")], window_hours=24,
                              fetch_fn=lambda s, w: arts, headline_select_fn=hsel)
    assert [(h.url, h.group) for h in out["aitimes"]] == [("https://a/2", "해외"), ("https://a/0", "국내")]


def test_headline_area_is_attached_from_area_fn_with_titles_only():
    arts = _arts(3)
    seen = {}

    def areas(titles):
        seen["titles"] = list(titles)
        return ["Applied AI", "AI Agents"]

    out = H.collect_headlines([_src(require_ai=False, max_items=2)], window_hours=24,
                              fetch_fn=lambda s, w: arts, headline_area_fn=areas)
    assert [(h.title, h.area) for h in out["aitimes"]] == [("AI 기사 0", "Applied AI"), ("AI 기사 1", "AI Agents")]
    assert seen["titles"] == ["AI 기사 0", "AI 기사 1"]                     # 분야 판정에도 제목만(고지 준수)


def test_headline_area_fn_failure_or_length_mismatch_leaves_no_area(capsys):
    def boom(_t):
        raise RuntimeError("throttled")

    for fn in (boom, lambda t: ["Applied AI"]):          # 예외 · 길이 불일치 → 분야 없음(소제목 없는 목록)
        out = H.collect_headlines([_src(require_ai=False, max_items=2)], window_hours=24,
                                  fetch_fn=lambda s, w: _arts(3), headline_area_fn=fn)
        assert [h.area for h in out["aitimes"]] == ["", ""]
    assert "WARN" in capsys.readouterr().err


def test_llm_headline_areas_maps_closed_list_in_order():
    ans = '생각...\n{"Applied AI": [2], "AI Agents": [1, 3]}'
    assert H.llm_headline_areas(["a", "b", "c"], invoke=lambda s, u: ans) == ["AI Agents", "Applied AI", "AI Agents"]


def test_llm_headline_areas_all_or_nothing(capsys):
    """한 건이라도 분야가 비거나 목록 밖 이름이면 [] — 일부만 소제목 아래 두면 마지막 묶음에 섞여 보인다."""
    assert H.llm_headline_areas(["a", "b"], invoke=lambda s, u: '{"AI Agents": [1]}') == []
    assert H.llm_headline_areas(["a", "b"], invoke=lambda s, u: '{"AI Agents": [1], "Chips": [2]}') == []
    assert H.llm_headline_areas(["a"], invoke=lambda s, u: "글쎄요") == []
    assert "WARN" in capsys.readouterr().err


def test_headline_areas_use_shared_six_area_list():
    from briefing.core.areas import AREAS
    assert H.AREAS is AREAS and len(AREAS) == 6                 # 2026-10-24 사용자 결정 — 헤드라인 칸·카드 밴드 한 어휘·한 순서
    assert "Research" not in AREAS and "Applied AI" in H._AREA_SYSTEM   # 장르 이름(Research) 제거, 정의는 공용 상수에서


def test_headline_carries_media_title_url_and_date():
    out = H.collect_headlines([_src(require_ai=False)], window_hours=24, fetch_fn=lambda s, w: _arts(1))
    h = out["aitimes"][0]
    assert (h.source_key, h.media, h.title, h.url, h.published_at) == (
        "aitimes", "AI Times", "AI 기사 0", "https://a/0", "2026-10-17T00:00:00+00:00")


def test_fetch_failure_skips_source_without_raising():
    def boom(_s, _w):
        raise TimeoutError("feed")

    assert H.collect_headlines([_src()], window_hours=24, fetch_fn=boom) == {}


def test_card_sources_are_not_collected_as_headlines():
    calls: list[str] = []
    H.collect_headlines([_src("the-decoder", headlines_only=False)], window_hours=24,
                        fetch_fn=lambda s, w: calls.append(s.key) or _arts(1))
    assert calls == []


# ── 피드 수집: 기사 페이지는 절대 요청하지 않는다 ─────────────────
def test_feed_fetch_reads_titles_without_requesting_article_pages(monkeypatch, tmp_path):
    now = datetime.now(timezone.utc)
    rss = f"""<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>t</title>
<item><title>최근 AI 기사</title><link>https://www.aitimes.com/n/1</link>
<description>본문 앞 300자</description><pubDate>{format_datetime(now - timedelta(hours=1))}</pubDate></item>
<item><title>오래된 AI 기사</title><link>https://www.aitimes.com/n/2</link>
<pubDate>{format_datetime(now - timedelta(hours=30))}</pubDate></item>
</channel></rss>"""
    feed = tmp_path / "feed.xml"
    feed.write_text(rss, encoding="utf-8")

    def no_page(*_a, **_k):
        raise AssertionError("기사 페이지 요청 금지")

    monkeypatch.setattr(S, "_http_get", no_page)
    arts = H.fetch_headline_feed(_src(url=str(feed)), 24)
    assert [a.title for a in arts] == ["최근 AI 기사"]     # 24h 창 밖은 제외
    assert arts[0].raw_text == ""                          # 피드 요약문(본문 앞 300자)도 싣지 않는다


# ── curate 는 헤드라인 소스의 본문을 가져오지 않는다 ───────────────
def test_curate_skips_headlines_only_sources(tmp_path):
    calls: list[str] = []

    def fetch(source, _w):
        calls.append(source.key)
        return [FetchedArticle(source.key, "https://x", "AI 제목", "AI 본문", "2026-10-17T00:00:00Z")]

    by_key = curate(SourceStore(str(tmp_path)), [_src(), _src("the-decoder", headlines_only=False)],
                    fetch_article_fn=fetch)
    assert calls == ["the-decoder"] and "aitimes" not in by_key


def test_feed_fetch_refuses_robots_disallowed_feed(monkeypatch):
    import feedparser

    from briefing.core.retrieval import robots
    monkeypatch.setattr(robots, "_fetch", lambda _u: "User-agent: *\nDisallow: /rss/\n")
    monkeypatch.setattr(feedparser, "parse", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("요청 금지")))
    assert H.fetch_headline_feed(_src(url="https://www.aitimes.com/rss/allArticle.xml"), 24) == []
