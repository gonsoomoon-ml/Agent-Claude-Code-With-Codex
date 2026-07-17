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

from .. import _debug


@dataclass(frozen=True)
class Source:
    key: str
    name: str
    url: str
    kind: str              # "rss" | "html" | "auto" (auto = 피드 자동발견 후 폴백)
    lang: str              # "en" | "ko"
    fragile: bool = False  # True = *진짜 차단*(Cloudflare challenge/JS-only) — v1 미구현, 현 catalog 엔 없음
    category: str = ""     # 관심 버킷(type 직교). catalog 필수(로더가 빈값 거부); UI 분야 그룹핑 키. 기본 ""=임시 Source()용
    require_ai: bool = False  # True = 종합지 피드 → curate 가 AI 관련 기사만 통과(relevance.is_ai_relevant). 기본 off=전부 통과
    homepage: str = ""     # 선택: 사람이 볼 정식 랜딩 URL 오버라이드. 빈값이면 파생(html=url, rss=호스트) — RSS 피드 호스트가 회사 대문일 때(aws-ml) 지정
    window_hours: int = 0  # 소스별 수집 윈도우 오버라이드(0=글로벌 기본). html(date-only 메타데이터) 소스는 48 — W≥U(24h)+P(24h), late-post(오후 PT 발행) 유실 보정
    max_items: int = 0     # 소스별 캡 오버라이드(0=글로벌 기본 5). 고볼륨 소스의 브리핑 편중/비용 상한
    select: str = ""       # 캡 초과 시 선별 방식: ""|"latest"(최신순 잘림=현행) | "llm"(Haiku pick-K — curate 가 select_fn 주입 시)


_KINDS = frozenset({"rss", "html", "auto"})
_LANGS = frozenset({"en", "ko"})
_REQUIRED = ("key", "name", "url", "kind", "lang", "category")  # category 도 필수 → 루프가 빈값 거부(non-empty 강제)
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
        w = e.get("window_hours", 0)
        if not isinstance(w, int) or isinstance(w, bool) or w < 0:  # bool 은 int 서브클래스 — 명시 거부
            raise ValueError(f"catalog[{i}] '{e['key']}': window_hours 는 0 이상 정수 (got {w!r})")
        mi = e.get("max_items", 0)
        if not isinstance(mi, int) or isinstance(mi, bool) or mi < 0:
            raise ValueError(f"catalog[{i}] '{e['key']}': max_items 는 0 이상 정수 (got {mi!r})")
        sel = e.get("select", "")
        if sel not in ("", "latest", "llm"):
            raise ValueError(f"catalog[{i}] '{e['key']}': select 는 ''|'latest'|'llm' (got {sel!r})")
        out.append(
            Source(
                key=e["key"],
                name=e["name"],
                url=e["url"],
                kind=e["kind"],
                lang=e["lang"],
                fragile=bool(e.get("fragile", False)),
                category=e["category"],
                require_ai=bool(e.get("require_ai", False)),
                homepage=e.get("homepage", ""),
                window_hours=w,
                max_items=mi,
                select=sel,
            )
        )
    return tuple(out)


# 전역 vetted CATALOG — catalog.yaml 에서 로드(import 시 1회, 검증). UI 는 이 목록에서 선택.
CATALOG: tuple[Source, ...] = _load_catalog()


def catalog_categories() -> list[str]:
    """CATALOG 의 정렬된 유니크 category — UI 분야 그룹 헤더를 데이터에서 유도(하드코딩 enum 아님 → 스케일)."""
    return sorted({s.category for s in CATALOG})
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
    feed_url: str, source_key: str, *, window_hours: int = 24, max_items: int = 5, full_text: bool = True
) -> list[FetchedArticle]:
    """RSS/Atom 피드 → FetchedArticle 목록 (feedparser). fetch_clean_rss·제너릭 피드발견 공용.

    full_text 면 entry.link 를 따라가 trafilatura 로 *전문*(상한) 추출 — 실패 시 피드 요약 폴백.
    published_parsed(UTC)는 calendar.timegm 으로 epoch 화. title·본문 모두 있어야 채택.
    ★ 폴백 결과가 기사 길이에 못 미치면(= 티저) 채택하지 않는다 — `_is_stub` 참조.
    """
    import feedparser  # lazy — feedparser 미설치 환경에서도 sources 모듈 import 가능

    feed = feedparser.parse(feed_url)
    now = time.time()
    out: list[FetchedArticle] = []
    stubs: list[str] = []
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
        text = ""
        if full_text and link:  # 전문 추적(상한). 실패·부실 시 아래 피드 요약 폴백.
            page = _http_get(link)
            if page:
                _t, body, _d = _extract_body(page)
                text = body
        if len(text) < MIN_SOURCE_CHARS:
            # 전문 미확보 → 피드 요약 폴백. 피드가 전문을 싣는 경우도 있으므로 *더 긴 쪽*을 쓴다.
            raw = entry.get("summary") or ""
            if not raw and entry.get("content"):
                raw = entry["content"][0].get("value", "")
            fallback = _excerpt(_clean_text(raw))
            if len(fallback) > len(text):
                text = fallback
        if not title:
            continue
        if _is_stub(text):  # 기사가 아니라 티저/메타설명 → 카드 자격 없음(아래 게이트 사유 참조)
            stubs.append(f"{title[:34]}({len(text)}자)")
            continue
        out.append(FetchedArticle(source_key, link, title, text, published))
    if stubs:  # non-silent — 소스가 통째로 스텁이면(예: 봇 차단) 여기서만 보인다
        _debug.warn("fetch stub", f"{source_key}: 본문 미확보 {len(stubs)}건 제외"
                                  f"(<{MIN_SOURCE_CHARS}자) — {' | '.join(stubs)}")
    return out


def fetch_clean_rss(source: Source, *, window_hours: int = 24, max_items: int = 5) -> list[FetchedArticle]:
    """클린 RSS 페치 — _fetch_feed(source.url) 위임. window_hours 이내·최신 max_items cap."""
    return _fetch_feed(source.url, source.key, window_hours=window_hours, max_items=max_items)


# ── 제너릭 HTML/auto 출처 페치 (사이트별 코드 0; trafilatura 범용 추출 + 피드 자동발견) ──
MAX_SOURCE_CHARS = 8000  # 넉넉한 상한 — 대부분 기사엔 사실상 전문, 초장문만 컷. 저작권: 원문은 7일 TTL(DynamoSourceStore)로 ephemeral.

MIN_SOURCE_CHARS = 500
"""동결 원문의 **하한** — 이보다 짧으면 기사가 아니라 티저(피드 요약·SEO 메타설명)다.

**왜 필요한가(2026-07-17 실측):** openai.com 이 봇을 403 으로 막으면서(`Enable JavaScript and cookies
to continue`) 전문 추출이 실패했고, 코드가 조용히 RSS 요약으로 폴백해 **SEO 메타설명 139~176자**를
동결 원문으로 삼았다. openai.com 소스 **8/8(100%)이 이렇게 만들어졌고 7장이 발행됐다** —
"Learn how OpenAI is making ChatGPT safer for teens…" 한 문장이 카드의 전부였다.

이것이 이 게이트가 존재하는 이유이자, 검증이 못 막는 종류의 실패다: author 는 받은 것을 정확히
요약했고 certifier 는 그 요약이 동결본에 함의됨을 정확히 확인했다. 게이트는 *동결본에 대한 충실성*만
보고 *동결본이 기사인지*는 아무도 안 본다 → **garbage in, verified garbage out.**
동결본이 기사라는 것은 verify-before-publish 의 *전제*이므로 페치 단계에서 지켜야 한다.

**임계 근거(source-store 148건 실측):** 스텁 = openai 139~176 · aws 도입문단 268/373 ·
aitimes 300자 절단 티저 6건. 진짜 짧은 기사 = aitimes 604·910(기자 바이라인까지 완결).
500 은 이 둘 사이에 있어 스텁 16건을 정확히 컷하고 진짜 기사는 하나도 안 건드린다.
"""


def _is_stub(text: str) -> bool:
    """동결 원문 자격 미달(기사가 아닌 티저) 판정. 길이만 본다 — 결정론·언어 무관."""
    return len(text.strip()) < MIN_SOURCE_CHARS


def discover_feed(url: str) -> str:
    """사이트 URL → RSS/Atom 피드 URL 자동발견(없으면 ""). UI 가 URL 만 받아도 RSS 인식(kind:auto 토대)."""
    from trafilatura import feeds  # lazy(무거운 import 회피)
    found = feeds.find_feed_urls(url)
    return found[0] if found else ""


def _http_get(url: str) -> str:
    """trafilatura.fetch_url — UA·재시도 처리된 평문 GET(접근통제 우회 없음). 실패 시 ""."""
    import trafilatura
    return trafilatura.fetch_url(url) or ""


def _excerpt(text: str, limit: int = MAX_SOURCE_CHARS) -> str:
    """단어 경계에서 limit 자로 자른 본문(초장문만 컷; 상한 = source-of-record 안전판)."""
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


def _extract_body(html_text: str) -> tuple[str, str, str]:
    """trafilatura 로 임의 HTML → (title, 본문(상한 적용), date). 실패 시 ("","",""). RSS 전문·HTML 공용."""
    import trafilatura
    doc = trafilatura.bare_extraction(html_text, with_metadata=True)
    if doc is None:
        return ("", "", "")
    title = (getattr(doc, "title", "") or "").strip()
    body = _excerpt((getattr(doc, "text", "") or "").strip())
    date = (getattr(doc, "date", "") or "").strip()
    return (title, body, date)


def _extract_article(html_text: str, url: str, source_key: str) -> FetchedArticle | None:
    """HTML 기사 → FetchedArticle. title·본문 둘 다 있고 본문이 기사 길이여야 채택(`_is_stub`)."""
    title, text, published = _extract_body(html_text)
    if not (title and text):
        return None
    if _is_stub(text):  # 리스팅/쿠키월/스켈레톤에서 부스러기만 추출된 경우 — non-silent
        _debug.warn("fetch stub", f"{source_key}: 본문 미확보({len(text)}자 < {MIN_SOURCE_CHARS}) — {title[:40]}")
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
