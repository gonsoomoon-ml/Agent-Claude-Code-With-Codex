#!/usr/bin/env python3
"""사례 4(Fable 5.2·Mythos 5.2 출시 소식 두 건) — 두 카드의 원장 행과 원문 앞부분 보기(읽기 전용).

    uv run python docs/work_note/Nov-2026/261114-duplicate-articles-7days/tools/case4_cards.py

두 글이 같은 시각인지(겹치는 내용·다른 내용) 눈으로 보기 위한 덤프다 — 결과 `case4-cards.txt`.
"""
from __future__ import annotations

import boto3
from boto3.dynamodb.conditions import Attr

from briefing.core.config import load_settings
from briefing.core.stores.dynamo import source_store_from_settings

ADMIN = "445814b8-5001-70a6-84a6-6c010ac347ba"
WANT = ("cement Anthropic", "Fable 5.2와 Mythos 5.2 출시")
HEAD = 900   # 저장소에 남기는 발췌는 짧게 — 시각 비교에 필요한 요점 단락까지만

t = boto3.resource("dynamodb", region_name="us-east-1").Table("briefing-ledger")
kw = {"FilterExpression": Attr("user_id").eq(ADMIN) & Attr("run_date").between("2026-11-10", "2026-11-11")}
resp = t.scan(**kw)
items = list(resp["Items"])
while "LastEvaluatedKey" in resp:
    resp = t.scan(ExclusiveStartKey=resp["LastEvaluatedKey"], **kw)
    items += resp["Items"]

store = source_store_from_settings(load_settings())
for r in sorted(items, key=lambda r: r["run_date"]):
    if not any(w in str(r.get("headline", "")) + str(r.get("title", "")) for w in WANT):
        continue
    print("=" * 100)
    for k in sorted(r):
        if k in ("user_id",):
            continue
        print(f"{k}: {str(r[k])[:900]}")
    src = store.get_source(r["source_id"])
    print(f"--- 원문 제목: {src.title}\n--- 원문 길이: {len(src.text)}자\n--- 원문 앞 {HEAD}자:\n{src.text[:HEAD]}")
