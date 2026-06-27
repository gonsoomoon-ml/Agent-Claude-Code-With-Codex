"""pipeline — host-agnostic 브리핑 드라이버 (curate → per-user gate → render).

★ 오케스트레이션을 *호스트 무관* 함수로 추출 — AgentCore entrypoint·로컬 스모크·테스트가 *모두* 이 함수를 부른다
(배포 어댑터에 용접 + 스모크 중복 제거). 결정론: gate 가 비가역 결정 소유; 이 드라이버는 수집·팬아웃·렌더 *순서*만.
DI seam(fetch/draft/revise/verify_fn) 그대로 통과 → 단위 테스트가 전 파이프라인을 결정론으로 덮음.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from . import render
from . import sources as src
from .config import Settings, UserConfig
from .curation import FetchArticleFn, curate
from .gate import GatedCard, produce_card
from .source_store import SourceStore


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
) -> list[UserBriefing]:
    """공유 수집(union)→동결 → per-user [gate.produce_card → render]. 사용자별 UserBriefing 목록 반환.

    ★ gate/certifier 는 user-blind(trust 경계). 배달(SES)·QUARANTINE 행선지는 호출자(어댑터) 책임 — 여기선 산출만.
    """
    fetch_targets = src.fetch_set(u.sources for u in users)  # 모든 사용자 선택의 합집합 1회
    by_key = curate(store, fetch_targets, window_hours=window_hours, fetch_article_fn=fetch_article_fn)

    out: list[UserBriefing] = []
    for u in users:
        user_keys = [s.key for s in src.resolve_sources(u.sources)]
        frozen = [fs for k in user_keys for fs in by_key.get(k, [])]
        cards = tuple(
            produce_card(fs, u, settings, store, draft_fn=draft_fn, revise_fn=revise_fn, verify_fn=verify_fn)
            for fs in frozen
        )
        out.append(
            UserBriefing(
                user_id=u.id,
                recipient=u.recipient,
                cards=cards,
                email=render.render_email(cards, u, settings, store),
                published=sum(1 for c in cards if c.decision == "PUBLISH"),
                quarantined=sum(1 for c in cards if c.decision == "QUARANTINE"),
            )
        )
    return out
