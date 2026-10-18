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
    """pytorch-kr-news = 커뮤니티 큐레이션(평일 평균 4.7건, 2026-10-18 실측) → 캡 5 + LLM 선별.
    the-decoder = 일 5~6건 → 기본 캡 5 + LLM 선별(최신순이면 가장 이른 글이 잘린다). 나머지 소스는 기본(0="")."""
    by_key = {s.key: s for s in CATALOG}
    p = by_key["pytorch-kr-news"]
    assert p.max_items == 5 and p.select == "llm" and p.lang == "ko"
    assert by_key["the-decoder"].max_items == 0 and by_key["the-decoder"].select == "llm"
    assert by_key["aws-ml"].max_items == 0 and by_key["aws-ml"].select == ""   # 기존 소스 무변경


def test_catalog_independent_voices_and_english_category_names():
    """섹션 값 = 바뀌지 않는 영문 이름(한국어판·영어판 공통 키 — 한국어 표시 이름은 두 언어판 때 표로 붙인다).
    개인 이름으로 쓰는 블로그·뉴스레터 = Independent Voices, 공식성 순서상 Google 뒤·Community(맨 끝) 앞."""
    by_key = {s.key: s for s in CATALOG}
    sw = by_key["simon-willison"]
    assert (sw.kind, sw.url, sw.lang) == ("rss", "https://simonwillison.net/atom/entries/", "en")
    assert sw.category == "Independent Voices" and sw.require_ai   # Python 등 비AI 글이 섞인다
    assert by_key["the-decoder"].category == "News & Media"
    assert by_key["pytorch-kr-news"].category == "Community"
    order = list(dict.fromkeys(s.category for s in CATALOG))      # 섹션 순서 = 첫 등장 순서
    assert all(c.isascii() for c in order)
    assert order.index("Google") < order.index("Independent Voices") < order.index("Community") == len(order) - 1


def test_catalog_anthropic_research_and_hf_blog():
    """2026-10-18 리뷰 편입. 둘 다 날짜만 있는 글이 있어 48h 창 — 상한을 창 안 최대 글 수보다 크게 잡아 Haiku 선별이
    사실상 안 돌게 한다(선별이 발송 기록 대조보다 먼저라 전날 보낸 글을 고르면 새 글이 밀려나는 문제를 비켜 감)."""
    by_key = {s.key: s for s in CATALOG}
    ar = by_key["anthropic-research"]
    assert (ar.kind, ar.url, ar.category) == ("html", "https://www.anthropic.com/research", "Anthropic")
    assert (ar.window_hours, ar.max_items, ar.select) == (48, 10, "llm")
    hf = by_key["hf-blog"]
    assert (hf.kind, hf.url, hf.category) == ("rss", "https://huggingface.co/blog/feed.xml", "Engineering Blogs")
    assert (hf.window_hours, hf.max_items, hf.select) == (48, 6, "llm")
    order = list(dict.fromkeys(s.category for s in CATALOG))
    assert order.index("Google") < order.index("Engineering Blogs") < order.index("Independent Voices")
    assert [s.category for s in CATALOG].count("Anthropic") == 5      # 같은 발행처는 한 블록(섹션이 둘로 갈리지 않게)
    anth = [i for i, s in enumerate(CATALOG) if s.category == "Anthropic"]
    assert anth == list(range(anth[0], anth[0] + 5))


def test_catalog_meta_research_and_gcloud_ai():
    """2026-10-18 리뷰 편입 2차 — Meta 원 발표처(AI Labs 묶음: 소스 1개라 자기 섹션 대신) · Google Cloud AI & ML(Google 섹션)."""
    by_key = {s.key: s for s in CATALOG}
    mr = by_key["meta-research"]
    assert (mr.kind, mr.url, mr.category) == ("html", "https://research.meta.ai/blog", "AI Labs")
    assert (mr.window_hours, mr.max_items, mr.select) == (48, 6, "llm")   # 날짜만 → 48h, 선별 회피
    gc = by_key["gcloud-ai"]
    assert (gc.kind, gc.category, gc.max_items, gc.select) == ("rss", "Google", 5, "llm")
    assert gc.homepage == "https://cloud.google.com/blog/products/ai-machine-learning"   # 피드 호스트는 사람용이 아님
    order = list(dict.fromkeys(s.category for s in CATALOG))
    assert order.index("Google") < order.index("AI Labs") < order.index("Engineering Blogs")
    goog = [i for i, s in enumerate(CATALOG) if s.category == "Google"]
    assert len(goog) == 5 and goog == list(range(goog[0], goog[0] + 5))   # Google 은 한 블록


def test_catalog_section_order_news_first():
    """섹션 순서 = 메일 밴드·웹 UI 공통(catalog 첫 등장 순서). 2026-10-18 사용자 결정: News & Media 먼저(메일은 AI Times
    헤드라인 칸 → 오늘의 핵심 3 → The Decoder 로 업계 흐름부터) → AWS → 원 발표처 → 2차(기술 블로그·개인 필진) → 커뮤니티(맨 끝)."""
    order = list(dict.fromkeys(s.category for s in CATALOG))
    assert order == ["News & Media", "Amazon (AWS)", "Anthropic", "Google", "AI Labs",
                     "Engineering Blogs", "Independent Voices", "Community"]


def test_catalog_window_hours_default_and_html_override():
    """html(date-only 메타데이터) 소스는 window 48h(W≥U+P) — RSS(분 단위 timestamp)는 0(=글로벌 24h)."""
    by_key = {s.key: s for s in CATALOG}
    assert by_key["aitimes"].window_hours == 0            # RSS — 현행 24h 그대로
    assert by_key["aws-kr-tech"].window_hours == 0        # RSS — 현행 24h 그대로
    for k in ("anthropic", "anthropic-eng", "claude-blog", "claude-dev", "google-dev"):
        assert by_key[k].window_hours == 48               # late-post(오후 PT 발행) 보정 — claude-dev 는 RSS 지만 pubDate 가 12:00 고정


def test_resolve_sources_empty_is_all():
    assert resolve_sources([]) == list(CATALOG)


def test_resolve_sources_subset_and_unknown_dropped():
    assert [s.key for s in resolve_sources(["claude-blog", "badkey"])] == ["claude-blog"]


def test_resolve_sources_warns_on_unknown_key(capsys):
    """미상 키는 드롭하되 **조용히는 아니다** — 어떤 키가 빠졌는지 warn 으로 남긴다.

    카탈로그에서 출처를 빼면 그 키를 구독 중이던 사용자는 *모르는 채로* 기사를 덜 받는다
    (2026-09-13 실측: users/gonsoo 의 `openai` 키가 발행처 재편 후 무음 드롭되고 있었다).
    드롭 자체는 유지한다(한 키 오타가 브리핑 전체를 막으면 안 됨) — 보이게만 만든다.
    """
    resolve_sources(["claude-blog", "badkey"])
    err = capsys.readouterr().err
    assert "badkey" in err
    assert "claude-blog" not in err   # 정상 키는 경고에 안 들어간다(노이즈 방지)


def test_resolve_sources_silent_when_all_keys_known(capsys):
    """정상 경로는 조용해야 한다 — 경고가 흔해지면 경고가 아니게 된다."""
    resolve_sources(["claude-blog", "aitimes"])
    assert capsys.readouterr().err == ""


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
    monkeypatch.setattr(s, "_extract_body", lambda _h: ("T", _ARTICLE, "2026-06-27", ""))
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


def test_strip_boilerplate_removes_recent_articles_list():
    """simonwillison.net 본문 끝 "More recent articles" 목록(2026-10-18 실측 15건 중 11건) — 다른 글의 제목·날짜
    (값 3.15·5.5 등)가 동결본에 섞이면 본문에 없는 수치의 알리바이가 된다(the-decoder 구독 안내와 같은 계열)."""
    from briefing.core.retrieval.sources import _strip_boilerplate
    body = "Here's a product feature the world is going to need: default hard budget caps."
    raw = (body + "\nMore recent articles\n- Hello Python 3.15, goodbye 3.10 - 12th October 2026\n"
           "- Claude Haiku 5.5 - 7th October 2026")
    assert _strip_boilerplate(raw) == body


def test_extract_article_drops_stub(capsys):
    """HTML 경로도 같은 게이트 — 쿠키월/스켈레톤에서 부스러기만 추출된 경우."""
    from briefing.core.retrieval import sources as s
    orig = s._extract_body
    try:
        s._extract_body = lambda _h: ("T", "Enable JavaScript and cookies to continue", "", "")
        assert s._extract_article("<html/>", "https://x/a", "anthropic") is None
        assert "본문 미확보" in capsys.readouterr().err
        s._extract_body = lambda _h: ("T", _ARTICLE, "", "")
        assert s._extract_article("<html/>", "https://x/a", "anthropic") is not None
    finally:
        s._extract_body = orig


# ── canonical 호스트 검사 — 블로그 리스팅의 *문서 페이지*를 새 글로 오인하지 않기(2026-10 감사: Best practices 28장) ──


def test_is_offsite_rules():
    from briefing.core.retrieval.sources import _is_offsite
    listing = "https://www.anthropic.com/engineering"
    assert _is_offsite("https://code.claude.com/docs/en/best-practices", listing) is True   # 실제 사례
    assert _is_offsite("https://www.anthropic.com/engineering/x", listing) is False         # 같은 호스트
    assert _is_offsite("https://anthropic.com/engineering/x", listing) is False             # www 무시
    assert _is_offsite("", listing) is False                                                # canonical 없음 → 통과
    assert _is_offsite("/engineering/x", listing) is False                                  # 상대경로 → 판단 불가 → 통과
    assert _is_offsite("https://x.com/a", "https://blog.x.com/") is False                   # 서브도메인 관계 → 통과
    assert _is_offsite("https://blog.x.com/a", "https://x.com/blog") is False


def test_extract_body_reads_canonical_link():
    html = _ARTICLE_HTML.replace(
        "<head>", '<head><link rel="canonical" href="https://code.claude.com/docs/en/best-practices">')
    from briefing.core.retrieval.sources import _extract_body
    assert _extract_body(html)[3] == "https://code.claude.com/docs/en/best-practices"
    assert _extract_body(_ARTICLE_HTML)[3] == ""                                            # canonical 없음 → ""


def test_extract_article_drops_offsite_canonical(capsys):
    from briefing.core.retrieval import sources as s
    orig = s._extract_body
    try:
        s._extract_body = lambda _h: ("Best practices", _ARTICLE, "2026-10-06",
                                      "https://code.claude.com/docs/en/best-practices")
        assert s._extract_article("<html/>", "https://www.anthropic.com/engineering/claude-code-best-practices",
                                  "anthropic-eng", "https://www.anthropic.com/engineering") is None
        assert "다른 호스트" in capsys.readouterr().err
        assert s._extract_article("<html/>", "https://x/a", "k") is not None   # listing_url 없으면 검사 안 함
    finally:
        s._extract_body = orig


def test_fetch_generic_html_skips_offsite_page(monkeypatch):
    """리스팅 링크가 다른 호스트의 문서로 넘어가면(canonical) 그 링크만 빠진다 — 정상 글은 그대로."""
    from briefing.core.retrieval import sources as s
    docs_page = _ARTICLE_HTML.replace(
        "<head>", '<head><link rel="canonical" href="https://code.claude.com/docs/en/best-practices">')
    pages = {"/news": '<a href="/news/opus">O</a><a href="/news/claude-code-best-practices">B</a>',
             "/news/opus": _ARTICLE_HTML, "/news/claude-code-best-practices": docs_page}
    monkeypatch.setattr(s, "discover_feed", lambda _u: "")
    monkeypatch.setattr(s, "_http_get", lambda u: pages[u.replace("https://www.anthropic.com", "")])
    arts = s.fetch_generic_html(_src(), window_hours=0, max_items=5)
    assert [a.url for a in arts] == ["https://www.anthropic.com/news/opus"]


# ── 페치 시간 상한 ── 한 소스가 멈춰도 브리핑 전체가 정지하지 않아야 한다 ──
# 배경(2026-08-09 미발송): trafilatura 는 pycurl 없으면 urllib3 경로 — `create_pool(timeout=N)` 은
# urllib3 에서 Timeout(connect=N, read=N) 이라 **읽기마다 초기화**된다(총 시간 상한 없음).
# 파이프라인은 소스를 직렬 처리하므로 한 URL 이 막히면 전체가 무출력으로 멈춘다.

def test_http_get_hard_deadline_unblocks_stalled_fetch(capsys):
    """멈춘 fetch 는 데드라인에서 포기하고 ""(+warn) — 호출자는 다음 링크로 넘어간다."""
    import time as _t

    import trafilatura

    from briefing.core.retrieval import sources as s
    orig = trafilatura.fetch_url
    try:
        trafilatura.fetch_url = lambda *a, **k: (_t.sleep(30), "never")[1]   # 응답 없는 서버
        t0 = _t.monotonic()
        out = s._http_get("https://stalled.example/a", timeout_s=0.3)
        elapsed = _t.monotonic() - t0
    finally:
        trafilatura.fetch_url = orig
    assert out == ""
    assert elapsed < 5.0, f"데드라인을 무시하고 {elapsed:.1f}s 대기"
    assert "fetch timeout" in capsys.readouterr().err          # non-silent


def test_fetch_generic_html_abandons_source_when_budget_exhausted(capsys):
    """소스 예산 초과 시 남은 링크를 포기 — 링크 수 x 데드라인만큼 끌지 않는다."""
    import time as _t

    from briefing.core.retrieval import sources as s
    listing = "".join(f'<a href="/news/a{i}">A</a>' for i in range(30))
    seen: list[str] = []

    def slow_get(url):
        seen.append(url)
        if url.endswith("/news"):
            return listing
        _t.sleep(0.05)
        return "<html/>"            # 추출 실패 → out 안 참 → 루프는 계속 돌려 한다

    orig = s._http_get
    try:
        s._http_get = slow_get
        s.discover_feed_orig = s.discover_feed
        s.discover_feed = lambda _u: ""
        arts = s.fetch_generic_html(_src(), window_hours=0, max_items=5, budget_s=0.2)
    finally:
        s._http_get = orig
        s.discover_feed = s.discover_feed_orig
    assert arts == []
    assert len(seen) < 31, f"예산을 무시하고 링크 {len(seen)}건 전부 시도"
    assert "fetch budget" in capsys.readouterr().err           # non-silent


def test_fetch_feed_hard_deadline_on_feed_download(capsys):
    """RSS 다운로드(feedparser.parse) 자체도 상한 — 여기도 막히면 소스가 통째로 정지한다."""
    import time as _t

    import feedparser

    from briefing.core.retrieval import sources as s
    orig = feedparser.parse
    try:
        feedparser.parse = lambda *a, **k: (_t.sleep(30), None)[1]
        t0 = _t.monotonic()
        arts = s._fetch_feed("https://stalled.example/rss", "x", timeout_s=0.3)
        elapsed = _t.monotonic() - t0
    finally:
        feedparser.parse = orig
    assert arts == []
    assert elapsed < 5.0, f"데드라인을 무시하고 {elapsed:.1f}s 대기"
    assert "fetch timeout" in capsys.readouterr().err


def test_discover_feed_hard_deadline_falls_back_to_listing(capsys):
    """피드 자동발견도 상한 — 여기가 막히면 예산 검사(루프 안)에 도달조차 못 한다.

    타임아웃 = ""(미발견) → 호출자는 리스팅 크롤 경로로 폴백하므로 소스를 잃지 않는다.
    """
    import time as _t

    from trafilatura import feeds

    from briefing.core.retrieval import sources as s
    orig = feeds.find_feed_urls
    try:
        feeds.find_feed_urls = lambda *a, **k: (_t.sleep(30), ["https://f/rss"])[1]
        t0 = _t.monotonic()
        out = s.discover_feed("https://stalled.example/", timeout_s=0.3)
        elapsed = _t.monotonic() - t0
    finally:
        feeds.find_feed_urls = orig
    assert out == ""
    assert elapsed < 5.0, f"데드라인을 무시하고 {elapsed:.1f}s 대기"
    assert "fetch timeout" in capsys.readouterr().err


# ── robots 검사(2026-10-17): 막힌 경로는 요청하지 않는다 ─────────────────
def _disallow(monkeypatch, text):
    from briefing.core.retrieval import robots
    monkeypatch.setattr(robots, "_fetch", lambda _u: text)


def test_http_get_refuses_robots_disallowed_url(monkeypatch, capsys):
    import trafilatura

    from briefing.core.retrieval import sources as s
    _disallow(monkeypatch, "User-agent: *\nDisallow: */feed/\n")
    monkeypatch.setattr(trafilatura, "fetch_url", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("요청 금지")))
    assert s._http_get("https://the-decoder.com/feed/") == ""
    assert "robots" in capsys.readouterr().err                   # non-silent


def test_fetch_feed_refuses_robots_disallowed_feed(monkeypatch):
    import feedparser

    from briefing.core.retrieval import sources as s
    _disallow(monkeypatch, "User-agent: *\nDisallow: /c/*.rss\n")
    monkeypatch.setattr(feedparser, "parse", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("요청 금지")))
    assert s._fetch_feed("https://discuss.pytorch.kr/c/news/14.rss", "pytorch-kr-news") == []


def test_html_kind_goes_straight_to_listing_without_feed_discovery(monkeypatch):
    """kind: html = 리스팅 직행. 피드 자동발견(trafilatura)은 광고된 피드를 *내부에서* 직접 받아 와서
    robots 검사를 거치지 않는다 — PyTorch KR 목록 페이지는 막힌 `/c/news/14.rss` 를 광고한다."""
    from briefing.core.retrieval import sources as s
    monkeypatch.setattr(s, "discover_feed", lambda _u: (_ for _ in ()).throw(AssertionError("발견 금지")))
    monkeypatch.setattr(s, "_http_get", lambda u: '<a href="/news/opus">Opus</a>' if u.endswith("/news") else _ARTICLE_HTML)
    assert len(s.fetch_generic_html(_src("html"), window_hours=0, max_items=3)) == 1


def test_article_links_article_path_reads_single_quoted_links_outside_listing_path():
    """Discourse: 목록 `/c/news/14` 의 글은 `/t/<slug>/<id>`(목록 경로 밖) + 작은따옴표 href."""
    listing = ("<a itemprop='url' href='https://discuss.pytorch.kr/t/vllm-sglang/12212' class='title'>A</a>"
               "<a href='/t/strata/12189'>B</a><a href='/c/news/14?page=1'>next</a><a href='/u/someone'>u</a>"
               "<a href='https://discuss.pytorch.kr/t/vllm-sglang/12212'>dup</a>")
    links = _article_links(listing, "https://discuss.pytorch.kr/c/news/14", article_path="/t/")
    assert links == ["https://discuss.pytorch.kr/t/vllm-sglang/12212", "https://discuss.pytorch.kr/t/strata/12189"]


def test_fetch_generic_html_passes_article_path(monkeypatch):
    from briefing.core.retrieval import sources as s
    src = Source("pytorch-kr-news", "P", "https://discuss.pytorch.kr/c/news/14", "html", "ko", article_path="/t/")
    monkeypatch.setattr(s, "_http_get",
                        lambda u: "<a href='/t/opus/1'>x</a>" if u.endswith("/14") else _ARTICLE_HTML)
    arts = s.fetch_generic_html(src, window_hours=0, max_items=3)
    assert [a.url for a in arts] == ["https://discuss.pytorch.kr/t/opus/1"]


# ── kind: sitemap — 사이트가 robots.txt 에 선언한 기계용 목록 ─────────────
_NEWS_SITEMAP = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:news="http://www.google.com/schemas/sitemap-news/0.9">
<url><loc>https://the-decoder.com/older/</loc><news:news><news:publication_date>{old}</news:publication_date>
<news:title><![CDATA[Older]]></news:title></news:news></url>
<url><loc>https://the-decoder.com/newest/</loc><news:news><news:publication_date>{new}</news:publication_date>
<news:title><![CDATA[Newest]]></news:title></news:news></url>
<url><loc>https://the-decoder.com/plain/</loc><lastmod>{mid}</lastmod></url>
</urlset>"""


def _iso(hours_ago):
    from datetime import datetime, timedelta, timezone
    return (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat(timespec="seconds")


def test_sitemap_entries_newest_first_with_news_date_or_lastmod():
    from briefing.core.retrieval.sources import _sitemap_entries
    xml = _NEWS_SITEMAP.format(old=_iso(30), new=_iso(1), mid=_iso(5))
    assert [u for u, _d in _sitemap_entries(xml)] == [
        "https://the-decoder.com/newest/", "https://the-decoder.com/plain/", "https://the-decoder.com/older/"]


def test_fetch_sitemap_keeps_window_and_uses_sitemap_timestamp(monkeypatch):
    """페이지 추출 날짜는 날짜만(2026-05-28)이라 부정확 → 사이트맵의 정확한 발행 시각을 쓴다."""
    from briefing.core.retrieval import sources as s
    new = _iso(1)
    xml = _NEWS_SITEMAP.format(old=_iso(30), new=new, mid=_iso(5))
    fetched: list[str] = []

    def get(u):
        fetched.append(u)
        return xml if u.endswith(".xml") else _ARTICLE_HTML

    monkeypatch.setattr(s, "_http_get", get)
    src = Source("the-decoder", "The Decoder", "https://the-decoder.com/news-sitemap.xml", "sitemap", "en")
    arts = s.fetch_sitemap(src, window_hours=24, max_items=5)
    assert [a.url for a in arts] == ["https://the-decoder.com/newest/", "https://the-decoder.com/plain/"]
    assert arts[0].published_at == new
    assert "https://the-decoder.com/older/" not in fetched        # 창 밖 글은 페이지를 열지도 않는다


def test_fetch_sitemap_respects_cap(monkeypatch):
    from briefing.core.retrieval import sources as s
    xml = _NEWS_SITEMAP.format(old=_iso(3), new=_iso(1), mid=_iso(2))
    monkeypatch.setattr(s, "_http_get", lambda u: xml if u.endswith(".xml") else _ARTICLE_HTML)
    src = Source("the-decoder", "D", "https://the-decoder.com/news-sitemap.xml", "sitemap", "en")
    assert len(s.fetch_sitemap(src, window_hours=24, max_items=2)) == 2


def test_fetch_sitemap_rejects_index_and_failed_download(monkeypatch):
    from briefing.core.retrieval import sources as s
    src = Source("x", "X", "https://h/sitemap.xml", "sitemap", "en")
    monkeypatch.setattr(s, "_http_get", lambda u: '<sitemapindex><sitemap><loc>https://h/s1.xml</loc></sitemap></sitemapindex>')
    with pytest.raises(RuntimeError, match="sitemapindex"):
        s.fetch_sitemap(src)
    monkeypatch.setattr(s, "_http_get", lambda u: "")
    with pytest.raises(RuntimeError, match="sitemap"):
        s.fetch_sitemap(src)


# ── 카탈로그: 두 소스를 robots 가 허용한 경로로 ──────────────────────
def test_catalog_moves_blocked_feeds_to_allowed_paths():
    by_key = {s.key: s for s in CATALOG}
    d = by_key["the-decoder"]
    assert (d.kind, d.url) == ("sitemap", "https://the-decoder.com/news-sitemap.xml")
    p = by_key["pytorch-kr-news"]
    assert (p.kind, p.url, p.article_path) == ("html", "https://discuss.pytorch.kr/c/news/14", "/t/")
    assert p.window_hours == 48                                     # 글 페이지 날짜가 날짜만 → late-post 보정


@pytest.mark.parametrize("bad", [
    "- {key: x, name: X, url: u, kind: html, lang: en, category: C, article_path: t/}",   # / 로 시작해야
    "- {key: x, name: X, url: u, kind: html, lang: en, category: C, article_path: 3}",    # 문자열이어야
])
def test_catalog_rejects_bad_article_path(bad):
    with pytest.raises(ValueError, match="article_path"):
        _load_catalog(_yaml(bad))
