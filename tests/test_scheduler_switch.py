"""scheduler/switch — 시스템 on/off 스위치의 *순수·AWS 무관* 단위(fake client 주입). 실 동작은 배포 뒤 확인.

스위치 = EventBridge 스케줄의 켜짐/꺼짐(2026-11-14 결정 4-2). 꺼 두면 아무것도 런타임을 깨우지 않는다.
"""
from __future__ import annotations

import copy


class _NotFound(Exception):
    pass


class _FakeSched:
    class exceptions:
        ResourceNotFoundException = _NotFound

    def __init__(self, schedules: dict[str, dict]):
        self.schedules = copy.deepcopy(schedules)
        self.updates: list[dict] = []

    def get_schedule(self, **kw):
        if kw["Name"] not in self.schedules:
            raise _NotFound(kw["Name"])
        # 실 응답처럼 update 에 넘기면 안 되는 메타 필드를 섞는다
        return {**copy.deepcopy(self.schedules[kw["Name"]]), "Name": kw["Name"],
                "Arn": "arn:aws:scheduler:::schedule/default/" + kw["Name"],
                "CreationDate": "2026-11-14", "LastModificationDate": "2026-11-14", "ResponseMetadata": {}}

    def update_schedule(self, **kw):
        self.updates.append(kw)
        self.schedules[kw["Name"]] = {k: v for k, v in kw.items() if k != "Name"}


class _FakeLambda:
    class exceptions:
        ResourceNotFoundException = _NotFound

    def __init__(self, dry: str | None = "0", exists: bool = True):
        self.dry, self.exists = dry, exists

    def get_function_configuration(self, **kw):
        if not self.exists:
            raise _NotFound(kw["FunctionName"])
        variables = {"BRIEFING_RUNTIME_ARN": "arn:rt"}
        if self.dry is not None:
            variables["BRIEFING_DRY_RUN"] = self.dry
        return {"Environment": {"Variables": variables}}


def _daily(state: str) -> dict:
    return {"ScheduleExpression": "cron(0 5 * * ? *)", "ScheduleExpressionTimezone": "Asia/Seoul",
            "FlexibleTimeWindow": {"Mode": "OFF"}, "State": state,
            "Target": {"Arn": "arn:lambda", "RoleArn": "arn:role", "Input": '{"source": "briefing-hourly-tick"}',
                       "RetryPolicy": {"MaximumRetryAttempts": 0}}}


def test_off_disables_an_enabled_schedule_without_changing_its_definition():
    """UpdateSchedule 은 전체 교체라 식·시간대·대상을 같이 넘겨야 한다 — 빠지면 스위치가 스케줄을 망가뜨린다."""
    from briefing.scheduler.switch import set_state

    sched = _FakeSched({"briefing-hourly-tick": _daily("ENABLED")})
    result = set_state(sched, ["briefing-hourly-tick"], "DISABLED")

    assert result == [("briefing-hourly-tick", "ENABLED", "DISABLED")]
    after = sched.schedules["briefing-hourly-tick"]
    assert after["State"] == "DISABLED"
    assert {k: v for k, v in after.items() if k != "State"} == {k: v for k, v in _daily("ENABLED").items() if k != "State"}


def test_update_call_omits_read_only_fields_from_the_get_response():
    from briefing.scheduler.switch import set_state

    sched = _FakeSched({"briefing-hourly-tick": _daily("DISABLED")})
    set_state(sched, ["briefing-hourly-tick"], "ENABLED")

    assert not {"Arn", "CreationDate", "LastModificationDate", "ResponseMetadata"} & set(sched.updates[0])


def test_schedule_that_does_not_exist_is_skipped():
    """주간 스케줄을 만들지 않은 계정(BRIEFING_WEEKLY_SCHEDULES=0)에서도 스위치가 그대로 돈다."""
    from briefing.scheduler.switch import set_state

    sched = _FakeSched({"briefing-hourly-tick": _daily("DISABLED")})
    result = set_state(sched, ["briefing-hourly-tick", "briefing-weekly-build"], "ENABLED")

    assert result == [("briefing-hourly-tick", "DISABLED", "ENABLED"), ("briefing-weekly-build", None, None)]


def test_schedule_already_in_the_requested_state_is_not_updated():
    from briefing.scheduler.switch import set_state

    sched = _FakeSched({"briefing-hourly-tick": _daily("DISABLED")})
    result = set_state(sched, ["briefing-hourly-tick"], "DISABLED")

    assert result == [("briefing-hourly-tick", "DISABLED", "DISABLED")] and sched.updates == []


def test_run_on_enables_every_existing_schedule():
    from briefing.scheduler.switch import run

    sched = _FakeSched({"briefing-hourly-tick": _daily("DISABLED")})
    run("on", sched, _FakeLambda(dry="0"))

    assert sched.schedules["briefing-hourly-tick"]["State"] == "ENABLED"


def test_run_on_warns_when_lambda_is_in_dry_run():
    """켰는데 BRIEFING_DRY_RUN=1 이면 요약·검증은 다 돌고 메일만 안 나간다 — 비용만 나가는 상태를 알린다."""
    from briefing.scheduler.switch import run

    sched = _FakeSched({"briefing-hourly-tick": _daily("DISABLED")})
    lines = run("on", sched, _FakeLambda(dry="1"))

    assert any("BRIEFING_DRY_RUN" in ln and "경고" in ln for ln in lines)


def test_run_on_warns_when_dry_run_variable_is_missing():
    """Lambda 는 변수가 없으면 dry-run 으로 본다(lambda_handler 기본 "1") — 없는 것도 같은 경고."""
    from briefing.scheduler.switch import run

    lines = run("on", _FakeSched({"briefing-hourly-tick": _daily("DISABLED")}), _FakeLambda(dry=None))

    assert any("BRIEFING_DRY_RUN" in ln and "경고" in ln for ln in lines)


def test_run_on_does_not_warn_when_sending_is_enabled():
    from briefing.scheduler.switch import run

    lines = run("on", _FakeSched({"briefing-hourly-tick": _daily("DISABLED")}), _FakeLambda(dry="0"))

    assert not any("경고" in ln for ln in lines)


def test_run_status_reports_state_expression_and_dry_run_without_changing_anything():
    from briefing.scheduler.switch import run

    sched = _FakeSched({"briefing-hourly-tick": _daily("ENABLED")})
    lines = run("status", sched, _FakeLambda(dry="0"))

    text = "\n".join(lines)
    assert "briefing-hourly-tick" in text and "ENABLED" in text and "cron(0 5 * * ? *)" in text and "Asia/Seoul" in text
    assert "BRIEFING_DRY_RUN=0" in text and sched.updates == []


def test_run_off_disables_and_reports_missing_lambda_without_failing():
    from briefing.scheduler.switch import run

    sched = _FakeSched({"briefing-hourly-tick": _daily("ENABLED")})
    lines = run("off", sched, _FakeLambda(exists=False))

    assert sched.schedules["briefing-hourly-tick"]["State"] == "DISABLED" and lines
