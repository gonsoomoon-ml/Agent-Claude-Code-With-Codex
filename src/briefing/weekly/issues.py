"""주간 호 저장소 — 초안 · 게이트 결과 · 상태. 로컬(JSON 파일)과 DynamoDB 두 backend, 같은 의미.

상태: building → ready | quarantined | failed → sending → sent | send_failed.
전이는 조건부다(지금 상태가 허용 집합일 때만). 07:00 send 가 두 번 돌아도 `sending` 을 먼저 잡은 쪽만 보낸다.
DynamoDB 표 `briefing-weekly-issues`(PK=issue_date) — runtime role 의 `table/briefing-*` IAM 이 덮는다(sent_log 와 같은 이유).
값은 전부 문자열로 둔다(게이트 결과 · 씨앗은 JSON 문자열 — DDB resource 의 float/Decimal 문제를 피한다).
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_TABLE = "briefing-weekly-issues"

# 목표 상태 → 허용되는 지금 상태(None = 항목 없음).
EDGES: dict[str, tuple[str | None, ...]] = {
    "building": (None, "ready", "quarantined", "failed"),   # 보내기 전이면 다시 만들 수 있다
    "ready": ("building",),
    "quarantined": ("building",),
    "failed": ("building",),
    "sending": ("ready", "quarantined"),                    # 1단계는 격리 호도 표시를 달아 관리자에게 보낸다
    "sent": ("sending",),
    "send_failed": ("sending",),
}
# force=True(관리자 수동 복구): 이미 보낸 호만 빼고 어디서든.
_FORCE_FROM: tuple[str | None, ...] = (None, "building", "ready", "quarantined", "failed", "sending", "send_failed")


class TransitionError(RuntimeError):
    """허용되지 않은 상태 전이(예: 이미 sending/sent 인 호를 다시 보내기)."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _allowed(to: str, force: bool) -> tuple[str | None, ...]:
    if to not in EDGES:
        raise ValueError(f"알 수 없는 상태: {to}")
    return _FORCE_FROM if force else EDGES[to]


class LocalIssueStore:
    """`<root>/<issue_date>.json` 하나 = 한 호. 로컬 CLI(1-A) 한 프로세스용 — 프로세스 간 잠금은 없다."""

    def __init__(self, root: str) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, issue_date: str) -> Path:
        return self.root / f"{issue_date}.json"

    def get(self, issue_date: str) -> dict | None:
        p = self._path(issue_date)
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

    def transition(self, issue_date: str, to: str, *, force: bool = False, **fields: str) -> dict:
        cur = self.get(issue_date)
        status = cur["status"] if cur else None
        if status not in _allowed(to, force):
            raise TransitionError(f"{issue_date}: {status} → {to} 불가")
        item = {**(cur or {}), **fields, "issue_date": issue_date, "status": to, "updated_at": _now()}
        tmp = self._path(issue_date).with_suffix(".tmp")
        tmp.write_text(json.dumps(item, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self._path(issue_date))   # 같은 폴더 rename = 원자적 교체
        return item


class DynamoIssueStore:
    """DDB 백엔드 — 조건부 update_item 으로 전이. 테이블 리소스 주입(DI) → 테스트는 fake."""

    def __init__(self, table: Any) -> None:
        self._t = table

    def get(self, issue_date: str) -> dict | None:
        return self._t.get_item(Key={"issue_date": issue_date}, ConsistentRead=True).get("Item")

    def transition(self, issue_date: str, to: str, *, force: bool = False, **fields: str) -> dict:
        allowed = _allowed(to, force)
        names = {"#s": "status"}
        values: dict[str, str] = {":to": to}
        sets = ["#s = :to"]
        for i, (k, v) in enumerate({**fields, "updated_at": _now()}.items()):
            names[f"#f{i}"], values[f":f{i}"] = k, v
            sets.append(f"#f{i} = :f{i}")
        conds = ["attribute_not_exists(issue_date)"] if None in allowed else []
        froms = [s for s in allowed if s is not None]
        for i, s in enumerate(froms):
            values[f":a{i}"] = s
        if froms:
            conds.append(f"#s IN ({', '.join(f':a{i}' for i in range(len(froms)))})")
        try:
            resp = self._t.update_item(
                Key={"issue_date": issue_date}, UpdateExpression="SET " + ", ".join(sets),
                ConditionExpression=" OR ".join(conds), ExpressionAttributeNames=names,
                ExpressionAttributeValues=values, ReturnValues="ALL_NEW")
        except Exception as e:  # noqa: BLE001 — 조건 실패만 TransitionError 로, 나머지는 그대로
            if getattr(e, "response", {}).get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                raise TransitionError(f"{issue_date}: → {to} 불가(조건 실패)") from e
            raise
        return resp["Attributes"]


def issue_store_from_settings(settings: Any) -> LocalIssueStore | DynamoIssueStore:
    """데일리 stores 와 같은 backend 스위치(BACKEND=local|dynamo). WEEKLY_ISSUES_BACKEND 로 따로 둘 수 있다
    (BACKEND=dynamo 로 실제 원장을 읽으면서 호는 로컬 `.data/` 에만 — 1-A · 시험)."""
    if (os.getenv("WEEKLY_ISSUES_BACKEND", "") or settings.backend) == "dynamo":
        import boto3  # lazy — 로컬 경로는 boto3 무접촉
        kw: dict = {"region_name": settings.region} if settings.region else {}
        if getattr(settings, "ddb_endpoint_url", ""):
            kw["endpoint_url"] = settings.ddb_endpoint_url
        name = os.getenv("WEEKLY_ISSUES_TABLE", DEFAULT_TABLE)
        return DynamoIssueStore(boto3.resource("dynamodb", **kw).Table(name))
    return LocalIssueStore(os.getenv("WEEKLY_ISSUES_PATH", "./.data/weekly_issues"))
