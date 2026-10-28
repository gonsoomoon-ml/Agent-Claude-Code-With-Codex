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
import threading
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import yaml

from .. import _debug
from ..article_identity import cite_key
from . import robots


@dataclass(frozen=True)
class Source:
    key: str
    name: str
    url: str
    kind: str              # "rss" | "html"(리스팅 직행) | "auto"(피드 자동발견 후 폴백) | "sitemap"(사이트맵 urlset)
    lang: str              # "en" | "ko"
    fragile: bool = False  # True = *진짜 차단*(Cloudflare challenge/JS-only) — v1 미구현, 현 catalog 엔 없음
    category: str = ""     # 관심 버킷(type 직교). catalog 필수(로더가 빈값 거부); UI 분야 그룹핑 키. 기본 ""=임시 Source()용
    require_ai: bool = False  # True = 종합지 피드 → curate 가 AI 관련 기사만 통과(relevance.is_ai_relevant). 기본 off=전부 통과
    homepage: str = ""     # 선택: 사람이 볼 정식 랜딩 URL 오버라이드. 빈값이면 파생(html=url, rss=호스트) — RSS 피드 호스트가 회사 대문일 때(aws-ml) 지정
    window_hours: int = 0  # 소스별 수집 윈도우 오버라이드(0=글로벌 기본). html(date-only 메타데이터) 소스는 48 — W≥U(24h)+P(24h), late-post(오후 PT 발행) 유실 보정
    max_items: int = 0     # 소스별 캡 오버라이드(0=글로벌 기본 5). 고볼륨 소스의 브리핑 편중/비용 상한
    select: str = ""       # 캡 초과 시 선별 방식: ""|"latest"(최신순 잘림=현행) | "llm"(Haiku pick-K — curate 가 select_fn 주입 시)
    headlines_only: bool = False  # True = 제목·링크만(본문 미수집·카드 없음) — 기사별 "AI 활용 금지" 고지 소스(headlines.py)
    article_path: str = ""  # html 리스팅의 글 링크 접두 경로(예 Discourse "/t/"). 빈값 = 리스팅 경로 바로 아래 한 단계만 글


_KINDS = frozenset({"rss", "html", "auto", "sitemap"})
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
        ho = e.get("headlines_only", False)
        if not isinstance(ho, bool):  # 'yes' 같은 문자열이 조용히 True 가 되면 본문 수집 여부가 뒤바뀐다
            raise ValueError(f"catalog[{i}] '{e['key']}': headlines_only 는 true|false (got {ho!r})")
        ap = e.get("article_path", "")
        if not isinstance(ap, str) or (ap and not ap.startswith("/")):
            raise ValueError(f"catalog[{i}] '{e['key']}': article_path 는 '/' 로 시작하는 경로 (got {ap!r})")
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
                headlines_only=ho,
                article_path=ap,
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
    """per-user 선택 키 → CATALOG 엔트리(catalog 순서·결정론). 빈 선택이면 전체(기본).

    ★ 미상 키는 **드롭하되 warn**(silent failure 금지). 드롭을 유지하는 이유: 키 하나가 오타거나
      카탈로그에서 빠졌다고 그 사용자의 브리핑 전체를 막으면 안 된다(curate 의 소스별 degrade 와 동형).
      경고를 붙이는 이유: 카탈로그에서 출처를 제거하면 그 키를 구독하던 사용자는 *모르는 채로*
      기사를 덜 받는다 — 2026-09-13 에 `openai` 키가 발행처 재편 후 무음 드롭 중인 걸 발견했다.
    """
    if not selected:
        return list(CATALOG)
    sel = set(selected)
    if unknown := sorted(sel - set(catalog_keys())):
        _debug.warn("resolve_sources",
                    f"미상 출처 키 {unknown} 무시 — 카탈로그에 없음(제거됐거나 오타). "
                    f"이 선택의 사용자는 해당 출처를 받지 못한다.")
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
    cited: tuple[str, ...] = ()  # 본문 안·다른 사이트 링크의 인용 키(재보도 dedup). 페이지 본문이 없으면 () — 검사 안 함


_TAG_RE = re.compile(r"<[^>]+>")


def _clean_text(raw_html: str) -> str:
    """RSS summary/content(HTML 가능) → 평문. 태그 제거 + 엔티티 해제 + 공백 정리."""
    text = _html.unescape(_TAG_RE.sub(" ", raw_html or ""))
    return re.sub(r"\s+", " ", text).strip()


# ── 페치 시간 상한 ── 소스 하나가 멈춰도 브리핑 전체가 정지하지 않게 하는 두 층 ──
_FETCH_TIMEOUT_S = 20    # 네트워크 요청 1건의 하드 데드라인(초). 실측 정상 0.2~1.2s 대비 ~17배 여유.
_SOURCE_BUDGET_S = 180   # html 소스 1개의 총 수집 예산(초). 링크 39개 직렬 walk 가 이 값의 대상.


def _with_deadline(fn: Callable[[], Any], timeout_s: float, label: str) -> Any:
    """`fn()` 을 데몬 스레드에서 돌리고 timeout_s 안에 안 끝나면 포기(+warn) → None.

    **왜 필요한가:** trafilatura 는 pycurl 이 없으면 urllib3 경로를 타는데, `create_pool(timeout=N)`
    은 urllib3 에서 `Timeout(connect=N, read=N)` 이다 — read 는 *읽기 1회* 기준이라 매번 초기화된다
    (총 시간 상한 없음). 서버가 조금씩 흘리면 영원히 안 끝나고, 파이프라인은 소스를 한 스레드에서
    직렬 처리하므로 브리핑 전체가 무출력으로 멈춘다(2026-08-09 미발송의 원인).
    라이브러리 자체 read 타임아웃(30s)보다 **낮게** 잡아야 항상 우리가 먼저 이겨 의미가 결정론적이다.

    **왜 스레드인가:** `signal.alarm` 은 메인 스레드 전용인데 AgentCore 는 async task 스레드에서
    파이프라인을 돌린다. 멈춘 스레드는 daemon 이라 프로세스 종료를 막지 않는다(결국 trafilatura
    자체 read 타임아웃이 풀어준다).

    ★ 예외는 삼키지 않고 그대로 재전파 — 침묵 실패 금지(listing 실패의 RuntimeError 계약 보존).
    """
    box: dict[str, Any] = {}

    def _run() -> None:
        try:
            box["v"] = fn()
        except BaseException as exc:  # noqa: BLE001 — 삼키지 않고 호출 스레드로 재전파
            box["e"] = exc

    worker = threading.Thread(target=_run, daemon=True)
    worker.start()
    worker.join(timeout_s)
    if worker.is_alive():
        _debug.warn("fetch timeout", f"{label}: {timeout_s:g}s 초과 — 포기")
        return None
    if "e" in box:
        raise box["e"]
    return box.get("v")


def _fetch_feed(
    feed_url: str, source_key: str, *, window_hours: int = 24, max_items: int = 5, full_text: bool = True,
    timeout_s: float = _FETCH_TIMEOUT_S,
) -> list[FetchedArticle]:
    """RSS/Atom 피드 → FetchedArticle 목록 (feedparser). fetch_clean_rss·제너릭 피드발견 공용.

    full_text 면 entry.link 를 따라가 trafilatura 로 *전문*(상한) 추출 — 실패 시 피드 요약 폴백.
    published_parsed(UTC)는 calendar.timegm 으로 epoch 화. title·본문 모두 있어야 채택.
    ★ 폴백 결과가 기사 길이에 못 미치면(= 티저) 채택하지 않는다 — `_is_stub` 참조.
    """
    import feedparser  # lazy — feedparser 미설치 환경에서도 sources 모듈 import 가능

    if not robots.allowed(feed_url, robots.FEED_TOKEN):   # 막힌 피드는 요청하지 않는다(non-silent)
        _debug.warn("robots", f"{source_key}: robots.txt 가 막은 피드 — 요청 안 함: {feed_url}")
        return []
    # ★ feedparser.parse(url) 는 *자체 네트워크 다운로드* — `_http_get` 과 같은 무제한 구멍이라 같은 상한.
    feed = _with_deadline(lambda: feedparser.parse(feed_url), timeout_s, f"feed {feed_url}")
    if feed is None:                                  # 시간초과(warn 은 _with_deadline 이 이미 냄)
        return []
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
        text, page = "", ""
        if full_text and link:  # 전문 추적(상한). 실패·부실 시 아래 피드 요약 폴백.
            page = _http_get(link)
            if page:
                _t, body, _d, _c = _extract_body(page)
                text = body
        page_used = bool(page) and len(text) >= MIN_SOURCE_CHARS  # 폴백이면 페이지 링크를 인용 키로 쓰지 않는다
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
        cited = _cited_keys(page, link) if page_used else ()
        out.append(FetchedArticle(source_key, link, title, text, published, cited=cited))
    if stubs:  # non-silent — 소스가 통째로 스텁이면(예: 봇 차단) 여기서만 보인다
        _debug.warn("fetch stub", f"{source_key}: 본문 미확보 {len(stubs)}건 제외"
                                  f"(<{MIN_SOURCE_CHARS}자) — {' | '.join(stubs)}")
    return out


def fetch_clean_rss(source: Source, *, window_hours: int = 24, max_items: int = 5) -> list[FetchedArticle]:
    """클린 RSS 페치 — _fetch_feed(source.url) 위임. window_hours 이내·최신 max_items cap."""
    return _fetch_feed(source.url, source.key, window_hours=window_hours, max_items=max_items)


# ── 제너릭 HTML/auto 출처 페치 (사이트별 코드 0; trafilatura 범용 추출 + 피드 자동발견) ──
MAX_SOURCE_CHARS = 20000  # 상한 — 초장문 꼬리만 컷. 동결 원문은 DDB 에 영구 보존된다(DynamoSourceStore — TTL 없음).
# 2026-10-28 상향(8,000→20,000): 8일(10-20~27) 원문 162건 중 89건(55%)이 8,000자에서 잘렸다. 잘린 84건을 다시
# 받아 잰 전체 길이 = 중앙값 14.2K · p90 24.5K · 최대 46.8K → 20K 면 그중 15건(162건의 ~9%)만 잘린다.
# 예: claude.com ROI 글(15,979자)이 절반에서 잘려 세 레버(control·track·prove) 중 'Prove' 섹션 전체가 빠졌다.
# ★ 공개 출시 전 결정(2026-10-28 보류): 영구 보존 × 상향 = 대부분 기사의 거의 전문을 영구 저장한다 — 원문 보존 정책을 그때 정한다.
# 잘린 원문으로 볼 길이(F1) — `_excerpt` 는 상한 안 마지막 공백에서 자르므로 잘린 원문은 상한보다 *짧다*.
# (2026-10-17 감사, 8,000 상한: ≥8,000자 0건 · 7,900–7,999자 520건 — `>= MAX_SOURCE_CHARS` 판정 경고는 한 번도 안 떴다.)
TRUNCATED_MIN_CHARS = MAX_SOURCE_CHARS - 100

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


def discover_feed(url: str, *, timeout_s: float = _FETCH_TIMEOUT_S) -> str:
    """사이트 URL → RSS/Atom 피드 URL 자동발견(없으면 ""). UI 가 URL 만 받아도 RSS 인식(kind:auto 토대).

    ★ 시간초과도 ""(미발견) — 호출자가 리스팅 크롤 경로로 폴백하므로 소스를 잃지 않는다.
      `fetch_generic_html` 의 첫 호출이라, 여기가 막히면 아래 소스 예산 검사에 도달조차 못 한다.
    """
    from trafilatura import feeds  # lazy(무거운 import 회피)
    found = _with_deadline(lambda: feeds.find_feed_urls(url), timeout_s, f"discover_feed {url}")
    return found[0] if found else ""


def _http_get(url: str, *, timeout_s: float = _FETCH_TIMEOUT_S) -> str:
    """trafilatura.fetch_url — UA·재시도 처리된 평문 GET(접근통제 우회 없음). 실패·시간초과 시 "".

    robots.txt 가 막은 경로면 요청하지 않고 ""(+warn) — 호출자 입장에선 페치 실패와 같다(그 글만 skip).
    """
    import trafilatura
    if not robots.allowed(url):
        _debug.warn("robots", f"robots.txt 가 막은 경로 — 요청 안 함: {url}")
        return ""
    return _with_deadline(lambda: trafilatura.fetch_url(url), timeout_s, url) or ""


def _excerpt(text: str, limit: int = MAX_SOURCE_CHARS) -> str:
    """단어 경계에서 limit 자로 자른 본문(초장문만 컷; 상한 = source-of-record 안전판)."""
    if len(text) <= limit:
        return text
    cut = text[:limit]
    sp = cut.rfind(" ")
    return (cut[:sp] if sp > limit * 0.6 else cut).strip()


def _article_links(listing_html: str, listing_url: str, article_path: str = "") -> list[str]:
    """리스팅에서 기사 링크만 — 제너릭 휴리스틱, 사이트별 코드 아님.

    기본: listing path 한 단계 아래 `{path}/{slug}`. article_path 를 주면 그 접두 경로 아래 링크(예 Discourse
    목록 `/c/news/14` 의 글 = `/t/<slug>/<id>` — 목록 경로 밖). href 는 큰·작은따옴표 둘 다(Discourse = 작은따옴표).
    """
    base = urlparse(listing_url)
    path = (article_path or base.path).rstrip("/")
    out: list[str] = []
    seen: set[str] = set()
    for href in re.findall(r"""href=["']([^"']+)["']""", listing_html):
        clean = href.split("#")[0].split("?")[0]
        p = urlparse(urljoin(f"{base.scheme}://{base.netloc}", clean)).path.rstrip("/")
        tail = p[len(path) + 1:]
        if p.startswith(path + "/") and tail and (article_path or "/" not in tail):
            absu = f"{base.scheme}://{base.netloc}{p}"
            if absu not in seen:
                seen.add(absu)
                out.append(absu)
    return out


# 본문 끝에 붙는 매체 부트플레이트(구독 권유·저자 소개) — 기사가 아니므로 동결 원문에서 뺀다.
# **왜 검증에 중요한가:** 동결본은 certifier 가 claim 을 재도출하는 유일한 근거다. 부트플레이트의
# 숫자가 거기 섞이면 **본문에 없는 수치의 알리바이**가 된다 — the-decoder 의 "AI Radar frontier
# report **six times a year**" 는 35/35(100%) 기사에 붙어 매번 값 6 을 원문 집합에 넣었고,
# 그러면 "6개 조직과 협력" 류의 근거 없는 claim 이 통과한다(적대 검증에서 실증).
# relevance._FOOTER_RE(aitimes 푸터의 'AI' 가 관련성 필터를 무력화)와 같은 계열의 문제.
# 마커 앞이 본문이므로 마커부터 끝까지 자른다. 소스별 코드 0(매체 무관 패턴만).
# "More recent articles" = 블로그 본문 끝 다른 글 목록(simonwillison.net 15건 중 11건 — 제목·날짜의 숫자가 섞인다).
_BOILER_RE = re.compile(
    r"(?is)\n\s*(?:AI News Without the Hype|Subscribe to THE DECODER|About the authors?|More recent articles)\b.*",
)


def _strip_boilerplate(text: str) -> str:
    """본문 끝 부트플레이트 제거. 자른 뒤가 기사 길이인지는 호출자(_is_stub)가 판단한다."""
    return _BOILER_RE.sub("", text).strip()


def _extract_body(html_text: str) -> tuple[str, str, str, str]:
    """trafilatura 로 임의 HTML → (title, 본문(부트플레이트 제거 + 상한), date, canonical). 실패 시 빈값 4개.

    canonical = `<link rel=canonical>`/`og:url`(trafilatura doc.url) — 없으면 "". RSS 전문·HTML 공용.
    """
    import trafilatura
    doc = trafilatura.bare_extraction(html_text, with_metadata=True)
    if doc is None:
        return ("", "", "", "")
    title = (getattr(doc, "title", "") or "").strip()
    body = _excerpt(_strip_boilerplate((getattr(doc, "text", "") or "").strip()))
    date = (getattr(doc, "date", "") or "").strip()
    canonical = (getattr(doc, "url", "") or "").strip()
    return (title, body, date, canonical)


_MD_LINK_RE = re.compile(r"\]\((https?://[^)\s]+)\)")


def _body_links(html_text: str) -> list[str]:
    """본문 안 링크(절대 URL)만 — trafilatura 본문 추출(markdown·링크 포함) 결과에서 뽑는다.

    ★ 페이지의 원시 href 전부를 쓰면 사이드바·메뉴·관련 글 목록이 섞여 엉뚱한 쌍이 생긴다(2026-10-28 실측:
      The Decoder 사이드바). 본문 추출이 그 경계를 대신 그어 준다. 실패 시 [].
    """
    import trafilatura
    md = trafilatura.extract(html_text, output_format="markdown", include_links=True) or ""
    return _MD_LINK_RE.findall(md)


def _cited_keys(html_text: str, page_url: str) -> tuple[str, ...]:
    """기사 HTML → 인용 키(정렬·중복 제거). 같은 사이트 링크(자기 글·태그 페이지)는 원문 후보가 아니라 버린다."""
    own = cite_key(page_url).partition("/")[0]
    keys = {k for k in map(cite_key, _body_links(html_text)) if k and k.partition("/")[0] != own}
    return tuple(sorted(keys))


def _host(u: str) -> str:
    """URL 호스트(소문자·`www.` 제거). 상대경로·빈값이면 ""."""
    h = (urlparse(u).hostname or "").lower()
    return h[4:] if h.startswith("www.") else h


def _is_offsite(canonical: str, listing_url: str) -> bool:
    """canonical 이 리스팅과 *다른 사이트*면 True — 블로그 리스팅에 남은 링크가 문서 등으로 옮겨간 경우.

    ★ fail-open: canonical 없음·상대경로(판단 불가)와 서브도메인 관계(blog.x.com ↔ x.com)는 False(통과).
    실측(2026-10-10): html 소스 4곳 링크 77개 중 True 는 best-practices(→ code.claude.com) 1건뿐.
    """
    c, home = _host(canonical), _host(listing_url)
    if not (c and home):
        return False
    return not (c == home or c.endswith("." + home) or home.endswith("." + c))


def _extract_article(html_text: str, url: str, source_key: str, listing_url: str = "") -> FetchedArticle | None:
    """HTML 기사 → FetchedArticle. title·본문 둘 다 있고 본문이 기사 길이여야 채택(`_is_stub`).

    listing_url 을 주면(html 리스팅 경로) canonical 이 다른 사이트인 페이지를 버린다 — 문서 페이지는
    최종 수정일을 날짜로 내서 수정될 때마다 "새 글"로 보이기 때문(2026-10 감사: Best practices 14회 재발송).
    """
    title, text, published, canonical = _extract_body(html_text)
    if not (title and text):
        return None
    if listing_url and _is_offsite(canonical, listing_url):  # non-silent — 무엇을 왜 버렸나
        _debug.warn("fetch offsite", f"{source_key}: canonical 이 다른 호스트 — 글이 아니라 건너뜀: {url} → {canonical}")
        return None
    if _is_stub(text):  # 리스팅/쿠키월/스켈레톤에서 부스러기만 추출된 경우 — non-silent
        _debug.warn("fetch stub", f"{source_key}: 본문 미확보({len(text)}자 < {MIN_SOURCE_CHARS}) — {title[:40]}")
        return None
    return FetchedArticle(source_key, url, title, text, published, cited=_cited_keys(html_text, url))


def _is_stale(published: str, window_hours: int) -> bool:
    """published(ISO/날짜) 가 window 밖이면 True. 날짜 모르면(빈값) False(통과)."""
    if not (published and window_hours):
        return False
    try:
        ts = datetime.fromisoformat(published.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return False
    return (time.time() - ts) / 3600.0 > window_hours


def fetch_generic_html(
    source: Source, *, window_hours: int = 24, max_items: int = 5, budget_s: float = _SOURCE_BUDGET_S
) -> list[FetchedArticle]:
    """제너릭 HTML/auto 출처 페치 — 피드 발견 시 RSS 경로 재사용, 없으면 리스팅 링크 + trafilatura 본문 추출.

    ★ 매체별 코드 0(UI 가 URL 만 받아도 동작). 권위 페치=fabric 소유. bounded excerpt 만(법적 자세).
    listing fetch 실패는 예외(curate 가 skip+warn); 개별 기사 실패는 그 기사만 skip.

    budget_s = 이 소스 하나의 **총** 수집 시간 예산(진입 시점부터). 요청별 상한(`_FETCH_TIMEOUT_S`)만으론
    링크 39개 × 20s = 13분까지 늘어나므로 두 층이 필요하다. 초과 시 남은 링크를 포기하고 확보분만 반환 —
    예외가 아니라 `break` 다(한 소스 때문에 브리핑을 죽이지 않는다; 카드별 격리와 같은 원리).
    """
    deadline = time.monotonic() + budget_s        # 예산 시계는 discover_feed·리스팅까지 포함해 진입 시점부터
    # kind: html = 리스팅 직행. 피드 자동발견(trafilatura.find_feed_urls)은 페이지가 광고한 피드를 *내부에서*
    # 직접 받아 와 robots 검사를 거치지 않는다(PyTorch KR 목록은 막힌 /c/news/14.rss 를 광고). auto 만 발견한다.
    feed = discover_feed(source.url) if source.kind == "auto" else ""
    if feed:
        return _fetch_feed(feed, source.key, window_hours=window_hours, max_items=max_items)
    listing = _http_get(source.url)
    if not listing:
        raise RuntimeError(f"html listing fetch 실패: {source.url}")
    out: list[FetchedArticle] = []
    for url in _article_links(listing, source.url, source.article_path):
        if len(out) >= max_items:
            break
        if time.monotonic() >= deadline:
            _debug.warn("fetch budget",
                        f"{source.key}: {budget_s:g}s 초과 — 남은 링크 포기({len(out)}건 확보)")
            break
        page = _http_get(url)
        if not page:
            continue
        art = _extract_article(page, url, source.key, source.url)
        if art and not _is_stale(art.published_at, window_hours):
            out.append(art)
    return out


_SM_URL_RE = re.compile(r"<url>(.*?)</url>", re.S)


def _sm_tag(block: str, name: str) -> str:
    """사이트맵 <url> 블록에서 태그 값(CDATA·엔티티 해제). 없으면 ""."""
    m = re.search(rf"<{name}>\s*(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?\s*</{name}>", block, re.S)
    return _html.unescape(m.group(1).strip()) if m else ""


def _epoch(date: str) -> float:
    """ISO 날짜/시각 → epoch(정렬용). 모르면 0(맨 뒤)."""
    try:
        return datetime.fromisoformat(date.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def _sitemap_entries(xml: str) -> list[tuple[str, str]]:
    """사이트맵 urlset → [(글 URL, 날짜)] 최신순. 날짜 = news:publication_date(뉴스 사이트맵, 정확) 우선, 없으면 lastmod.

    정규식 파싱인 이유: 필요한 건 태그 3개뿐이고, 외부 XML 을 XML 파서에 넣지 않으니 엔티티 확장류 위험이 없다.
    """
    out: list[tuple[str, str]] = []
    for block in _SM_URL_RE.findall(xml):
        loc = _sm_tag(block, "loc")
        if loc:
            out.append((loc, _sm_tag(block, "news:publication_date") or _sm_tag(block, "lastmod")))
    out.sort(key=lambda e: _epoch(e[1]), reverse=True)
    return out


def fetch_sitemap(
    source: Source, *, window_hours: int = 24, max_items: int = 5, budget_s: float = _SOURCE_BUDGET_S
) -> list[FetchedArticle]:
    """사이트맵(urlset) 출처 — 사이트가 robots.txt `Sitemap:` 으로 선언한 기계용 글 목록.

    피드를 robots 가 막은 사이트(the-decoder `Disallow: */feed/`)를 허용된 경로로 읽는 방법이다.
    창 안의 글만 페이지를 열어 본문을 뽑고(`_extract_article` — html 리스팅과 같은 추출·스텁·offsite 검사),
    발행 시각은 사이트맵 값을 쓴다(페이지 추출 날짜는 날짜만인 경우가 많아 late-post 오판의 원인).
    sitemapindex(하위 사이트맵 목록)는 미지원 — catalog url 에 urlset 주소를 직접 적는다.
    다운로드 실패·index 는 예외(curate 가 skip+warn); 개별 글 실패는 그 글만 skip. 예산은 fetch_generic_html 과 같다.
    """
    deadline = time.monotonic() + budget_s
    xml = _http_get(source.url)
    if not xml:
        raise RuntimeError(f"sitemap fetch 실패: {source.url}")
    if "<sitemapindex" in xml:
        raise RuntimeError(f"sitemapindex 미지원 — urlset 주소를 catalog url 로: {source.url}")
    out: list[FetchedArticle] = []
    for url, date in _sitemap_entries(xml):
        if len(out) >= max_items:
            break
        if _is_stale(date, window_hours):       # 창 밖 글은 페이지를 열지 않는다
            continue
        if time.monotonic() >= deadline:
            _debug.warn("fetch budget", f"{source.key}: {budget_s:g}s 초과 — 남은 글 포기({len(out)}건 확보)")
            break
        page = _http_get(url)
        if not page:
            continue
        art = _extract_article(page, url, source.key, source.url)
        if art is None:
            continue
        if date:
            art = replace(art, published_at=date)
        if not _is_stale(art.published_at, window_hours):
            out.append(art)
    return out


def fetch_fragile(source: Source) -> list[FetchedArticle]:
    """*진짜 차단*(Cloudflare challenge/JS-only) 출처 — v1 미구현(접근통제 우회는 법적 red line이라 보류).

    평문으로 잡히는 HTML 은 fetch_generic_html(trafilatura)로 처리. 현 catalog 엔 fragile 출처 없음.
    """
    raise NotImplementedError("fragile fetch — 진짜 차단 출처 전용(현 catalog 엔 없음)")
