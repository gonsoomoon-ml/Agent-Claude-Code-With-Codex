"""deploy_scheduler 의 *순수·AWS 무관* 단위 — 스케줄 명세(SCHEDULES)와 create 호출 인자. 실 배포는 done-when 으로 검증.

주간(1-B, delivery-plan §4·§7-4): 토 06:00·07:00 Asia/Seoul 스케줄 2개(Input 에 mode) + 표 briefing-weekly-issues(PK=issue_date).
데일리 시간당 스케줄은 Input 에 mode 가 없어야 한다(Lambda 기본 scheduled — 무변경)."""
from __future__ import annotations

import json


class _FakeSched:
    class exceptions:
        class ConflictException(Exception):
            pass

    def __init__(self, existing_state: str | None = None):
        self.created: list[dict] = []
        self.updated: list[dict] = []
        self.existing_state = existing_state   # None = 스케줄 없음(create 성공)

    def create_schedule(self, **kw):
        if self.existing_state is not None:
            raise self.exceptions.ConflictException()
        self.created.append(kw)

    def get_schedule(self, **kw):
        return {"Name": kw["Name"], "State": self.existing_state}

    def update_schedule(self, **kw):
        self.updated.append(kw)


class _FakeDdb:
    class exceptions:
        class ResourceInUseException(Exception):
            pass

    def __init__(self):
        self.created: list[dict] = []

    def create_table(self, **kw):
        self.created.append(kw)

    def get_waiter(self, name):
        class _W:
            def wait(self, **kw):
                pass
        return _W()


def test_schedules_spec_hourly_unchanged_and_weekly_kst():
    from briefing.scheduler.deploy_scheduler import SCHEDULES

    by = {s["name"]: s for s in SCHEDULES}
    h = by["briefing-hourly-tick"]
    assert h["expr"] == "cron(0 * * * ? *)" and h["tz"] == "UTC" and "mode" not in h["input"]
    b, s = by["briefing-weekly-build"], by["briefing-weekly-send"]
    assert b["expr"] == "cron(0 6 ? * SAT *)" and b["tz"] == "Asia/Seoul" and b["input"]["mode"] == "weekly_build"
    assert s["expr"] == "cron(0 7 ? * SAT *)" and s["tz"] == "Asia/Seoul" and s["input"]["mode"] == "weekly_send"


def test_ensure_schedule_sends_spec_to_scheduler():
    from briefing.scheduler.deploy_scheduler import SCHEDULES, _ensure_schedule

    sched = _FakeSched()
    spec = next(s for s in SCHEDULES if s["name"] == "briefing-weekly-send")
    _ensure_schedule(sched, spec, "arn:lambda", "arn:role")
    kw = sched.created[0]
    assert kw["Name"] == "briefing-weekly-send" and kw["ScheduleExpression"] == "cron(0 7 ? * SAT *)"
    assert kw["ScheduleExpressionTimezone"] == "Asia/Seoul" and kw["State"] == "DISABLED"   # 새 스케줄은 꺼진 채로(스위치로 켠다)
    assert kw["Target"]["Arn"] == "arn:lambda" and kw["Target"]["RoleArn"] == "arn:role"
    assert json.loads(kw["Target"]["Input"]) == {"source": "briefing-weekly-send", "mode": "weekly_send"}
    assert kw["Target"]["RetryPolicy"] == {"MaximumRetryAttempts": 0}


def test_ensure_table_weekly_issues_pk_only_and_sent_log_pk_sk():
    from briefing.scheduler.deploy_scheduler import SENT_LOG_TABLE, WEEKLY_ISSUES_TABLE, _ensure_table

    ddb = _FakeDdb()
    _ensure_table(ddb, WEEKLY_ISSUES_TABLE, pk="issue_date")
    _ensure_table(ddb, SENT_LOG_TABLE, pk="user_id", sk="run_date")
    weekly, sent = ddb.created
    assert weekly["TableName"] == "briefing-weekly-issues" and weekly["BillingMode"] == "PAY_PER_REQUEST"
    assert weekly["KeySchema"] == [{"AttributeName": "issue_date", "KeyType": "HASH"}]
    assert weekly["AttributeDefinitions"] == [{"AttributeName": "issue_date", "AttributeType": "S"}]
    assert sent["KeySchema"] == [{"AttributeName": "user_id", "KeyType": "HASH"},
                                 {"AttributeName": "run_date", "KeyType": "RANGE"}]


# ───────────────────────── 재배포는 켜짐/꺼짐 상태를 건드리지 않는다(결정 4-2) ─────────────────────────

def test_ensure_schedule_update_keeps_disabled_state():
    """꺼 둔 시스템을 재배포해도 다시 켜지지 않는다 — 예전엔 State="ENABLED" 고정이라 재배포가 스위치를 되돌렸다."""
    from briefing.scheduler.deploy_scheduler import SCHEDULES, _ensure_schedule

    sched = _FakeSched(existing_state="DISABLED")
    _ensure_schedule(sched, SCHEDULES[0], "arn:lambda", "arn:role")
    assert sched.created == [] and sched.updated[0]["State"] == "DISABLED"


def test_ensure_schedule_update_keeps_enabled_state():
    from briefing.scheduler.deploy_scheduler import SCHEDULES, _ensure_schedule

    sched = _FakeSched(existing_state="ENABLED")
    _ensure_schedule(sched, SCHEDULES[0], "arn:lambda", "arn:role")
    assert sched.updated[0]["State"] == "ENABLED" and sched.updated[0]["ScheduleExpression"] == "cron(0 * * * ? *)"


# ───────────────────────── 스케줄 명세는 .env 로 조절한다(결정 4-1 · 4-3) ─────────────────────────

def test_schedules_from_env_default_is_the_hourly_and_weekly_spec():
    """설정이 없으면 지금 그대로(매시간 + 주간 2개) — 여러 사용자용 기본 동작을 코드에 남긴다."""
    from briefing.scheduler.deploy_scheduler import SCHEDULES, schedules_from_env

    assert schedules_from_env({}) == SCHEDULES


def test_schedules_from_env_daily_cron_and_timezone_override():
    from briefing.scheduler.deploy_scheduler import schedules_from_env

    specs = schedules_from_env({"BRIEFING_DAILY_CRON": "cron(0 5 * * ? *)", "BRIEFING_DAILY_TZ": "Asia/Seoul"})
    daily = specs[0]
    assert daily["name"] == "briefing-hourly-tick" and daily["input"] == {"source": "briefing-hourly-tick"}
    assert daily["expr"] == "cron(0 5 * * ? *)" and daily["tz"] == "Asia/Seoul"
    assert [s["name"] for s in specs[1:]] == ["briefing-weekly-build", "briefing-weekly-send"]   # 주간은 무변경


def test_schedules_from_env_weekly_off_leaves_only_the_daily_schedule():
    from briefing.scheduler.deploy_scheduler import schedules_from_env

    specs = schedules_from_env({"BRIEFING_WEEKLY_SCHEDULES": "0"})
    assert [s["name"] for s in specs] == ["briefing-hourly-tick"]


def test_schedules_from_env_blank_values_fall_back_to_defaults():
    """`.env` 에 키만 있고 값이 비면 기본값 — 빈 cron 식으로 create 가 터지는 것을 막는다."""
    from briefing.scheduler.deploy_scheduler import SCHEDULES, schedules_from_env

    assert schedules_from_env({"BRIEFING_DAILY_CRON": " ", "BRIEFING_DAILY_TZ": "", "BRIEFING_WEEKLY_SCHEDULES": ""}) == SCHEDULES
