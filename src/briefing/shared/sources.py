"""sources — 출처 CATALOG(전역 vetted) + per-user 선택 + fabric 권위 페치.

설계:
- CATALOG = `catalog.yaml` 의 검증된 전역 출처 목록(임의 URL 금지·큐레이션). 로드 시 검증 → 잘못되면 시작 크래시.
- per-user 선택 = profile.yaml `sources: [key,...]` → resolve_sources(); 빈 선택이면 전체.
- 수집 = 모든 사용자 선택의 *합집합*만 1회 fetch+freeze(content-addressing 이 사용자 간 dedup) → per-user 필터.
- 커스텀 피드(사용자 URL 직접 추가)는 검증 필요 → v2. v1 (웹)UI = CATALOG 에서 선택.
- 출처 URL 드리프트 가정: last-verified + 폴백 (스펙 리뷰가 OpenAI/DeepMind 변경 적발).
"""
from __future__ import annotations

import calendar
import html as _html
import re
import time
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import yaml


@dataclass(frozen=True)
class Source:
    key: str
    name: str
    url: str
    kind: str              # "rss" | "html" | "auto" (auto = 피드 자동발견 후 폴백)
    lang: str              # "en" | "ko"
    fragile: bool = False  # True = *진짜 차단*(Cloudflare challenge/JS-only) — v1 미구현, 현 catalog 엔 없음


_KINDS = frozenset({"rss", "html", "auto"})
_LANGS = frozenset({"en", "ko"})
_REQUIRED = ("key", "name", "url", "kind", "lang")
_CATALOG_PATH = Path(__file__).parent / "catalog.yaml"


def _load_catalog(path: Path = _CATALOG_PATH) -> tuple[Source, ...]:
    """catalog.yaml 로드 + 검증 → CATALOG. 잘못되면 *시작 시 크래시*(silent failure 금지)."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list) or not raw:
        raise ValueError(f"catalog.yaml: 비어있거나 list 아님 ({path})")
    out: list[Source] = []
    seen: set[str] = set()
    for i, e in enumerate(raw):
        if not isinstance(e, dict):
            raise ValueError(f"catalog[{i}]: 항목이 dict 아님")
        for f in _REQUIRED:
            if not e.get(f):
                raise ValueError(f"catalog[{i}]: 필수 필드 '{f}' 누락/빈값")
        if e["kind"] not in _KINDS:
            raise ValueError(f"catalog[{i}] '{e['key']}': kind 는 {set(_KINDS)} 중 하나 (got {e['kind']!r})")
        if e["lang"] not in _LANGS:
            raise ValueError(f"catalog[{i}] '{e['key']}': lang 는 {set(_LANGS)} 중 하나 (got {e['lang']!r})")
        if e["key"] in seen:
            raise ValueError(f"catalog[{i}]: 중복 key '{e['key']}'")
        seen.add(e["key"])
        out.append(
            Source(
                key=e["key"],
                name=e["name"],
                url=e["url"],
                kind=e["kind"],
                lang=e["lang"],
                fragile=bool(e.get("fragile", False)),
            )
        )
    return tuple(out)


# 전역 vetted CATALOG — catalog.yaml 에서 로드(import 시 1회, 검증). UI 는 이 목록에서 선택.
CATALOG: tuple[Source, ...] = _load_catalog()
_BY_KEY: dict[str, Source] = {s.key: s for s in CATALOG}


def catalog_keys() -> tuple[str, ...]:
    """UI/API 검증용 — 선택 가능한 출처 키."""
    return tuple(_BY_KEY)


def resolve_sources(selected: Sequence[str]) -> list[Source]:
    """per-user 선택 키 → CATALOG 엔트리(catalog 순서·결정론). 빈 선택이면 전체(기본)."""
    if not selected:
        return list(CATALOG)
    sel = set(selected)
    return [s for s in CATALOG if s.key in sel]


def fetch_set(selections: Iterable[Sequence[str]]) -> list[Source]:
    """모든 사용자 선택의 합집합 → 공유 수집 대상(중복 fetch 방지). 빈 선택은 전체로 간주."""
    keys: set[str] = set()
    for sel in selections:
        keys.update(sel if sel else catalog_keys())
    return [s for s in CATALOG if s.key in keys]


@dataclass(frozen=True)
class FetchedArticle:
    source_key: str
    url: str
    title: str
    raw_text: str
    published_at: str      # ISO8601 (24h 윈도우 필터용)


_TAG_RE = re.compile(r"<[^>]+>")


def _clean_text(raw_html: str) -> str:
    """RSS summary/content(HTML 가능) → 평문. 태그 제거 + 엔티티 해제 + 공백 정리."""
    text = _html.unescape(_TAG_RE.sub(" ", raw_html or ""))
    return re.sub(r"\s+", " ", text).strip()


def _fetch_feed(
    feed_url: str, source_key: str, *, window_hours: int = 24, max_items: int = 5
) -> list[FetchedArticle]:
    """RSS/Atom 피드 URL → FetchedArticle 목록 (feedparser). fetch_clean_rss·제너릭 피드발견 공용.

    published_parsed(UTC struct_time)는 `calendar.timegm` 으로 epoch 화(local 해석 방지). title·본문 모두 있어야 채택.
    """
    import feedparser  # lazy — feedparser 미설치 환경에서도 sources 모듈 import 가능

    feed = feedparser.parse(feed_url)
    now = time.time()
    out: list[FetchedArticle] = []
    for entry in feed.entries:
        if len(out) >= max_items:
            break
        parsed = entry.get("published_parsed") or entry.get("updated_parsed")
        published = ""
        if parsed:
            ts = calendar.timegm(parsed)  # struct_time(UTC) → epoch
            if window_hours and (now - ts) / 3600.0 > window_hours:
                continue
            published = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
        title = (entry.get("title") or "").strip()
        link = (entry.get("link") or "").strip()
        raw = entry.get("summary") or ""
        if not raw and entry.get("content"):
            raw = entry["content"][0].get("value", "")
        text = _clean_text(raw)
        if not (title and text):
            continue
        out.append(FetchedArticle(source_key, link, title, text, published))
    return out


def fetch_clean_rss(source: Source, *, window_hours: int = 24, max_items: int = 5) -> list[FetchedArticle]:
    """클린 RSS 페치 — _fetch_feed(source.url) 위임. window_hours 이내·최신 max_items cap."""
    return _fetch_feed(source.url, source.key, window_hours=window_hours, max_items=max_items)


# ── 제너릭 HTML/auto 출처 페치 (사이트별 코드 0; trafilatura 범용 추출 + 피드 자동발견) ──
EXCERPT_CHARS = 800  # ★ 저작권 자세: 전문 아닌 bounded excerpt 만 동결(검증엔 충분)


def discover_feed(url: str) -> str:
    """사이트 URL → RSS/Atom 피드 URL 자동발견(없으면 ""). UI 가 URL 만 받아도 RSS 인식(kind:auto 토대)."""
    from trafilatura import feeds  # lazy(무거운 import 회피)
    found = feeds.find_feed_urls(url)
    return found[0] if found else ""


def _http_get(url: str) -> str:
    """trafilatura.fetch_url — UA·재시도 처리된 평문 GET(접근통제 우회 없음). 실패 시 ""."""
    import trafilatura
    return trafilatura.fetch_url(url) or ""


def _excerpt(text: str, limit: int = EXCERPT_CHARS) -> str:
    """단어 경계에서 limit 자로 자른 발췌(전문 저장 회피)."""
    if len(text) <= limit:
        return text
    cut = text[:limit]
    sp = cut.rfind(" ")
    return (cut[:sp] if sp > limit * 0.6 else cut).strip()


def _article_links(listing_html: str, listing_url: str) -> list[str]:
    """리스팅에서 기사 링크만(listing path 한 단계 아래 `{path}/{slug}`) — 제너릭 휴리스틱, 사이트별 코드 아님."""
    base = urlparse(listing_url)
    path = base.path.rstrip("/")
    out: list[str] = []
    seen: set[str] = set()
    for href in re.findall(r'href="([^"]+)"', listing_html):
        clean = href.split("#")[0].split("?")[0]
        p = urlparse(urljoin(f"{base.scheme}://{base.netloc}", clean)).path.rstrip("/")
        tail = p[len(path) + 1:]
        if p.startswith(path + "/") and tail and "/" not in tail:
            absu = f"{base.scheme}://{base.netloc}{p}"
            if absu not in seen:
                seen.add(absu)
                out.append(absu)
    return out


def _extract_article(html_text: str, url: str, source_key: str) -> FetchedArticle | None:
    """trafilatura 로 임의 기사 HTML → title·본문·date. bounded excerpt. 추출 실패 시 None."""
    import trafilatura
    doc = trafilatura.bare_extraction(html_text, with_metadata=True)
    if doc is None:
        return None
    title = (getattr(doc, "title", "") or "").strip()
    text = _excerpt((getattr(doc, "text", "") or "").strip())
    published = (getattr(doc, "date", "") or "").strip()
    if not (title and text):
        return None
    return FetchedArticle(source_key, url, title, text, published)


def _is_stale(published: str, window_hours: int) -> bool:
    """published(ISO/날짜) 가 window 밖이면 True. 날짜 모르면(빈값) False(통과)."""
    if not (published and window_hours):
        return False
    try:
        ts = datetime.fromisoformat(published.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return False
    return (time.time() - ts) / 3600.0 > window_hours


def fetch_generic_html(source: Source, *, window_hours: int = 24, max_items: int = 5) -> list[FetchedArticle]:
    """제너릭 HTML/auto 출처 페치 — 피드 발견 시 RSS 경로 재사용, 없으면 리스팅 링크 + trafilatura 본문 추출.

    ★ 매체별 코드 0(UI 가 URL 만 받아도 동작). 권위 페치=fabric 소유. bounded excerpt 만(법적 자세).
    listing fetch 실패는 예외(curate 가 skip+warn); 개별 기사 실패는 그 기사만 skip.
    """
    feed = discover_feed(source.url)
    if feed:
        return _fetch_feed(feed, source.key, window_hours=window_hours, max_items=max_items)
    listing = _http_get(source.url)
    if not listing:
        raise RuntimeError(f"html listing fetch 실패: {source.url}")
    out: list[FetchedArticle] = []
    for url in _article_links(listing, source.url):
        if len(out) >= max_items:
            break
        page = _http_get(url)
        if not page:
            continue
        art = _extract_article(page, url, source.key)
        if art and not _is_stale(art.published_at, window_hours):
            out.append(art)
    return out


def fetch_fragile(source: Source) -> list[FetchedArticle]:
    """*진짜 차단*(Cloudflare challenge/JS-only) 출처 — v1 미구현(접근통제 우회는 법적 red line이라 보류).

    평문으로 잡히는 HTML 은 fetch_generic_html(trafilatura)로 처리. 현 catalog 엔 fragile 출처 없음.
    """
    raise NotImplementedError("fragile fetch — 진짜 차단 출처 전용(현 catalog 엔 없음)")
