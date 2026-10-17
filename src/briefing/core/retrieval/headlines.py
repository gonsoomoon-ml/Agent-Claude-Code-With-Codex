"""headlines — 제목·링크 전용 소스: 본문을 가져오지 않고, AI 판정자에는 **제목만** 넘긴다.

왜(2026-10-17 적법성 점검): AI타임스 기사마다 "무단전재 및 재배포, AI학습 및 활용 금지" 고지가 붙어 있다.
본문 수집 + LLM 요약(카드)은 이 고지와 정면 충돌 → 카드 경로(curate)에서 뺀다. 대신 기계가 읽으라고 공개한
RSS 의 제목·링크·발행시각만 쓴다. 피드 요약문은 본문 앞 300자를 그대로 옮긴 것이라 싣지 않는다(전재).
Haiku 관련성 판정·선별은 제목만 받고 출력은 선택 여부뿐 — 메일엔 원제목을 그대로 싣는다(재작성·번역·요약 없음).
판단 근거: docs/work_note/Oct-2026/261017-find-new-articles/source-candidates.md

검증 카드가 아니므로 gate/certifier 를 거치지 않는다 → render 가 "요약·검증 없음" 칸으로 카드와 분리한다.
"""
from __future__ import annotations

import calendar
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timezone

from .. import _debug
from . import sources as src
from .relevance import RelevanceFn, is_ai_relevant
from .selection import SelectFn, latest_k

_DEFAULT_MAX_HEADLINES = 8   # 소스당 헤드라인 상한(카탈로그 max_items 가 덮어씀)
_POOL = 30                   # 판정 후보 상한 — Haiku 관련성 판정은 제목당 1콜이라 비용·지연을 유계로

# (source, window_hours) -> 후보. 기본 = 피드 전용 수집(fetch_headline_feed). 테스트는 fake 주입.
HeadlineFetchFn = Callable[[src.Source, int], Sequence[src.FetchedArticle]]


@dataclass(frozen=True)
class Headline:
    source_key: str
    media: str          # 카탈로그 정본명(예 "AI Times")
    title: str          # 피드 원제목 그대로
    url: str
    published_at: str   # ISO8601 (없으면 "")


def fetch_headline_feed(source: src.Source, window_hours: int) -> list[src.FetchedArticle]:
    """RSS → (제목, 링크, 발행시각). 기사 페이지 요청 0 · 피드 요약문 미사용(raw_text="").

    `_fetch_feed` 를 쓰지 않는 이유: 그쪽은 링크를 따라가 전문을 받고(금지된 본문 수집), 짧은 항목을
    스텁으로 버린다(제목만 있는 항목은 전부 탈락). 여기선 둘 다 하면 안 된다.
    """
    import feedparser  # lazy — sources._fetch_feed 와 같은 이유

    feed = src._with_deadline(lambda: feedparser.parse(source.url), src._FETCH_TIMEOUT_S,
                              f"headline feed {source.url}")
    if feed is None:   # 시간초과(warn 은 _with_deadline 이 이미 냄)
        return []
    now = time.time()
    out: list[src.FetchedArticle] = []
    for entry in feed.entries:
        if len(out) >= _POOL:
            break
        title = (entry.get("title") or "").strip()
        link = (entry.get("link") or "").strip()
        if not (title and link):
            continue
        published = ""
        parsed = entry.get("published_parsed") or entry.get("updated_parsed")
        if parsed:
            ts = calendar.timegm(parsed)
            if window_hours and (now - ts) / 3600.0 > window_hours:
                continue
            published = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
        out.append(src.FetchedArticle(source.key, link, title, "", published))
    return out


def collect_headlines(
    sources: Sequence[src.Source],
    *,
    window_hours: int = 24,
    fetch_fn: HeadlineFetchFn | None = None,
    relevance_fn: RelevanceFn | None = None,
    select_fn: SelectFn | None = None,
) -> dict[str, list[Headline]]:
    """headlines_only 소스만 → {source_key: [Headline]}. 다른 소스는 무시(카드 경로 = curate).

    require_ai 면 제목으로 관련성 판정(주=Haiku, 미주입=키워드), 캡 초과면 select=llm 일 때 판정자가 고른다.
    한 소스 실패가 브리핑을 막지 않는다(curate 와 같은 source-level degradation).
    """
    fetch = fetch_fn or fetch_headline_feed
    is_relevant = relevance_fn or is_ai_relevant
    out: dict[str, list[Headline]] = {}
    for source in sources:
        if not source.headlines_only:
            continue
        try:
            arts = fetch(source, source.window_hours or window_hours)
        except Exception as err:  # noqa: BLE001 — 피드 1개 실패가 전체 브리핑을 죽이면 안 됨
            _debug.warn("headlines skip", f"{source.key}: {type(err).__name__}: {err}")
            continue
        # ★ 고지 준수 불변식: 주입 fetch 가 본문을 돌려줘도 판정자에게 닿기 전에 지운다 — AI 에는 제목만.
        cands = [replace(a, raw_text="") for a in list(arts)[:_POOL]]
        if source.require_ai:
            cands = [a for a in cands if is_relevant(a.title, "")]
        cap = source.max_items or _DEFAULT_MAX_HEADLINES
        if len(cands) > cap:
            chooser = select_fn if (source.select == "llm" and select_fn is not None) else latest_k
            cands = list(chooser(cands, cap))[:cap]
        if cands:
            out[source.key] = [Headline(source.key, source.name, a.title, a.url, a.published_at) for a in cands]
    return out
