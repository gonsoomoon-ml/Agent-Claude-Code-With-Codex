"""due — 타임존 due-check (C6). 시간당 1회 tick 에서 "지금 발송할 사용자"만 고른다.

★ 확장 설계: per-user EventBridge 규칙(사용자 수만큼 규칙)을 만드는 대신, 규칙은 *시간당 1개*만 두고
  이 순수 함수가 each user 의 로컬 시각을 계산해 due 를 판정한다 → 사용자 수와 무관하게 규칙 1개.
순수·결정론(now_utc 주입) → 타임존 경계(예: 07:00 KST = 22:00 UTC 전날)를 단위 테스트로 못박는다.
"""
from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from typing import TypeVar

U = TypeVar("U")  # UserConfig 류(덕타이핑: .send_hour:int · .timezone:str 필요)


def users_due_now(users: Sequence[U], now_utc: datetime, *, granularity_h: int = 1) -> list[U]:
    """now_utc 를 each user.timezone 으로 변환 → 로컬 시각이 user.send_hour 버킷이면 due.

    granularity_h: tick 간격(시간). 기본 1 = 시간당 tick → 로컬 hour == send_hour 면 due.
    now_utc 가 naive 면 UTC 로 간주(스케줄러는 보통 aware UTC 를 준다).
    """
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)
    out: list[U] = []
    for u in users:
        try:
            local = now_utc.astimezone(ZoneInfo(u.timezone))
        except Exception:  # noqa: BLE001 — 잘못된 tz 는 이 사용자만 건너뜀(배치 보호)
            from ..core._debug import warn
            warn("due.skip_bad_tz", f"user={getattr(u, 'id', u)!r} timezone={u.timezone!r}")
            continue
        # 시간 버킷팅: granularity_h=1 이면 local.hour == send_hour
        if local.hour // granularity_h == u.send_hour // granularity_h:
            out.append(u)
    return out
