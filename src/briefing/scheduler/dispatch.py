"""dispatch — ⑤ 의 host-agnostic 코어: due → run_briefing → deliver. (Lambda·로컬이 같이 호출.)

흐름(시간당 tick 1회):
  users_due_now(now_utc) → 그 due 사용자만 run_briefing(검증 후 발행) → 각 브리핑 deliver(SES)
  → 중복 발송 방지(sent_log; v1 은 None=stateless 가능, v1.5 는 ③ ledger/DDB 로 백킹).

★ 순수 오케스트레이션(시계·DI fns·deliver 주입) → 클라우드 없이 전 경로 테스트. 비가역 조치(발송)는
  should_deliver 게이트 통과분만(QUARANTINE/빈 미발송) + dedup → 같은 run_date 재실행해도 1회.
"""
from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from ..core.pipeline import run_briefing
from .deliver import DeliverFn, should_deliver
from .due import users_due_now


def dispatch(
    settings: Any,
    store: Any,
    users: Sequence[Any],
    now_utc: datetime,
    *,
    deliver_fn: DeliverFn,
    run_date: str = "",
    granularity_h: int = 1,
    sent_log: Any = None,
    card_cache: Any = None,
    ledger: Any = None,
    **fns: Any,
) -> list[str]:
    """due 사용자에게 검증 브리핑을 발송. 발송한 user_id 목록 반환.

    sent_log(옵션): `already_sent(user_id, run_date)->bool` · `mark_sent(user_id, run_date)` —
    None 이면 dedup 없음(v1 stateless). run_date 미지정 시 now_utc 의 UTC 날짜.
    """
    due = users_due_now(users, now_utc, granularity_h=granularity_h)
    if not due:
        return []   # 아무도 due 아님 → run_briefing/발송 호출 0 (시간당 tick 의 대부분)

    rd = run_date or now_utc.strftime("%Y-%m-%d")
    briefings = run_briefing(settings, store, due, card_cache=card_cache, ledger=ledger, run_date=rd, **fns)

    delivered: list[str] = []
    for b in briefings:
        if not should_deliver(b):                                   # QUARANTINE/빈 발행 → skip
            continue
        if sent_log is not None and sent_log.already_sent(b.user_id, rd):
            continue                                                # 중복 발송 방지
        deliver_fn(b)                                               # 비가역: SES 발송
        if sent_log is not None:
            sent_log.mark_sent(b.user_id, rd)
        delivered.append(b.user_id)
    return delivered
