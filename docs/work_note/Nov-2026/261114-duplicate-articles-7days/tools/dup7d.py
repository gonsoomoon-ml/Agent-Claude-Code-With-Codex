#!/usr/bin/env python3
"""최근 7 run(2026-11-07 ~ 11-13) 중복 점검 — 읽기 전용.

1) sent-log: run_date 별 사용자·발행 수
2) 신원 중복(PUBLISH + QUARANTINE 모두 — N5 로 ⚠ 카드도 발송됨): 같은 사용자에게 같은 기사가 두 번
3) CloudWatch: pipeline rereport / pipeline dedup 줄
4) 관리자 발송 카드 목록 덤프(run_date·매체·제목·URL) → cards.tsv (주제 군집 눈검사용)
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone

import boto3

from briefing.core.article_identity import identity_keys

REGION = "us-east-1"
SINCE, UNTIL = "2026-11-07", "2026-11-13"
ADMIN = "445814b8-5001-70a6-84a6-6c010ac347ba"
LOG_GROUP = "/aws/bedrock-agentcore/runtimes/briefing_agent-b9uh7rDAqL-DEFAULT"
OUT = sys.argv[1] if len(sys.argv) > 1 else "."


def scan(t, **kw):
    resp = t.scan(**kw)
    out = list(resp["Items"])
    while "LastEvaluatedKey" in resp:
        resp = t.scan(ExclusiveStartKey=resp["LastEvaluatedKey"], **kw)
        out += resp["Items"]
    return out


ddb = boto3.resource("dynamodb", region_name=REGION)
sent = [s for s in scan(ddb.Table("briefing-sent-log")) if SINCE <= s.get("run_date", "") <= UNTIL]
print("== 1) sent-log ==")
by_day = defaultdict(list)
for s in sent:
    by_day[s["run_date"]].append(s)
for rd in sorted(by_day):
    rows = by_day[rd]
    st = Counter(r.get("status") for r in rows)
    pub = sorted(int(r.get("published", 0)) for r in rows)
    print(f"{rd}: {len(rows)}건 status={dict(st)} published={pub}")

meta = {i["source_id"]: i for i in scan(ddb.Table("briefing-source-store"),
                                        ProjectionExpression="source_id, #u, title, media, fetched_at",
                                        ExpressionAttributeNames={"#u": "url"})}
ledger = scan(ddb.Table("briefing-ledger"))
sent_keys = {(s["user_id"], s["run_date"]) for s in scan(ddb.Table("briefing-sent-log")) if s.get("status") == "sent"}
rows = [r for r in ledger if r.get("decision") in ("PUBLISH", "QUARANTINE") and (r["user_id"], r["run_date"]) in sent_keys]
print(f"\n원장 발송 행(PUBLISH+QUARANTINE, 전 기간): {len(rows)}")


def keys(sid):
    m = meta.get(sid)
    if not m:
        return frozenset({f"sid:{sid}"})
    return identity_keys(source_id=sid, url=m.get("url", ""), title=m.get("title", ""), media=m.get("media", ""))


print("\n== 2) 신원 중복(같은 사용자·같은 기사 두 번, 90일 안) ==")
per_user = defaultdict(list)
for r in rows:
    per_user[r["user_id"]].append(r)
dups = []
for uid, rs in per_user.items():
    rs.sort(key=lambda r: r["run_date"])
    seen: dict[str, tuple[str, str]] = {}
    for r in rs:
        ks = keys(r["source_id"])
        hit = next(((k, seen[k]) for k in ks if k in seen and seen[k][0] < r["run_date"]), None)
        if hit and SINCE <= r["run_date"] <= UNTIL:
            dups.append((r["run_date"], uid[:12], r.get("decision"), hit[0][:70], hit[1][0], r.get("headline", "")[:50]))
        for k in ks:
            seen.setdefault(k, (r["run_date"], r["source_id"]))
print(f"중복 {len(dups)}장")
for d in sorted(dups):
    print("  ", d)

print("\n== 2b) 같은 run 안 같은 기사(사용자별) ==")
same_run = 0
for uid, rs in per_user.items():
    by_run = defaultdict(list)
    for r in rs:
        if SINCE <= r["run_date"] <= UNTIL:
            by_run[r["run_date"]].append(r)
    for rd, rr in by_run.items():
        c = Counter()
        for r in rr:
            for k in keys(r["source_id"]):
                if not k.startswith("sid:"):
                    c[k] += 1
        for k, n in c.items():
            if n > 1:
                same_run += 1
                print("  ", rd, uid[:12], n, k[:80])
print(f"같은 run 중복 키 {same_run}")

print("\n== 3) CloudWatch ==")
logs = boto3.client("logs", region_name=REGION)
start = int(datetime(2026, 11, 7, 19, 0, tzinfo=timezone.utc).timestamp() * 1000)
for pat in ('"pipeline rereport"', '"pipeline dedup"'):
    evs, tok = [], None
    while True:
        kw = dict(logGroupName=LOG_GROUP, filterPattern=pat, startTime=start)
        if tok:
            kw["nextToken"] = tok
        resp = logs.filter_log_events(**kw)
        evs += resp.get("events", [])
        tok = resp.get("nextToken")
        if not tok:
            break
    print(f"-- {pat}: {len(evs)}줄")
    uniq = Counter()
    for e in evs:
        day = datetime.fromtimestamp(e["timestamp"] / 1000, tz=timezone.utc).strftime("%m-%d")
        msg = e["message"].strip()
        i = msg.find("pipeline")
        body = msg[i:]
        # 사용자 id 부분을 지워 같은 쌍을 하나로
        j = body.find(": ")
        uniq[(day, body[j + 2:] if j != -1 else body)] += 1
    for (day, body), n in sorted(uniq.items()):
        print(f"  {day} x{n}  {body[:230]}")

print("\n== 4) 관리자 카드 덤프 ==")
adm = sorted((r for r in rows if r["user_id"] == ADMIN and SINCE <= r["run_date"] <= UNTIL),
             key=lambda r: (r["run_date"], r["source_id"]))
with open(f"{OUT}/cards.tsv", "w") as f:
    for r in adm:
        m = meta.get(r["source_id"], {})
        f.write("\t".join([r["run_date"], r.get("decision", ""), m.get("media", "?"), str(m.get("fetched_at", ""))[:10],
                           (m.get("title", "") or "").replace("\t", " "), r.get("headline", "").replace("\t", " "),
                           m.get("url", ""), r["source_id"][:12]]) + "\n")
print(f"관리자 카드 {len(adm)}장 → {OUT}/cards.tsv | 날짜별 {dict(sorted(Counter(r['run_date'] for r in adm).items()))}")
json.dump({"n": len(adm)}, open(f"{OUT}/summary.json", "w"))
