#!/usr/bin/env python3
"""새어 나간 후보 쌍 진단 — 읽기 전용. B 페이지를 다시 받아 인용 키를 뽑고, A 의 cite_key 와 맞는지 본다.

사용: uv run python leak_diag.py <cards.tsv>
"""
from __future__ import annotations

import sys

import boto3

from briefing.core.article_identity import cite_key
from briefing.core.retrieval.sources import _cited_keys, _http_get

REGION = "us-east-1"
ADMIN = "445814b8-5001-70a6-84a6-6c010ac347ba"

cards = [ln.rstrip("\n").split("\t") for ln in open(sys.argv[1])]
# (run_date, decision, media, fetched, title, headline, url, sid12)


def find(sub: str):
    hits = [c for c in cards if sub in c[4]]
    return hits[0] if hits else None


PAIRS = [  # (A 제목 조각 | None, B 제목 조각)
    ("The components of agent memory", "에이전트 메모리, 많이 저장하기보다"),
    ("Gemini 4 Carbon is now available", "Gemini 4 Carbon arrives just in time"),
    ("Google Search gets a major upgrade with Gemini 4 Hydrogen", "Google's Gemini 4 Hydrogen outscores"),
    ("Claude for Manufacturing: AI plugin", "Anthropic's Claude for Manufacturing plugs"),
    (None, "Claude Fable 5.2 and Mythos 5.2 cement"),
    (None, "Anthropic, Claude Fable 5.2와 Mythos 5.2 출시"),
    ("Thinking Machines' Inkling 2 Small drops", "Thinking Machines Lab, 활성 17B"),
    (None, "Claude Meetings lets Anthropic"),
    (None, "Anthropic says AI is eroding Nvidia"),
    (None, "Google DeepMind's Gemini Robotics 2.5"),
    (None, "OpenAI, 승인된 보안 조직 전용 GPT-6 Cyber"),
    (None, "METR의 Anthropic 내부 AI R&D"),
    (None, "Nvidia's model GR00T 2"),
    (None, "OpenAI enters the cybersecurity market"),
    (None, "OpenAI rebuilt AI shopping"),
    (None, "Anthropic's Fable 5.2 completes 41 percent"),
]

# 관리자에게 지난 90일 보낸 모든 기사 URL 의 cite_key → (run_date, media, title)
ddb = boto3.resource("dynamodb", region_name=REGION)
t = ddb.Table("briefing-ledger")
resp = t.query(KeyConditionExpression="user_id = :u", ExpressionAttributeValues={":u": ADMIN})
rows = list(resp["Items"])
while "LastEvaluatedKey" in resp:
    resp = t.query(KeyConditionExpression="user_id = :u", ExpressionAttributeValues={":u": ADMIN},
                   ExclusiveStartKey=resp["LastEvaluatedKey"])
    rows += resp["Items"]
rows = [r for r in rows if r.get("decision") in ("PUBLISH", "QUARANTINE") and r["run_date"] >= "2026-08-10"]
sids = sorted({r["source_id"] for r in rows})
first_run = {}
for r in sorted(rows, key=lambda r: r["run_date"]):
    first_run.setdefault(r["source_id"], r["run_date"])
meta = {}
ss = ddb.meta.client
for i in range(0, len(sids), 100):
    keys = [{"source_id": s} for s in sids[i:i + 100]]
    req = {"briefing-source-store": {"Keys": keys, "ProjectionExpression": "source_id, #u, title, media",
                                     "ExpressionAttributeNames": {"#u": "url"}}}
    while req:
        out = ss.batch_get_item(RequestItems=req)
        for it in out["Responses"].get("briefing-source-store", []):
            meta[it["source_id"]] = it
        req = out.get("UnprocessedKeys") or None
sent = {}
for sid, m in meta.items():
    k = cite_key(m.get("url", ""))
    if k:
        sent[k] = (first_run[sid], m.get("media", ""), m.get("title", ""), m.get("url", ""))
print(f"관리자 90일 발송 기사 {len(meta)} · 인용 키 {len(sent)}\n")

for a_sub, b_sub in PAIRS:
    b = find(b_sub)
    if not b:
        print(f"?? B 없음: {b_sub}\n")
        continue
    a = find(a_sub) if a_sub else None
    html = _http_get(b[6])
    cited = _cited_keys(html, b[6]) if html else ()
    print(f"B {b[0][5:]} [{b[2]}] {b[4][:70]}\n   {b[6]}")
    if a:
        ak = cite_key(a[6])
        print(f" A {a[0][5:]} [{a[2]}] {a[4][:60]}\n   {a[6]}\n   A 키 = {ak} → B 인용에 {'있음' if ak in cited else '없음'}")
    hits = [(k, sent[k]) for k in cited if k in sent]
    print(f"   B 인용 키 {len(cited)}개 · 발송 기사와 일치 {len(hits)}")
    for k, (rd, media, title, _u) in hits:
        print(f"     ✓ {k}  ← {rd} [{media}] {title[:50]}")
    interesting = [k for k in cited if any(h in k for h in ("anthropic.com", "claude.com", "deepmind.google", "blog.google",
                                                              "openai.com", "thinkingmachines", "metr.org", "nvidia.com",
                                                              "research.google", "developers.googleblog", "ai.meta.com",
                                                              "huggingface.co/blog"))]
    for k in interesting[:8]:
        if k not in sent:
            print(f"     · {k}")
    print()
