"""sources — CATALOG 로드/검증 + per-user 선택."""
import tempfile
from pathlib import Path

import pytest

import types

from briefing.core.retrieval.sources import (
    CATALOG,
    MAX_SOURCE_CHARS,
    Source,
    _article_links,
    _excerpt,
    _extract_article,
    _fetch_feed,
    _load_catalog,
    catalog_keys,
    fetch_set,
    resolve_sources,
)


def test_catalog_loaded_from_yaml():
    assert len(CATALOG) >= 5
    assert "aitimes" in catalog_keys() and "anthropic" in catalog_keys()
    assert "anthropic-eng" in catalog_keys()   # 공식 발표(news)와 별개의 엔지니어링 블로그
    assert "google-ai" in catalog_keys()       # The Keyword AI — Gemini 공식 발표 채널
    assert "google-dev" in catalog_keys()      # Google Developers Blog — Gemini API·에이전트 dev


def test_catalog_max_items_and_select():
    """pytorch-kr-news = 고볼륨(일 6~9건) 커뮤니티 큐레이션 → 캡 3 + LLM 선별. 나머지 소스는 기본(0="")."""
    by_key = {s.key: s for s in CATALOG}
    p = by_key["pytorch-kr-news"]
    assert p.max_items == 3 and p.select == "llm" and p.lang == "ko"
    assert by_key["aitimes"].max_items == 0 and by_key["aitimes"].select == ""   # 기존 소스 무변경


def test_catalog_window_hours_default_and_html_override():
    """html(date-only 메타데이터) 소스는 window 48h(W≥U+P) — RSS(분 단위 timestamp)는 0(=글로벌 24h)."""
    by_key = {s.key: s for s in CATALOG}
    assert by_key["aitimes"].window_hours == 0            # RSS — 현행 24h 그대로
    assert by_key["aws-kr-tech"].window_hours == 0        # RSS — 현행 24h 그대로
    for k in ("anthropic", "anthropic-eng", "claude-blog", "google-dev"):
        assert by_key[k].window_hours == 48               # late-post(오후 PT 발행) 보정


def test_resolve_sources_empty_is_all():
    assert resolve_sources([]) == list(CATALOG)


def test_resolve_sources_subset_and_unknown_dropped():
    assert [s.key for s in resolve_sources(["claude-blog", "badkey"])] == ["claude-blog"]


def test_fetch_set_union_and_empty_is_all():
    assert {s.key for s in fetch_set([["claude-blog"], ["aitimes", "claude-blog"]])} == {"claude-blog", "aitimes"}
    assert {s.key for s in fetch_set([[]])} == set(catalog_keys())  # 빈 선택 = 전체


def _yaml(text: str) -> Path:
    p = Path(tempfile.mkdtemp()) / "c.yaml"
    p.write_text(text, encoding="utf-8")
    return p


@pytest.mark.parametrize("bad", [
    "- {key: x, name: X, url: u, kind: BOGUS, lang: en}",  # 잘못된 kind
    "- {key: x, name: X, url: u, kind: rss, lang: en}\n- {key: x, name: Y, url: v, kind: rss, lang: en}",  # 중복 key
    "- {name: X, url: u, kind: rss, lang: en}",  # 필수 key 누락
    "[]",  # 빈
    "- {key: x, name: X, url: u, kind: rss, lang: en, category: C, window_hours: -1}",   # 음수 윈도우
    "- {key: x, name: X, url: u, kind: rss, lang: en, category: C, window_hours: 48h}",  # 비정수 윈도우
    "- {key: x, name: X, url: u, kind: rss, lang: en, category: C, max_items: -3}",      # 음수 캡
    "- {key: x, name: X, url: u, kind: rss, lang: en, category: C, select: rank}",       # 미지원 select
])
def test_catalog_validation_rejects(bad):
    with pytest.raises(ValueError):
        _load_catalog(_yaml(bad))


# ── 제너릭 HTML 페치 (trafilatura 오프라인 추출 = 결정론; 네트워크 없음) ──
_ARTICLE_HTML = (
    "<html><head><title>예시 기사 \\ Anthropic</title></head><body>"
    "<nav>Skip nav Research Policy Commitments</nav>"
    "<article><h1>Introducing Claude Opus 4.8</h1>"
    '<time datetime="2026-05-28">May 28, 2026</time>'
    "<p>We are upgrading Claude Opus to a new version. It builds on Opus 4.7 with improvements across benchmarks.</p>"
    "<p>It is available today for the same price and is a more effective collaborator on agentic tasks.</p>"
    # ↓ 본문을 기사 길이로 채운다 — MIN_SOURCE_CHARS 게이트(티저 컷)를 넘겨야 정상 경로가 테스트된다.
    "<p>The model shows gains on agentic coding, long-context reasoning, and tool use, and it keeps the "
    "same latency envelope as the prior version so existing deployments need no change. Developers can "
    "opt in through the same model identifier family, and evaluations covering retrieval, planning, and "
    "multi-step execution show consistent improvement over the previous generation across our internal "
    "and public benchmark suites.</p>"
    "</article></body></html>"
)


def test_extract_article_offline():
    art = _extract_article(_ARTICLE_HTML, "https://x/news/opus", "anthropic")
    assert art is not None
    assert art.title == "Introducing Claude Opus 4.8"          # trafilatura: h1/og:title (사이트 접미사 제거)
    assert "upgrading Claude Opus" in art.raw_text
    assert art.published_at.startswith("2026-05-28")            # <time datetime>
    assert len(art.raw_text) <= MAX_SOURCE_CHARS                # 넉넉한 상한(초장문만 컷)


def test_excerpt_bounds():
    assert len(_excerpt("word " * 400, 100)) <= 100             # 길면 단어경계로 cut
    assert _excerpt("short", 100) == "short"                    # 짧으면 그대로


def test_article_links_generic():
    listing = '<a href="/news/foo">F</a><a href="/news/bar?x=1#y">B</a><a href="/about">x</a><a href="/news/foo">dup</a>'
    links = _article_links(listing, "https://www.anthropic.com/news")
    assert links == ["https://www.anthropic.com/news/foo", "https://www.anthropic.com/news/bar"]  # /about 제외·dup 제거


def _src(kind="html"):
    return Source("anthropic", "Anthropic", "https://www.anthropic.com/news", kind, "en")


def test_fetch_generic_html_no_feed(monkeypatch):
    from briefing.core.retrieval import sources as s
    monkeypatch.setattr(s, "discover_feed", lambda _u: "")       # 피드 없음 → 리스팅 링크 경로
    monkeypatch.setattr(s, "_http_get", lambda u: '<a href="/news/opus">Opus</a>' if u.endswith("/news") else _ARTICLE_HTML)
    arts = s.fetch_generic_html(_src(), window_hours=0, max_items=3)
    assert len(arts) == 1 and arts[0].title == "Introducing Claude Opus 4.8"
    assert arts[0].url == "https://www.anthropic.com/news/opus"


def test_fetch_generic_html_with_feed(monkeypatch):
    from briefing.core.retrieval import sources as s
    monkeypatch.setattr(s, "discover_feed", lambda _u: "https://feed.example/rss")  # 피드 발견
    seen = {}

    def fake_feed(feed_url, key, **_kw):
        seen["url"], seen["key"] = feed_url, key
        return [s.FetchedArticle(key, "u", "t", "본문", "2026-06-27")]

    monkeypatch.setattr(s, "_fetch_feed", fake_feed)
    arts = s.fetch_generic_html(_src("auto"))
    assert seen == {"url": "https://feed.example/rss", "key": "anthropic"}  # 피드 → RSS 경로 재사용
    assert len(arts) == 1


_ARTICLE = "기사 본문. " * 120   # 기사 길이(≥MIN_SOURCE_CHARS) 합성본


def test_fetch_feed_full_text(monkeypatch):
    from briefing.core.retrieval import sources as s
    entry = {"title": "T", "link": "https://x/a", "summary": "짧은 피드 요약", "published_parsed": None}
    monkeypatch.setattr("feedparser.parse", lambda _u: types.SimpleNamespace(entries=[entry]))
    monkeypatch.setattr(s, "_http_get", lambda _u: "<html>full</html>")
    monkeypatch.setattr(s, "_extract_body", lambda _h: ("T", _ARTICLE, "2026-06-27"))
    arts = _fetch_feed("https://feed", "openai", window_hours=0)
    assert len(arts) == 1 and arts[0].raw_text == _ARTICLE   # 피드 요약 아닌 *전문*


def test_fetch_feed_falls_back_to_feed_when_it_carries_full_text(monkeypatch):
    """전문 fetch 실패 → 피드 요약 폴백. 단 폴백이 *기사 길이*일 때만(전문을 싣는 피드)."""
    from briefing.core.retrieval import sources as s
    entry = {"title": "T", "link": "https://x/a", "summary": _ARTICLE, "published_parsed": None}
    monkeypatch.setattr("feedparser.parse", lambda _u: types.SimpleNamespace(entries=[entry]))
    monkeypatch.setattr(s, "_http_get", lambda _u: "")
    arts = _fetch_feed("https://feed", "openai", window_hours=0)
    assert arts[0].raw_text.startswith("기사 본문.")


def test_fetch_feed_drops_teaser_fallback(capsys, monkeypatch):
    """★ 회귀: openai.com 이 봇 차단(403) → 전문 실패 → SEO 메타설명 144자가 동결 원문이 됐다.

    author 는 그 한 문장을 정확히 요약했고 certifier 도 정확히 통과시켰다(8/8 이 이렇게 만들어져 7장 발행).
    검증이 못 막는 실패 = 페치가 막아야 한다. 무음 금지(warn) — 소스가 통째로 죽으면 여기서만 보인다.
    """
    from briefing.core.retrieval import sources as s
    entry = {"title": "Why teens deserve access to safe AI", "link": "https://openai.com/index/x",
             "summary": "Learn how OpenAI is making ChatGPT safer for teens with age-appropriate "
                        "protections, learning tools, parental controls, and expert partnerships.",
             "published_parsed": None}
    monkeypatch.setattr("feedparser.parse", lambda _u: types.SimpleNamespace(entries=[entry]))
    monkeypatch.setattr(s, "_http_get", lambda _u: "")   # 403 → 전문 미확보
    arts = _fetch_feed("https://feed", "openai", window_hours=0)
    assert arts == []
    assert "본문 미확보" in capsys.readouterr().err     # non-silent


def test_strip_boilerplate_removes_subscription_block():
    """★ 부트플레이트의 숫자는 **본문에 없는 수치의 알리바이**가 된다.

    the-decoder 의 "AI Radar frontier report **six times a year"** 는 35/35(100%) 기사에 붙어
    매번 값 6 을 동결 원문에 넣었다 — certifier 는 동결본만 보므로 "6개 조직" 류 근거 없는
    claim 이 통과한다(적대 검증에서 실증). 동결본은 기사여야 한다.
    """
    from briefing.core.retrieval.sources import _strip_boilerplate
    body = "Google is renaming NotebookLM to Gemini Notebook. About 30 million people use the tool."
    raw = (body + "\nAI News Without the Hype – Curated by Humans\n"
           'Subscribe to THE DECODER for ad-free reading, a weekly AI newsletter, our exclusive '
           '"AI Radar" frontier report six times a year, full archive access.\nSubscribe now')
    cleaned = _strip_boilerplate(raw)
    assert cleaned == body
    assert "six times a year" not in cleaned      # 값 6 의 알리바이 제거
    assert "30 million" in cleaned                # 본문 사실은 보존


def test_strip_boilerplate_keeps_plain_article():
    """마커가 없으면 아무것도 자르지 않는다(과잉 절단 방지)."""
    from briefing.core.retrieval.sources import _strip_boilerplate
    assert _strip_boilerplate(_ARTICLE) == _ARTICLE.strip()


def test_extract_article_drops_stub(capsys):
    """HTML 경로도 같은 게이트 — 쿠키월/스켈레톤에서 부스러기만 추출된 경우."""
    from briefing.core.retrieval import sources as s
    orig = s._extract_body
    try:
        s._extract_body = lambda _h: ("T", "Enable JavaScript and cookies to continue", "")
        assert s._extract_article("<html/>", "https://x/a", "anthropic") is None
        assert "본문 미확보" in capsys.readouterr().err
        s._extract_body = lambda _h: ("T", _ARTICLE, "")
        assert s._extract_article("<html/>", "https://x/a", "anthropic") is not None
    finally:
        s._extract_body = orig
