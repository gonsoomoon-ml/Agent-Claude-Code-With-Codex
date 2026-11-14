#!/usr/bin/env python3
"""범위 확인(읽기 전용): 출시(10-28) 이후 재보도 제외 로그 전체(관리자 기준, 쌍 단위) + 두 원문의 발송일."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone

import boto3
from boto3.dynamodb.conditions import Attr, Key

REGION = "us-east-1"
ADMIN = "445814b8-5001-70a6-84a6-6c010ac347ba"
LOG_GROUP = "/aws/bedrock-agentcore/runtimes/briefing_agent-b9uh7rDAqL-DEFAULT"
logs = boto3.client("logs", region_name=REGION)
start = int(datetime(2026, 10, 28, 19, 0, tzinfo=timezone.utc).timestamp() * 1000)
evs, tok = [], None
while True:
    kw = dict(logGroupName=LOG_GROUP, filterPattern=f'"pipeline rereport" "{ADMIN}"', startTime=start)
    if tok:
        kw["nextToken"] = tok
    r = logs.filter_log_events(**kw)
    evs += r.get("events", [])
    tok = r.get("nextToken")
    if not tok:
        break
uniq = Counter()
for e in evs:
    day = datetime.fromtimestamp(e["timestamp"] / 1000, tz=timezone.utc).strftime("%m-%d")
    m = e["message"]
    i = m.find(ADMIN)
    body = m[i + len(ADMIN) + 2:]
    body = body.split('","attributes"')[0].strip()
    uniq[(day, body[:150])] += 1
kinds = Counter()
for (day, body), n in sorted(uniq.items()):
    kind = "제외" if "재보도 제외" in body else ("실패" if "판정 실패" in body else "기타")
    kinds[kind] += 1
    print(f"{day} {kind} {body[:150]}")
print(f"\n관리자 기준 줄 종류: {dict(kinds)}")

ddb = boto3.resource("dynamodb", region_name=REGION)
ss, led = ddb.Table("briefing-source-store"), ddb.Table("briefing-ledger")
rows = []
r = led.query(KeyConditionExpression=Key("user_id").eq(ADMIN))
rows += r["Items"]
while "LastEvaluatedKey" in r:
    r = led.query(KeyConditionExpression=Key("user_id").eq(ADMIN), ExclusiveStartKey=r["LastEvaluatedKey"])
    rows += r["Items"]
for sub in ("Transformers Model Integration Contracts", "모델 통합 계약", "The components of agent memory", "에이전트 메모리, 많이 저장하기보다"):
    kw = dict(FilterExpression=Attr("title").contains(sub), ProjectionExpression="source_id, title, media")
    x = ss.scan(**kw)
    items = list(x["Items"])
    while "LastEvaluatedKey" in x:
        x = ss.scan(ExclusiveStartKey=x["LastEvaluatedKey"], **kw)
        items += x["Items"]
    for it in items:
        sent = sorted((q["run_date"], q.get("decision")) for q in rows if q["source_id"] == it["source_id"])
        print(f"[{it['media']}] {it['title'][:60]} → {sent}")
