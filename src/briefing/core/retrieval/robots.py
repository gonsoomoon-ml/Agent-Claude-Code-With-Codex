"""robots — robots.txt 판정(RFC 9309) + 실행 중 검사. 막힌 경로는 요청하지 않는다.

왜 필요한가(2026-10-17 적법성 점검): the-decoder(`Disallow: */feed/`)·PyTorch KR(`Disallow: /c/*.rss`)의
피드 경로가 막혀 있었는데 매일 가져가고 있었다. 1회성 vetting 은 `urllib.robotparser` 가 와일드카드
(`*`·`$`)를 무시해 "허용"으로 오판했다. → 판정은 RFC 9309 로 직접 하고, 지키는 일은 사람의 점검이
아니라 코드가 매 요청 전에 한다(`sources._http_get`·`_fetch_feed`·`headlines.fetch_headline_feed`).

RFC 9309 요점(여기서 구현한 것):
  - 그룹 선택: 우리 product token 을 이름으로 가진 그룹, 없으면 `*` 그룹. 연속된 User-agent 줄은 한 그룹.
  - 규칙 매칭: 경로+쿼리에 대해 `*`(아무 문자열)·`$`(끝 고정). **가장 긴 규칙**이 이기고, 길이가 같으면 Allow.
  - 읽기 실패: 4xx = 파일 없음 → 전부 허용 · 5xx·시간초과·네트워크 오류 = 확인 불가 → 전부 금지.
"""
from __future__ import annotations

import re
import time
from urllib.parse import urlsplit

from .. import _debug

DEFAULT_TOKEN = "trafilatura"   # 본문·목록 요청의 User-Agent(trafilatura 기본 UA) product token
FEED_TOKEN = "feedparser"       # 피드 다운로드(feedparser.parse)의 UA product token
_TTL_S = 3600                   # 호스트별 robots.txt 캐시 수명 — 한 번의 발송 run(~10분)엔 1회 읽기

_CACHE: dict[str, tuple[float, str | None]] = {}   # robots.txt URL → (읽은 시각, 본문 | None=확인 불가)


def _groups(text: str) -> list[tuple[list[str], list[tuple[str, str]]]]:
    """robots.txt → [(user-agent 토큰들(소문자), [(allow|disallow, 경로 패턴)])]."""
    groups: list[tuple[list[str], list[tuple[str, str]]]] = []
    in_agents = False                     # 직전 줄이 User-agent 였나 — 연속된 User-agent 는 같은 그룹
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if ":" not in line:
            continue
        key, value = (x.strip() for x in line.split(":", 1))
        key = key.lower()
        if key == "user-agent":
            if not in_agents:
                groups.append(([], []))
            groups[-1][0].append(value.lower())
            in_agents = True
        elif key in ("allow", "disallow"):
            in_agents = False
            if groups:
                groups[-1][1].append((key, value))
        elif key != "sitemap":            # sitemap 은 그룹과 무관한 줄 — 그룹을 끊지 않는다
            in_agents = False
    return groups


def _pattern(path: str) -> re.Pattern[str]:
    """규칙 경로 → 정규식. `*` = 아무 문자열, 끝의 `$` = 경로 끝 고정, 나머지는 글자 그대로."""
    anchored = path.endswith("$")
    body = path[:-1] if anchored else path
    regex = "".join(".*" if c == "*" else re.escape(c) for c in body)
    return re.compile("^" + regex + ("$" if anchored else ""))


def is_allowed(text: str, url: str, token: str = DEFAULT_TOKEN) -> bool:
    """robots.txt 본문 기준으로 url 요청이 허용되나(순수 함수)."""
    groups = _groups(text)
    chosen = [g for g in groups if token.lower() in g[0]] or [g for g in groups if "*" in g[0]]
    parts = urlsplit(url)
    target = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
    best: tuple[int, bool] | None = None   # (규칙 길이, allow?)
    for _agents, rules in chosen:
        for kind, path in rules:
            if not path:                    # 빈 Disallow = 아무것도 막지 않음
                continue
            if _pattern(path).match(target):
                cand = (len(path), kind == "allow")
                if best is None or cand > best:   # 더 긴 규칙 우선, 같은 길이면 allow(True > False)
                    best = cand
    return best is None or best[1]


def _fetch_live(robots_url: str) -> str | None:
    """robots.txt 읽기. 2xx → 본문 · 4xx(429 제외) → ""(파일 없음=전부 허용) · 그 밖 → None(확인 불가)."""
    from trafilatura import downloads   # lazy(무거운 import 회피)

    from .sources import _FETCH_TIMEOUT_S, _with_deadline   # lazy — sources 가 이 모듈을 import 한다
    resp = _with_deadline(lambda: downloads.fetch_response(robots_url), _FETCH_TIMEOUT_S, robots_url)
    if resp is None:
        return None
    status = int(getattr(resp, "status", 0) or 0)
    if 200 <= status < 300:
        return (resp.data or b"").decode("utf-8", errors="replace")
    if 400 <= status < 500 and status != 429:
        return ""
    return None


_fetch = _fetch_live   # 테스트가 바꿔 끼우는 지점(tests/conftest.py — 네트워크 0)


def allowed(url: str, token: str = DEFAULT_TOKEN) -> bool:
    """url 을 요청해도 되나. 호스트의 robots.txt 는 _TTL_S 동안 1회만 읽는다. http(s) 가 아니면(로컬 파일) True."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return True
    robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"
    now = time.time()
    hit = _CACHE.get(robots_url)
    if hit is None or now - hit[0] > _TTL_S:
        text = _fetch(robots_url)
        _CACHE[robots_url] = (now, text)
        if text is None:   # non-silent — 호스트당 1번(캐시 수명 동안 링크마다 반복하지 않는다)
            _debug.warn("robots", f"{robots_url} 확인 불가(5xx·시간초과) — 이번 실행에서 {parts.netloc} 요청 안 함")
    else:
        text = hit[1]
    if text is None:
        return False
    return is_allowed(text, url, token)
