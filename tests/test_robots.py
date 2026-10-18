"""robots — RFC 9309 robots.txt 판정 + 실행 중 검사(호스트당 1회 읽기).

왜: 2026-10-17 적법성 점검에서 the-decoder(`Disallow: */feed/`)·PyTorch KR(`Disallow: /c/*.rss`)의
피드 경로가 막혀 있는데 매일 가져가고 있었다. 1회성 vetting 은 `urllib.robotparser` 가 와일드카드를
무시해 "허용"으로 오판했다 → 판정은 RFC 9309 로, 지키는 일은 코드가 매 요청마다.
"""
from briefing.core.retrieval import robots

_DECODER = """# Hello, Robot.
User-agent: *
Disallow: /wp-admin/
Disallow: */embed/
Disallow: */feed/
"""

_DISCOURSE = """User-agent: mauibot
Disallow: /

User-agent: *
Disallow: /admin/
Disallow: /t/*/*.rss
Disallow: /c/*.rss

User-agent: Googlebot
Disallow: /admin/
"""


# ── 판정(순수) ──────────────────────────────────────────────
def test_wildcard_rules_block_feed_paths_that_robotparser_missed():
    assert not robots.is_allowed(_DECODER, "https://the-decoder.com/feed/")
    assert not robots.is_allowed(_DISCOURSE, "https://discuss.pytorch.kr/c/news/14.rss")
    assert robots.is_allowed(_DECODER, "https://the-decoder.com/some-article/")
    assert robots.is_allowed(_DISCOURSE, "https://discuss.pytorch.kr/c/news/14")
    assert robots.is_allowed(_DISCOURSE, "https://discuss.pytorch.kr/t/some-topic/12204")


def test_end_anchor_and_longest_match_with_allow_winning_ties():
    text = "User-agent: *\nDisallow: /*.pdf$\nDisallow: /private/\nAllow: /private/ok\nAllow: /x\nDisallow: /x\n"
    assert not robots.is_allowed(text, "https://h/a/file.pdf")
    assert robots.is_allowed(text, "https://h/a/file.pdf?v=1")        # $ = 경로 끝 고정
    assert not robots.is_allowed(text, "https://h/private/secret")
    assert robots.is_allowed(text, "https://h/private/ok/page")       # 더 긴 규칙(Allow)이 이긴다
    assert robots.is_allowed(text, "https://h/x")                     # 같은 길이면 Allow


def test_specific_group_overrides_star_and_empty_disallow_allows_all():
    text = "User-agent: *\nDisallow: /\n\nUser-agent: trafilatura\nDisallow:\n"
    assert robots.is_allowed(text, "https://h/a", token="trafilatura")   # 우리 이름의 그룹이 * 보다 우선
    assert not robots.is_allowed(text, "https://h/a", token="feedparser")


def test_consecutive_user_agent_lines_share_one_group():
    text = "User-agent: a\nUser-agent: *\nDisallow: /blocked\n"
    assert not robots.is_allowed(text, "https://h/blocked")


def test_query_string_is_part_of_the_matched_path():
    text = "User-agent: *\nDisallow: /*?*api_key*\n"
    assert not robots.is_allowed(text, "https://h/x?api_key=1")
    assert robots.is_allowed(text, "https://h/x")


# ── 실행 중 검사(읽기 실패 의미 + 캐시) ─────────────────────────
def test_allowed_reads_robots_once_per_host(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(robots, "_fetch", lambda u: calls.append(u) or _DECODER)
    assert not robots.allowed("https://the-decoder.com/feed/")
    assert robots.allowed("https://the-decoder.com/a-story/")
    assert calls == ["https://the-decoder.com/robots.txt"]


def test_missing_robots_file_allows_everything(monkeypatch):
    monkeypatch.setattr(robots, "_fetch", lambda u: "")          # 4xx = 파일 없음 → 전부 허용(RFC 9309 §2.3.1.3)
    assert robots.allowed("https://h/anything")


def test_unreachable_robots_skips_the_host(monkeypatch, capsys):
    monkeypatch.setattr(robots, "_fetch", lambda u: None)        # 5xx·시간초과 = 확인 불가 → 전부 금지(§2.3.1.4)
    assert not robots.allowed("https://h/a")
    assert not robots.allowed("https://h/b")
    assert capsys.readouterr().err.count("[WARN robots]") == 1     # 호스트당 경고 1번(링크마다 도배하지 않는다)


def test_non_http_urls_are_not_checked(monkeypatch):
    monkeypatch.setattr(robots, "_fetch", lambda u: (_ for _ in ()).throw(AssertionError("fetch 금지")))
    assert robots.allowed("/tmp/feed.xml")                          # 로컬 파일(테스트 픽스처)


def test_fetch_maps_status_codes(monkeypatch):
    from types import SimpleNamespace

    from trafilatura import downloads
    responses = {
        "https://ok/robots.txt": SimpleNamespace(status=200, data=b"User-agent: *\nDisallow: /x\n"),
        "https://gone/robots.txt": SimpleNamespace(status=404, data=b"<html>not found</html>"),
        "https://busy/robots.txt": SimpleNamespace(status=429, data=b""),
    }
    monkeypatch.setattr(downloads, "fetch_response", lambda u, **_k: responses.get(u))
    assert robots._fetch_live("https://ok/robots.txt") == "User-agent: *\nDisallow: /x\n"
    assert robots._fetch_live("https://gone/robots.txt") == ""        # 4xx → 전부 허용
    assert robots._fetch_live("https://busy/robots.txt") is None      # 429 → 확인 불가
    assert robots._fetch_live("https://down/robots.txt") is None      # 응답 없음(5xx·네트워크) → 확인 불가
