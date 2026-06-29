"""pipeline — host-agnostic 브리핑 드라이버 (curate → per-user gate → render).

★ 오케스트레이션을 *호스트 무관* 함수로 추출 — AgentCore entrypoint·로컬 스모크·테스트가 *모두* 이 함수를 부른다
(배포 어댑터에 용접 + 스모크 중복 제거). 결정론: gate 가 비가역 결정 소유; 이 드라이버는 수집·팬아웃·렌더 *순서*만.
DI seam(fetch/draft/revise/verify_fn) 그대로 통과 → 단위 테스트가 전 파이프라인을 결정론으로 덮음.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from . import render
from .retrieval import sources as src
from .stores.cache import CardCache, card_key
from .config import Settings, UserConfig
from .retrieval.curation import FetchArticleFn, curate
from .gate import GatedCard, produce_card
from .stores.ledger import Ledger
from .stores.source_store import SourceStore


@dataclass(frozen=True)
class UserBriefing:
    user_id: str
    recipient: str
    cards: tuple[GatedCard, ...]
    email: str
    published: int
    quarantined: int


def run_briefing(
    settings: Settings,
    store: SourceStore,
    users: Sequence[UserConfig],
    *,
    window_hours: int = 24,
    fetch_article_fn: FetchArticleFn | None = None,
    draft_fn=None,
    revise_fn=None,
    verify_fn=None,
    card_cache: CardCache | None = None,
    ledger: Ledger | None = None,
    run_date: str = "",
) -> list[UserBriefing]:
    """공유 수집(union)→동결 → per-user [gate.produce_card → render]. 사용자별 UserBriefing 목록 반환.

    ★ gate/certifier 는 user-blind(trust 경계). 배달(SES)·QUARANTINE 행선지는 호출자(어댑터) 책임 — 여기선 산출만.
    """
    fetch_targets = src.fetch_set(u.sources for u in users)  # 모든 사용자 선택의 합집합 1회
    by_key = curate(store, fetch_targets, window_hours=window_hours, fetch_article_fn=fetch_article_fn)

    out: list[UserBriefing] = []
    today = render.format_briefing_date(run_date)
    for u in users:
        # (frozen, category) 쌍 — category 는 출처 카탈로그 Source.category (분야 그룹 키)
        fs_cat = [(fs, s.category) for s in src.resolve_sources(u.sources) for fs in by_key.get(s.key, [])]
        cards = tuple(
            _process(fs, u, settings, store, card_cache, ledger, run_date, draft_fn, revise_fn, verify_fn)
            for fs, _ in fs_cat
        )
        # render 는 *카드의* source_id 로 분야를 찾는다(실 author 는 fs.source_id 복사) → 카드 기준으로 매핑
        source_categories = {g.card.source_id: cat for (_fs, cat), g in zip(fs_cat, cards)}
        out.append(
            UserBriefing(
                user_id=u.id,
                recipient=u.recipient,
                cards=cards,
                email=render.render_email(
                    cards, u, settings, store, source_categories=source_categories, today=today
                ),
                published=sum(1 for c in cards if c.decision == "PUBLISH"),
                quarantined=sum(1 for c in cards if c.decision == "QUARANTINE"),
            )
        )
    return out


def _process(fs, u, settings, store, card_cache, ledger, run_date, draft_fn, revise_fn, verify_fn) -> GatedCard:
    """카드 캐시(재계산 방지) + ledger(history 기록). 둘 다 드라이버 레벨 — gate/trust 무관.

    cache hit 면 claude -p+codex skip; ledger 는 매 (user, source) 처리를 (run_date, source_id, card_key) 로 기록
    → history 조회가 source_store(원문)·card cache(카드) 를 join 할 수 있게 한다(중복 저장 없음).
    """
    if card_cache is None and ledger is None:
        return produce_card(fs, u, settings, store, draft_fn=draft_fn, revise_fn=revise_fn, verify_fn=verify_fn)
    key = card_key(
        fs.source_id,
        getattr(u, "lens", "") or "",
        getattr(u, "skill_md", "") or "",
        getattr(settings, "author_model_id", ""),
    )
    gated = card_cache.get(key) if card_cache is not None else None
    if gated is None:
        gated = produce_card(fs, u, settings, store, draft_fn=draft_fn, revise_fn=revise_fn, verify_fn=verify_fn)
        if card_cache is not None:
            card_cache.put(key, gated)
    if ledger is not None:
        ledger.append(run_date, u.id, fs.source_id, key, gated.decision, gated.card.headline)
    return gated
