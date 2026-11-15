#!/usr/bin/env python3
"""재보도 판정 실패(`same` 이 None → B 유지) 가 얼마나 자주 나는지 센다(읽기 전용 · Bedrock 호출 없음).

    uv run python docs/work_note/Nov-2026/261114-duplicate-articles-7days/tools/judge_fail_scan.py <폴더>

1) 저장된 판정 결과(<폴더> 안): same-site-measure.json(쌍마다 2회) · same-site-replay-*.json(쌍마다 1회)에서
   판정 실패 호출 수와 그 이유 문자열(`llm_rereport` 가 남긴 것 — "판정 JSON 없음: …" 또는 예외 이름).
2) 운영 로그(CloudWatch, v64 배포 2026-10-28 14:12Z 이후 전 사용자): `pipeline rereport` 줄을 종류별로 센다.
   운영의 `판정 실패 — 통과(fail-open)` 줄은 B 제목만 남기고 이유는 남기지 않는다(같은 run 에서는 쌍당 1번만 찍힌다).
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import boto3

folder = Path(sys.argv[1])
REGION = "us-east-1"
LOG_GROUP = "/aws/bedrock-agentcore/runtimes/briefing_agent-b9uh7rDAqL-DEFAULT"

print("== 1) 저장된 판정 결과")
tot_calls = tot_fail = 0
for path in sorted(folder.glob("same-site-*.json")):
    rows = json.load(open(path, encoding="utf-8"))
    calls, fails = 0, []
    for r in rows:
        vals = r["same"] if isinstance(r["same"], list) else [r["same"]]
        calls += len(vals)
        n = sum(v is None for v in vals)
        if n:
            fails.append((n, r))
    n_fail = sum(n for n, _ in fails)
    tot_calls += calls
    tot_fail += n_fail
    print(f"{path.name}: 쌍 {len(rows)} · 호출 {calls} · 판정 실패 호출 {n_fail}(쌍 {len(fails)})")
    for n, r in fails:
        print(f"   {r['run_date']} 실패 {n}회 [{r['b_media'][:14]}] {r['b_title'][:60]}\n"
              f"{'':14}← [{r['a_media'][:14]}] {r['a_title'][:60]}\n{'':14}이유: {r['reason'][:150]}")
print(f"합계: 호출 {tot_calls} · 판정 실패 {tot_fail}")

print("\n== 2) 운영 로그(2026-10-28 14:12Z 이후)")
logs = boto3.client("logs", region_name=REGION)
start = int(datetime(2026, 10, 28, 14, 12, tzinfo=timezone.utc).timestamp() * 1000)
evs, tok = [], None
while True:
    kw = dict(logGroupName=LOG_GROUP, filterPattern='"pipeline rereport"', startTime=start)
    if tok:
        kw["nextToken"] = tok
    resp = logs.filter_log_events(**kw)
    evs += resp.get("events", [])
    tok = resp.get("nextToken")
    if not tok:
        break


def kind_of(body: str) -> str:
    for label in ("재보도 단계 실패", "판정 실패", "재보도 제외", "새 판정"):
        if label in body:
            return label
    return "기타"


uniq: dict[tuple[str, str], str] = {}   # (날짜, 사용자 id 뒤 본문) → 종류 — 같은 줄이 여러 번 실려도 한 번만
days = set()
for e in evs:
    day = datetime.fromtimestamp(e["timestamp"] / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
    days.add(day)
    m = e["message"]
    i = m.find("pipeline rereport]")
    body = m[i + len("pipeline rereport]"):].split('","attributes"')[0].strip() if i != -1 else m.strip()
    body = body.split(": ", 1)[1] if ": " in body else body   # 사용자 id 떼기 — 판정 실패는 run 당 첫 사용자에게만 찍힌다
    uniq[(day, body[:160])] = kind_of(body)
kinds = Counter(uniq.values())
print(f"로그 이벤트 {len(evs)} · 줄이 있던 날 {len(days)}일({min(days) if days else '-'} ~ {max(days) if days else '-'})")
print(f"줄 종류(날짜·본문 기준 중복 제거): {dict(kinds)}")
for (day, body), kind in sorted(uniq.items()):
    if kind in ("판정 실패", "재보도 단계 실패", "기타"):
        print(f"   {day} {kind}: {body[:150]}")
