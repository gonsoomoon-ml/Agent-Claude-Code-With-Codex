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

import yaml


@dataclass(frozen=True)
class Source:
    key: str
    name: str
    url: str
    kind: str              # "rss" | "html"
    lang: str              # "en" | "ko"
    fragile: bool = False  # True = Browser Tool 필요(Cloudflare/HTML), v1.5


_KINDS = frozenset({"rss", "html"})
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


def fetch_clean_rss(
    source: Source, *, window_hours: int = 24, max_items: int = 5
) -> list[FetchedArticle]:
    """클린 RSS 페치 (feedparser). window_hours 이내 항목만(0=무필터), 최신 max_items 개 cap.

    published_parsed(UTC struct_time)는 `calendar.timegm` 으로 epoch 화(local 해석 방지). title·본문 모두 있어야 채택.
    """
    import feedparser  # lazy — feedparser 미설치 환경에서도 sources 모듈 import 가능

    feed = feedparser.parse(source.url)
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
        out.append(FetchedArticle(source.key, link, title, text, published))
    return out


def fetch_fragile(source: Source) -> list[FetchedArticle]:
    """깨지는 출처(Cloudflare/HTML) — v1.5 Browser Tool 경유(관리형 격리 브라우저). v1 폴백 미정."""
    raise NotImplementedError("fragile fetch — v1.5 AgentCore Browser Tool")
