"""sent_log — ⑤ 중복 발송 방지(dedup). dispatch 의 `sent_log` seam(`already_sent`/`mark_sent`) 구현.

★ 전용 테이블 `briefing-sent-log`(PK=user_id, SK=run_date) — ③ ledger 재사용은 footgun이라 분리:
  ledger 의 `query(user_id, sk>=since_date)` 가 상한이 없어, 같은 테이블에 SENT 마커를 넣으면 그들의
  Diff-Since-Last 질의에 섞인다. runtime 의 기존 `table/briefing-*` IAM 이 이 테이블도 커버(②b).
- 키=(user_id, run_date) → "이 사용자가 이 날 브리핑을 받았나"의 per-user-per-day boolean.
- endpoint_url 옵션: 빈값=실 AWS, 값=DynamoDB Local(dynamo.py 와 동일 패턴). 테이블 주입 가능(테스트는 fake).
"""
from __future__ import annotations

import os
from typing import Any

DEFAULT_SENT_LOG_TABLE = "briefing-sent-log"


def _table(table_name: str, region: str = "", endpoint_url: str = ""):
    import boto3  # lazy — local/테스트 경로는 boto3 무접촉
    kw: dict = {}
    if region:
        kw["region_name"] = region
    if endpoint_url:
        kw["endpoint_url"] = endpoint_url
    return boto3.resource("dynamodb", **kw).Table(table_name)


class DynamoSentLog:
    """DDB 백킹 dedup. 테이블 리소스 주입(DI) → 테스트는 fake, 운영은 `from_settings`."""

    def __init__(self, table: Any) -> None:
        self._t = table

    @classmethod
    def from_settings(cls, settings: Any) -> DynamoSentLog:
        name = os.getenv("SENT_LOG_TABLE", DEFAULT_SENT_LOG_TABLE)
        return cls(_table(name, settings.region, getattr(settings, "ddb_endpoint_url", "")))

    def already_sent(self, user_id: str, run_date: str) -> bool:
        return "Item" in self._t.get_item(Key={"user_id": user_id, "run_date": run_date})

    def mark_sent(self, user_id: str, run_date: str, *, record: dict | None = None) -> None:
        # 키 단위 멱등(같은 (user,date) 덮어씀). record 있으면 audit 필드 병합(하위호환: 없으면 기존 dedup 불리언).
        item = {"user_id": user_id, "run_date": run_date}
        if record:
            item.update(record)
        self._t.put_item(Item=item)
