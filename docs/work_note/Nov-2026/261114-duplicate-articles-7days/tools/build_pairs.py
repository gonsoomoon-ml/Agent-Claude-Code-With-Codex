#!/usr/bin/env python3
"""판정 실험용 쌍 목록 만들기(읽기 전용) → pairs.json

① 발송된 기사끼리 링크로 걸리는 쌍(2026-10-21 ~ 11-13): 운영과 같은 drop_rereports 를 "항상 다름"으로 답하는
   기록용 판정자로 돌려 걸린 쌍을 전부 모은다(판정 호출 없음, 페이지만 다시 받는다).
② 운영이 실제로 제외한 쌍: CloudWatch `pipeline rereport` 줄의 제목 앞부분으로 source-store 에서 찾는다.
라벨(정답)은 사람이 읽고 정한 것 — 아래 KEEP_SUBSTR / MISS_SUBSTR / SKIP_SUBSTR.
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone

import boto3

from briefing.core.article_identity import published_keys
from briefing.core.config import DEFAULT_DEDUP_LOOKBACK_DAYS, load_settings
from briefing.core.rereport_dedup import drop_rereports
from briefing.core.retrieval.rereport import RereportVerdict
from briefing.core.retrieval.sources import CATALOG, _cited_keys, _http_get
from briefing.core.stores.dynamo import ledger_from_settings, source_store_from_settings

OUT = sys.argv[1]
ADMIN = "445814b8-5001-70a6-84a6-6c010ac347ba"
SINCE, UNTIL, LAUNCH = "2026-10-21", "2026-11-13", "2026-10-28"
LOG_GROUP = "/aws/bedrock-agentcore/runtimes/briefing_agent-b9uh7rDAqL-DEFAULT"

# 게이트 주간(10-21~27)에서 "유지"가 정답인 B 제목 조각(스펙 §7) — 나머지 게이트 쌍은 "제외"가 정답
GATE_KEEP = ("gitai", "AAIF에 Agent Skills", "AI Quest")
# 출시 뒤 발송된 쌍 중 "제외"가 정답인 B(이번 조사에서 놓친 것으로 확인)
MISS = ("에이전트 메모리, 많이 저장하기보다", "모델 통합 계약")
# 경계 사례 — 채점에서 뺀다
SKIP = ("Mistral Large 4 가중치 공개", "Introducing Gemini 4 Hydrogen")

settings = load_settings()
ledger, store = ledger_from_settings(settings), source_store_from_settings(settings)
category = {s.name: s.category for s in CATALOG}
rows = ledger.query(ADMIN)


def cited_of(fs):
    html = _http_get(fs.url)
    return _cited_keys(html, fs.url) if html else ()


pairs: list[dict] = []
meta_memo: dict = {}
d, end = date.fromisoformat(SINCE), date.fromisoformat(UNTIL)
while d <= end:
    rd = d.isoformat()
    d += timedelta(days=1)
    sids = sorted({r["source_id"] for r in rows if r.get("run_date") == rd and r.get("decision") in ("PUBLISH", "QUARANTINE")})
    survivors = []
    for sid in sids:
        try:
            fs = store.get_source(sid)
        except KeyError:
            continue
        survivors.append((fs, category.get(fs.media, "")))
    if not survivors:
        continue
    with ThreadPoolExecutor(8) as ex:
        cited = {fs.source_id: c for (fs, _), c in zip(survivors, ex.map(lambda x: cited_of(x[0]), survivors)) if c}
    sent_index: dict[str, str] = {}
    published_keys(ledger, store, ADMIN, rd, DEFAULT_DEDUP_LOOKBACK_DAYS, meta_memo, url_index=sent_index)
    memo: dict = {}
    drop_rereports(survivors, cited=cited, sent_index=sent_index, get_source=store.get_source,
                   judge=lambda a, b: RereportVerdict(False, "record"), memo=memo)
    by_sid = {fs.source_id: fs for fs, _ in survivors}
    for a_sid, b_sid in memo:
        a, b = by_sid.get(a_sid) or store.get_source(a_sid), by_sid[b_sid]
        if any(s in b.title for s in SKIP):
            label = None
        elif rd < LAUNCH:
            label = not any(s in b.title for s in GATE_KEEP)
        else:
            label = any(s in b.title for s in MISS)
        pairs.append(dict(group="gate" if rd < LAUNCH else "sent", run_date=rd, a_sid=a_sid, b_sid=b_sid,
                          a_title=a.title, b_title=b.title, a_media=a.media, b_media=b.media, expect=label))
    print(f"{rd}: 생존자 {len(survivors)} · 걸린 쌍 {len(memo)}", flush=True)

# ② 운영이 제외한 쌍
ddb = boto3.resource("dynamodb", region_name="us-east-1")
t = ddb.Table("briefing-source-store")
kw = dict(ProjectionExpression="source_id, title, media, fetched_at")
r = t.scan(**kw)
metas = list(r["Items"])
while "LastEvaluatedKey" in r:
    r = t.scan(ExclusiveStartKey=r["LastEvaluatedKey"], **kw)
    metas += r["Items"]
sent_sids = {r["source_id"] for r in rows}
logs = boto3.client("logs", region_name="us-east-1")
start = int(datetime(2026, 10, 28, 19, 0, tzinfo=timezone.utc).timestamp() * 1000)
evs, tok = [], None
while True:
    q = dict(logGroupName=LOG_GROUP, filterPattern=f'"pipeline rereport" "{ADMIN}"', startTime=start)
    if tok:
        q["nextToken"] = tok
    x = logs.filter_log_events(**q)
    evs += x.get("events", [])
    tok = x.get("nextToken")
    if not tok:
        break
seen = set()
for e in evs:
    m = re.search(r"재보도 제외 — (.+?) ← (.+?) \(", e["message"])
    if not m:
        continue
    bp, ap = m.group(1).strip(), m.group(2).strip()
    if (bp, ap) in seen:
        continue
    seen.add((bp, ap))
    day = datetime.fromtimestamp(e["timestamp"] / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
    bs = [x for x in metas if (x.get("title") or "").startswith(bp) and x["source_id"] not in sent_sids]
    as_ = [x for x in metas if (x.get("title") or "").startswith(ap) and x["source_id"] in sent_sids]
    if not bs or not as_:
        print(f"!! 못 찾음 B={len(bs)} A={len(as_)}: {bp[:40]} ← {ap[:40]}")
        continue
    b, a = max(bs, key=lambda x: str(x.get("fetched_at"))), max(as_, key=lambda x: str(x.get("fetched_at")))
    label = None if any(s in b["title"] for s in SKIP) else True
    pairs.append(dict(group="dropped", run_date=day, a_sid=a["source_id"], b_sid=b["source_id"], a_title=a["title"],
                      b_title=b["title"], a_media=a.get("media", ""), b_media=b.get("media", ""), expect=label))

json.dump(pairs, open(OUT, "w"), ensure_ascii=False, indent=1)
print(Counter((p["group"], p["expect"]) for p in pairs))
