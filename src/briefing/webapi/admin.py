# src/briefing/webapi/admin.py
"""admin — 운영 모니터링 읽기 API(admin 전용). role 은 여기(require_admin)서만 집행된다.

GET /admin/emails: briefing-sent-log 을 Scan(작은 테이블) → 발송 이메일 리스트(비용·시간·기사수).
cost_usd 는 DDB Decimal → JSON float 환원. v1=Scan(GSI 불필요).
"""
from __future__ import annotations

import os
from decimal import Decimal

from fastapi import APIRouter, Request

from .authz import require_admin

router = APIRouter()


def _sent_log_table():
    """운영 boto3 Table(lazy). 테스트는 monkeypatch 로 fake 주입."""
    import boto3
    region = os.getenv("AWS_REGION", "us-east-1")
    name = os.getenv("SENT_LOG_TABLE", "briefing-sent-log")
    return boto3.resource("dynamodb", region_name=region).Table(name)


def _to_json(item: dict) -> dict:
    """DDB item → JSON 안전(Decimal→float/int)."""
    out = {}
    for k, v in item.items():
        out[k] = float(v) if isinstance(v, Decimal) else v
    return out


@router.get("/admin/emails")
def list_emails(req: Request, date: str | None = None, limit: int = 200) -> dict:
    require_admin(req)   # 403 if not admin — role 집행 단일 지점
    table = _sent_log_table()
    kw: dict = {}
    if date:
        from boto3.dynamodb.conditions import Attr
        kw["FilterExpression"] = Attr("run_date").eq(date)
    # 계측 이전 dedup-only 행({user_id,run_date})은 audit 필드가 없다 → 제외(대시보드=계측 발송만).
    items = [_to_json(i) for i in table.scan(**kw).get("Items", []) if "sent_at" in i]
    items.sort(key=lambda x: x.get("sent_at", ""), reverse=True)
    items = items[:limit]
    total_cost = round(sum(float(i.get("cost_usd", 0)) for i in items), 4)
    durs = [i.get("duration_ms", 0) for i in items]
    totals = {"count": len(items), "cost_usd": total_cost,
              "avg_duration_ms": int(sum(durs) / len(durs)) if durs else 0}
    return {"emails": items, "totals": totals}
