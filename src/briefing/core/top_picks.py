"""top_picks — 오늘의 핵심 3: 사용자가 받는 발행 카드 전체에서 K장을 골라 메일 맨 앞에 올린다.

검증을 통과한 카드의 **순서만** 바꾼다(내용 불변) → author/certifier 분리와 무관(relevance·selection 과 같은 논거).
기준 = 소스 선별과 같은 P2b(`selection._SELECT_SYSTEM`) — 에이전트·Applied AI 우선, 같은 사건 둘 금지.
판정 재료 = 사실층(제목·요약)만. 해석층(why)은 lens 별이라 넣으면 같은 카드 묶음도 사용자마다 결과가 달라져
run 내 공유(memo)가 깨진다. 실패하면 빈 목록 = 핵심 칸 없이 발송 — 최신순 대체는 하지 않는다(앞 K장 = 늘
첫 섹션 카드가 "핵심"이 된다).
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING

from . import _debug
from .retrieval.selection import pick_indices

if TYPE_CHECKING:
    from .gate import GatedCard

TOP_K = 3
TOP_MIN_CARDS = 6   # 발행 카드가 이보다 적으면 생략 — 짧은 메일(주말)에선 순서만 바뀌는 셈

# (발행 카드, k) -> 고른 카드(k 이하). production = Haiku(relevance_bedrock), 미주입 = 칸 없음.
TopPickFn = Callable[[Sequence["GatedCard"], int], list["GatedCard"]]


def llm_top_picks(cards: Sequence[GatedCard], k: int,
                  *, invoke: Callable[[str, str], str]) -> list[GatedCard]:
    """LLM 판정자로 K장. invoke=(system,user)->str. 실패·유효 선택 부족이면 [](non-silent warn)."""
    cards = list(cards)
    try:
        return [cards[i] for i in pick_indices([(g.card.headline, g.card.summary) for g in cards], k, invoke=invoke)]
    except Exception as err:  # throttle/timeout/파싱 — 핵심 칸만 빠지고 메일은 나간다
        _debug.warn("top picks", f"{type(err).__name__}: {err} → 핵심 칸 생략")
        return []


def top_source_ids(cards: Sequence[GatedCard], top_pick_fn: TopPickFn | None,
                   memo: dict[tuple[str, ...], tuple[str, ...]]) -> tuple[str, ...]:
    """pipeline 용 — 발행 카드가 TOP_MIN_CARDS 이상일 때만 판정해 고른 카드의 source_id(판정 순서)를 돌려준다.

    같은 카드 묶음을 받는 사용자들은 memo 로 판정 1회를 공유한다(재료가 사실층이라 lens 무관).
    주입된 함수가 예외를 던져도 () — 브리핑을 막지 않는다(fail-open, 카드 격리와 같은 원칙).
    """
    pub = [g for g in cards if g.decision == "PUBLISH"]
    if top_pick_fn is None or len(pub) < TOP_MIN_CARDS:
        return ()
    key = tuple(g.card.source_id for g in pub)
    if key not in memo:
        try:
            memo[key] = tuple(g.card.source_id for g in top_pick_fn(pub, TOP_K))[:TOP_K]
        except Exception as err:  # noqa: BLE001 — 핵심 칸은 보조 장치
            _debug.warn("top picks", f"{type(err).__name__}: {err} → 핵심 칸 생략")
            memo[key] = ()
    return memo[key]
