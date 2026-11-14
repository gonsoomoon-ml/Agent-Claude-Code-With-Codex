#!/usr/bin/env python3
"""마무리 확인(읽기 전용): ① 사용자별 발송 기사 집합이 관리자와 같은가 ② 링크로 걸리지 않은 닮은 쌍 3개를 판정자에 직접.

    uv run python final_checks.py

② 는 "판정자에게 물으면 같은 발표라고 하는가"만 본다 — 운영은 링크가 없으면 판정하지 않는다(설계).
"""
from __future__ import annotations

from collections import defaultdict

import boto3
from boto3.dynamodb.conditions import Attr

from briefing.core.config import load_settings
from briefing.core.retrieval.relevance_bedrock import make_bedrock_rereport
from briefing.core.stores.dynamo import source_store_from_settings

SINCE, UNTIL = "2026-11-07", "2026-11-13"
ADMIN = "445814b8-5001-70a6-84a6-6c010ac347ba"
ddb = boto3.resource("dynamodb", region_name="us-east-1")


def scan(t, **kw):
    r = t.scan(**kw)
    out = list(r["Items"])
    while "LastEvaluatedKey" in r:
        r = t.scan(ExclusiveStartKey=r["LastEvaluatedKey"], **kw)
        out += r["Items"]
    return out


rows = scan(ddb.Table("briefing-ledger"), FilterExpression=Attr("run_date").between(SINCE, UNTIL))
sets = defaultdict(set)
for r in rows:
    if r.get("decision") in ("PUBLISH", "QUARANTINE"):
        sets[(r["run_date"], r["user_id"])].add(r["source_id"])
users = sorted({u for _, u in sets})
print(f"사용자 {len(users)}명")
for rd in sorted({d for d, _ in sets}):
    base = sets.get((rd, ADMIN), set())
    diff = {u[:14]: (len(sets[(rd, u)] - base), len(base - sets[(rd, u)])) for u in users
            if (rd, u) in sets and sets[(rd, u)] != base}
    print(f"{rd}: 관리자 {len(base)}장 · 관리자와 다른 사용자 {diff or '없음'}")

s = load_settings()
store = source_store_from_settings(s)
t = ddb.Table("briefing-source-store")
judge = make_bedrock_rereport(s)


def src(sub: str):
    items = scan(t, FilterExpression=Attr("title").contains(sub), ProjectionExpression="source_id, title, media")
    assert items, f"source-store 에 없음: {sub}"   # 같은 제목이 여러 건(다시 받은 동결본)이면 첫 건
    return store.get_source(items[0]["source_id"])


for label, a_sub, b_sub in [
    ("Hydrogen 실제 받은 쌍(Search → Decoder)", "Google Search gets a major upgrade with Gemini 4 Hydrogen", "Google's Gemini 4 Hydrogen outscores"),
    ("Claude Sheets 두 글(같은 사이트)", "Claude Whiteboards, Claude Sheets, and Claude Data", "Working with Claude Sheets, Whiteboards"),
    ("GPT-6 Cyber 한국어 소개 → Decoder Daybreak", "OpenAI, 승인된 보안 조직 전용 GPT-6 Cyber", "OpenAI enters the cybersecurity market"),
]:
    a, b = src(a_sub), src(b_sub)
    print(f"\n== {label}")
    for i in range(2):
        v = judge(a.text, b.text)
        print(f"   {i + 1}) same={v.same} | {v.reason[:230]}")
