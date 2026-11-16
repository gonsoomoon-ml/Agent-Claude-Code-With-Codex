#!/usr/bin/env python3
"""사례 5 — 운영이 뺀 쌍 중 같은 회사 공식 글끼리 걸린 것들의 매체·주소·길이 보기(읽기 전용).

    uv run python docs/work_note/Nov-2026/261114-duplicate-articles-7days/tools/case5_firstparty_drops.py

`scope_1028.py` 의 제외 목록(10-28 이후 21건)에서 제목으로 고른 3건(Gemini Omni 1.2 Flash · Gemini for healthcare ·
Gemini 4 Hydrogen)의 양쪽 글을 source-store 에서 찾는다. 어느 쪽이 빠졌는지는 `scope_1028.py` 출력과 함께 읽는다 —
결과 `case5-firstparty-drops.txt`.
"""
from __future__ import annotations

import boto3
from boto3.dynamodb.conditions import Attr

SUBS = ("Gemini Omni 1.2 Flash", "Gemini for healthcare", "Gemini 4 Hydrogen")
t = boto3.resource("dynamodb", region_name="us-east-1").Table("briefing-source-store")
cond = Attr("title").contains(SUBS[0])
for s in SUBS[1:]:
    cond = cond | Attr("title").contains(s)
kw = dict(FilterExpression=cond, ProjectionExpression="source_id, title, media, #u, fetched_at, #t",
          ExpressionAttributeNames={"#u": "url", "#t": "text"})
r = t.scan(**kw)
items = list(r["Items"])
while "LastEvaluatedKey" in r:
    r = t.scan(ExclusiveStartKey=r["LastEvaluatedKey"], **kw)
    items += r["Items"]
for i in sorted(items, key=lambda i: (str(i.get("title", ""))[:12], str(i.get("fetched_at", "")))):
    print(f"{str(i.get('fetched_at', ''))[:16]} [{i.get('media', '?')}] {len(str(i.get('text', '')))}자 · {str(i.get('title', ''))[:80]}\n    {i.get('url', '')}")
