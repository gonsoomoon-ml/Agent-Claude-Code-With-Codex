#!/usr/bin/env python3
"""Gemini 4 Hydrogen 건 진단 — 읽기 전용. 빠진 글(원 발표)과 남은 글(Search)이 서로 어떻게 인용하는지."""
from __future__ import annotations

from datetime import datetime, timezone

import boto3
from boto3.dynamodb.conditions import Attr

from briefing.core.article_identity import cite_key
from briefing.core.retrieval.sources import _cited_keys, _http_get

REGION = "us-east-1"
ddb = boto3.resource("dynamodb", region_name=REGION)
t = ddb.Table("briefing-source-store")
kw = dict(FilterExpression=Attr("title").contains("Hydrogen"),
          ProjectionExpression="source_id, #u, title, media, fetched_at", ExpressionAttributeNames={"#u": "url"})
resp = t.scan(**kw)
items = list(resp["Items"])
while "LastEvaluatedKey" in resp:
    resp = t.scan(ExclusiveStartKey=resp["LastEvaluatedKey"], **kw)
    items += resp["Items"]
keys = {}
for it in sorted(items, key=lambda i: str(i.get("fetched_at"))):
    k = cite_key(it["url"])
    keys[k] = it
    print(f"{str(it.get('fetched_at'))[:25]:25} [{it.get('media')}] {it.get('title')[:70]}\n    {it['url']}  sid={it['source_id'][:12]}")
print()
for k, it in keys.items():
    html = _http_get(it["url"])
    cited = _cited_keys(html, it["url"]) if html else ()
    hits = [c for c in cited if c in keys]
    print(f"[{it.get('media')}] {it.get('title')[:50]} → 인용 {len(cited)}개, 이 묶음 안 인용: {hits}")

# 원장: 이 묶음 기사들이 누구에게 언제 나갔나(관리자)
led = ddb.Table("briefing-ledger")
ADMIN = "445814b8-5001-70a6-84a6-6c010ac347ba"
for it in items:
    r = led.scan(FilterExpression=Attr("source_id").eq(it["source_id"]) & Attr("user_id").eq(ADMIN),
                 ProjectionExpression="run_date, decision")
    rows = r["Items"]
    while "LastEvaluatedKey" in r:
        r = led.scan(FilterExpression=Attr("source_id").eq(it["source_id"]) & Attr("user_id").eq(ADMIN),
                     ProjectionExpression="run_date, decision", ExclusiveStartKey=r["LastEvaluatedKey"])
        rows += r["Items"]
    print(f"  원장(관리자) {it.get('title')[:40]}: {[(x['run_date'], x['decision']) for x in rows]}")

logs = boto3.client("logs", region_name=REGION)
start = int(datetime(2026, 11, 12, 19, 0, tzinfo=timezone.utc).timestamp() * 1000)
end = int(datetime(2026, 11, 13, 6, 0, tzinfo=timezone.utc).timestamp() * 1000)
resp = logs.filter_log_events(logGroupName="/aws/bedrock-agentcore/runtimes/briefing_agent-b9uh7rDAqL-DEFAULT",
                              filterPattern='"pipeline rereport" "Hydrogen"', startTime=start, endTime=end, limit=3)
for e in resp.get("events", [])[:1]:
    m = e["message"]
    i = m.find("pipeline rereport")
    print("\nLOG:", m[i:i + 420])
