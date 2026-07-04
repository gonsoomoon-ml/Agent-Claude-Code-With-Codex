"""curation — 생성/평가 층: 권위 페치 → 동결(sha256). v1 = 결정론 Python, v-next = Strands Graph.

§5.5 staging: v1 은 plain(조기 graph 금지). 출처가 늘고 LLM 클러스터링/랭킹/근접중복 머지가 생기면
이 함수를 Strands `GraphBuilder`(collect→cluster→rank→fan-out, 각 단계 = FunctionNode)로 *승격* — gate 는 무변경.
권위 페치 = fabric(여기) 소유 → content-addressed 동결 → author·certifier 가 같은 바이트(anti-cheat).
fetch 실 구현은 sources.py(clean RSS=feedparser, fragile=Browser Tool v1.5); 여기선 *오케스트레이션*만.
(AgentCore 무관 = 호스트 무관 fabric 로직이라 core/ 에 둔다.)
"""
from __future__ import annotations

from collections.abc import Callable, Sequence

from .. import _debug
from . import sources as src
from ..stores.source_store import FrozenSource, SourceStore
from .relevance import is_ai_relevant
from .sources import FetchedArticle, Source

FetchArticleFn = Callable[[Source, int], Sequence[FetchedArticle]]


def _default_fetch(source: Source, window_hours: int) -> Sequence[FetchedArticle]:
    """source.kind/fragile 로 디스패치: fragile→fetch_fragile(미구현·진짜 차단), html/auto→제너릭(trafilatura), rss→clean RSS."""
    if source.fragile:
        return src.fetch_fragile(source)
    if source.kind in ("html", "auto"):
        return src.fetch_generic_html(source, window_hours=window_hours)
    return src.fetch_clean_rss(source, window_hours=window_hours)


def curate(
    store: SourceStore,
    fetch_targets: Sequence[Source],
    *,
    window_hours: int = 24,
    fetch_article_fn: FetchArticleFn | None = None,
) -> dict[str, list[FrozenSource]]:
    """fetch_targets(출처 union) → 권위 페치 → content-addressed 동결 → {source_key: [FrozenSource]}.

    fetch_article_fn = **DI seam** (테스트/로컬은 fake 주입; 기본은 sources.py 페치). content-addressing 이
    사용자·출처 간 dedup. 반환을 source_key 로 그룹화 → 호출자가 per-user 선택으로 필터.
    """
    fetch = fetch_article_fn or _default_fetch
    by_key: dict[str, list[FrozenSource]] = {}
    seen: set[str] = set()
    for source in fetch_targets:
        try:
            articles = fetch(source, window_hours)
        except Exception as err:  # 출처 1개 실패(fragile NotImplementedError·네트워크·파싱)가 전체 브리핑을 죽이면 안 됨
            # source-level graceful degradation: skip 후 계속. non-silent — warn(항상 stderr→CloudWatch).
            _debug.warn("curate skip", f"{source.key}: {type(err).__name__}: {err}")
            continue
        dropped = 0
        for art in articles:
            # require_ai 소스(종합지 피드): AI 무관 기사를 요약·검증 *전* 컷 → 비용 절감(relevance v1, recall 우선)
            if source.require_ai and not is_ai_relevant(art.title, art.raw_text):
                dropped += 1
                continue
            fs = store.freeze(
                url=art.url, title=art.title, raw_text=art.raw_text,
                fetched_at=art.published_at, media=source.name,  # 발행 매체 = catalog 정본명(예 "AI Times")
            )
            if fs.source_id in seen:
                continue
            seen.add(fs.source_id)
            by_key.setdefault(source.key, []).append(fs)
        if dropped:  # non-silent — 무엇이/몇 건 빠졌나 기록(silent truncation 금지)
            _debug.dprint("curate filter", f"{source.key}: AI 무관 {dropped}건 제외(require_ai)", "yellow")
    return by_key
