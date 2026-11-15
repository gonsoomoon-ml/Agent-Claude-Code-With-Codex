#!/usr/bin/env python3
"""switch.py — 시스템 on/off 스위치(EventBridge 스케줄의 켜짐/꺼짐).

끄면 아무것도 런타임을 깨우지 않는다 → LLM 호출·런타임 과금 0. 표·이미지·Lambda·런타임은 그대로라
켜면 다음 스케줄 시각부터 바로 돈다. 꺼 둔 동안에도 수동 실행(invoke_runtime)은 된다.

★ `BRIEFING_DRY_RUN=1` 은 비용 스위치가 아니다 — 요약·검증은 다 돌고 메일만 안 나간다. 그래서 `on`·`status` 는
  Lambda 의 그 값을 함께 보여 주고, 켰는데 dry-run 이면 경고한다.
대상 = deploy_scheduler.SCHEDULES 의 이름 전부(데일리 + 주간) — 없는 스케줄은 건너뛴다(주간을 안 만든 계정).

사용법: `uv run python -m briefing.scheduler.switch on|off|status`
"""
from __future__ import annotations

import sys

from .deploy_scheduler import LAMBDA_NAME, SCHEDULES

SCHEDULE_NAMES: tuple[str, ...] = tuple(s["name"] for s in SCHEDULES)
STATES = {"on": "ENABLED", "off": "DISABLED"}
# UpdateSchedule 은 전체 교체 — get_schedule 응답에서 정의 필드만 골라 다시 넘긴다(Arn·날짜 등 읽기 전용 필드 제외).
_DEFINITION_KEYS = ("ScheduleExpression", "ScheduleExpressionTimezone", "FlexibleTimeWindow", "Target",
                    "Description", "GroupName", "StartDate", "EndDate", "KmsKeyArn", "ActionAfterCompletion")
_DRY_ON = ("1", "true", "yes", "on")   # lambda_handler 와 같은 해석


def _get(sched, name: str) -> dict | None:
    try:
        return sched.get_schedule(Name=name)
    except sched.exceptions.ResourceNotFoundException:
        return None


def set_state(sched, names, state: str) -> list[tuple[str, str | None, str | None]]:
    """각 스케줄을 state 로 맞춘다 → [(이름, 이전 상태, 이후 상태)]. 없는 스케줄은 (이름, None, None)."""
    out: list[tuple[str, str | None, str | None]] = []
    for name in names:
        cur = _get(sched, name)
        if cur is None:
            out.append((name, None, None))
            continue
        if cur["State"] != state:
            sched.update_schedule(Name=name, State=state, **{k: cur[k] for k in _DEFINITION_KEYS if k in cur})
        out.append((name, cur["State"], state))
    return out


def dry_run_value(lam, function_name: str = LAMBDA_NAME) -> str | None:
    """Lambda 의 BRIEFING_DRY_RUN — 함수가 없으면 None, 변수가 없으면 ""(Lambda 는 dry-run 으로 본다)."""
    try:
        cfg = lam.get_function_configuration(FunctionName=function_name)
    except lam.exceptions.ResourceNotFoundException:
        return None
    return cfg.get("Environment", {}).get("Variables", {}).get("BRIEFING_DRY_RUN", "")


def run(action: str, sched, lam, names=SCHEDULE_NAMES) -> list[str]:
    """on · off · status 실행 → 출력 줄 목록(테스트가능). status 는 아무것도 바꾸지 않는다."""
    lines: list[str] = []
    if action in STATES:
        for name, before, after in set_state(sched, names, STATES[action]):
            lines.append(f"  {name}: 없음(건너뜀)" if before is None else
                         f"  {name}: {before} → {after}" if before != after else f"  {name}: {after}(그대로)")
    else:
        for name in names:
            cur = _get(sched, name)
            lines.append(f"  {name}: 없음" if cur is None else
                         f"  {name}: {cur['State']} · {cur['ScheduleExpression']} {cur.get('ScheduleExpressionTimezone', 'UTC')}")
    dry = dry_run_value(lam)
    if dry is None:
        lines.append(f"  Lambda {LAMBDA_NAME}: 없음")
        return lines
    lines.append(f"  Lambda BRIEFING_DRY_RUN={dry or '(미설정)'}")
    if action == "on" and (dry == "" or dry.strip().lower() in _DRY_ON):
        lines.append("  ⚠️ 경고: BRIEFING_DRY_RUN 이 dry-run 이다 — 요약·검증은 돌고(LLM 비용) 메일은 안 나간다. "
                     "`.env` 에 BRIEFING_DRY_RUN=0 을 넣고 deploy_scheduler 를 다시 실행하라.")
    return lines


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1 or args[0] not in ("on", "off", "status"):
        print("사용법: uv run python -m briefing.scheduler.switch on|off|status")
        return 2
    import boto3

    from ..core.config import load_settings

    region = load_settings().region
    account = boto3.client("sts").get_caller_identity()["Account"]
    print(f"switch {args[0]} — account={account} region={region}")
    for line in run(args[0], boto3.client("scheduler", region_name=region), boto3.client("lambda", region_name=region)):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
