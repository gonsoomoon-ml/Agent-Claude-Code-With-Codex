#!/usr/bin/env python3
"""사례 4 — 관리자에게 나간 카드 중 제목에 'Fable 5.2' 또는 'Mythos 5.2' 가 든 것 전부(전 기간, 읽기 전용).

    uv run python docs/work_note/Nov-2026/261114-duplicate-articles-7days/tools/case4_all_fable52.py

Anthropic 의 출시 발표 글 자체가 수집·발송된 적이 있는지 본다 — 결과 `case4-all-fable52.txt`.
"""
from __future__ import annotations

import boto3
from boto3.dynamodb.conditions import Attr

ADMIN = "445814b8-5001-70a6-84a6-6c010ac347ba"
ddb = boto3.resource("dynamodb", region_name="us-east-1")


def scan(t, **kw):
    resp = t.scan(**kw)
    out = list(resp["Items"])
    while "LastEvaluatedKey" in resp:
        resp = t.scan(ExclusiveStartKey=resp["LastEvaluatedKey"], **kw)
        out += resp["Items"]
    return out


rows = scan(ddb.Table("briefing-ledger"),
            FilterExpression=Attr("user_id").eq(ADMIN) & (Attr("headline").contains("Fable 5.2") | Attr("headline").contains("Mythos 5.2")))
meta = {}
for r in rows:
    m = ddb.Table("briefing-source-store").get_item(
        Key={"source_id": r["source_id"]}, ProjectionExpression="media, #u", ExpressionAttributeNames={"#u": "url"}).get("Item", {})
    meta[r["source_id"]] = m
print(f"원장 행 {len(rows)}건")
for r in sorted(rows, key=lambda r: r["run_date"]):
    m = meta[r["source_id"]]
    print(f"{r['run_date']} {r.get('decision'):<10} [{m.get('media', '?')}] {r.get('headline', '')[:90]}\n    {m.get('url', '')}")

# 수집은 됐지만 발송되지 않은 Anthropic 쪽 글이 있는지 — source-store 제목으로 본다.
src = scan(ddb.Table("briefing-source-store"),
           FilterExpression=Attr("title").contains("Fable 5.2") | Attr("title").contains("Mythos 5.2"),
           ProjectionExpression="source_id, title, media, #u, fetched_at", ExpressionAttributeNames={"#u": "url"})
sent_ids = {r["source_id"] for r in rows}
print(f"\nsource-store 에서 제목에 'Fable 5.2'/'Mythos 5.2' 가 든 글 {len(src)}건")
for s in sorted(src, key=lambda s: str(s.get("fetched_at", ""))):
    mark = "발송" if s["source_id"] in sent_ids else "미발송"
    print(f"{str(s.get('fetched_at', ''))[:10]} {mark} [{s.get('media', '?')}] {s.get('title', '')[:90]}\n    {s.get('url', '')}")
