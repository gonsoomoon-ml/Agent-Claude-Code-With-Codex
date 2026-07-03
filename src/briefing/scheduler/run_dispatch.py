"""local — ⑤ due-check 로컬 프리뷰 (클라우드 0). "지금(또는 주어진 tick) 누가 due 인가"를 본다.

실 LLM/SES/네트워크 없이 타임존 due 로직만 실 사용자 설정으로 검증. 실 브리핑·발송은 클라우드(scheduled)가 담당.
실행: `uv run python -m briefing.scheduler.run_dispatch [now_utc]`   (예: 2026-06-27T22:00 = 07:00 KST)
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from ..core.config import list_users, load_settings, load_user
from .due import users_due_now


def main() -> None:
    settings = load_settings()
    users = [load_user(uid, settings) for uid in list_users(settings)]

    now = datetime.now(timezone.utc)
    if len(sys.argv) > 1:                       # now override (UTC ISO; tz 없으면 UTC 로 간주)
        now = datetime.fromisoformat(sys.argv[1])
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

    due = users_due_now(users, now)
    due_ids = {u.id for u in due}
    print(f"[now]  {now.isoformat()}  ·  사용자 {len(users)}명")
    for u in users:
        local = now.astimezone(ZoneInfo(u.timezone))
        mark = "  ← DUE" if u.id in due_ids else ""
        print(f"   {u.id:10} send_hour={u.send_hour:02d}  {u.timezone:16} local={local:%Y-%m-%d %H:%M}{mark}")
    print(f"[due]  {len(due)}명: {sorted(due_ids)}")
    print("[next] 클라우드 실행: Lambda 수동 invoke 또는 invoke_runtime --mode scheduled (dry-run)")


if __name__ == "__main__":
    main()
