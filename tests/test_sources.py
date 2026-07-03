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


def test_resolve_sources_empty_is_all():
    assert resolve_sources([]) == list(CATALOG)


def test_resolve_sources_subset_and_unknown_dropped():
    assert [s.key for s in resolve_sources(["openai", "badkey"])] == ["openai"]


def test_fetch_set_union_and_empty_is_all():
    assert {s.key for s in fetch_set([["openai"], ["aitimes", "openai"]])} == {"openai", "aitimes"}
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


def test_fetch_feed_full_text(monkeypatch):
    from briefing.core.retrieval import sources as s
    entry = {"title": "T", "link": "https://x/a", "summary": "짧은 피드 요약", "published_parsed": None}
    monkeypatch.setattr("feedparser.parse", lambda _u: types.SimpleNamespace(entries=[entry]))
    monkeypatch.setattr(s, "_http_get", lambda _u: "<html>full</html>")
    monkeypatch.setattr(s, "_extract_body", lambda _h: ("T", "전문 본문 긴 내용", "2026-06-27"))
    arts = _fetch_feed("https://feed", "openai", window_hours=0)
    assert len(arts) == 1 and arts[0].raw_text == "전문 본문 긴 내용"   # 피드 요약 아닌 *전문*


def test_fetch_feed_full_text_fallback(monkeypatch):
    from briefing.core.retrieval import sources as s
    entry = {"title": "T", "link": "https://x/a", "summary": "피드 요약 폴백", "published_parsed": None}
    monkeypatch.setattr("feedparser.parse", lambda _u: types.SimpleNamespace(entries=[entry]))
    monkeypatch.setattr(s, "_http_get", lambda _u: "")               # 전문 fetch 실패 → 피드 요약 폴백
    arts = _fetch_feed("https://feed", "openai", window_hours=0)
    assert arts[0].raw_text == "피드 요약 폴백"
