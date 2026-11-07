"""deploy_scheduler 의 *순수·AWS 무관* 단위 — 스케줄 명세(SCHEDULES)와 create 호출 인자. 실 배포는 done-when 으로 검증.

주간(1-B, delivery-plan §4·§7-4): 토 06:00·07:00 Asia/Seoul 스케줄 2개(Input 에 mode) + 표 briefing-weekly-issues(PK=issue_date).
데일리 시간당 스케줄은 Input 에 mode 가 없어야 한다(Lambda 기본 scheduled — 무변경)."""
from __future__ import annotations

import json


class _FakeSched:
    class exceptions:
        class ConflictException(Exception):
            pass

    def __init__(self):
        self.created: list[dict] = []

    def create_schedule(self, **kw):
        self.created.append(kw)


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
    assert kw["ScheduleExpressionTimezone"] == "Asia/Seoul" and kw["State"] == "ENABLED"
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
