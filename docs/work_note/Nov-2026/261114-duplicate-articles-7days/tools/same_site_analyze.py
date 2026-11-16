#!/usr/bin/env python3
"""same_site_measure.py 결과 분석 — 후보 쌍을 B 매체 분야·기간·호스트별로 나눠 수와 '같은 발표' 수를 센다(Bedrock 호출 없음).

    uv run python docs/work_note/Nov-2026/261114-duplicate-articles-7days/tools/same_site_analyze.py <same-site-measure.json>

'같은 발표' = 2회 모두 True. 판정 실패(None)는 '같은 발표'가 아닌 쪽에 들어가므로 수를 따로 찍는다.
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from datetime import date

from briefing.core.retrieval.sources import CATALOG

cat = {s.name: s.category for s in CATALOG}
rows = json.load(open(sys.argv[1]))
for r in rows:
    r["yes"] = r["same"] == [True, True]
    r["gap"] = (date.fromisoformat(r["run_date"]) - date.fromisoformat(r["a_run"])).days
    r["b_cat"], r["a_cat"] = cat.get(r["b_media"], "?"), cat.get(r["a_media"], "?")
    r["host"] = r["cited"].split("/", 1)[0]

failed = [r for r in rows if None in r["same"]]
print(f"후보 {len(rows)} · 같은 발표 {sum(r['yes'] for r in rows)} · 판정 실패 포함 {len(failed)}")
for r in failed:
    print(f"   실패 {r['run_date'][5:]} {r['same']} [{r['b_media'][:14]}] {r['b_title'][:56]} ← [{r['a_media'][:14]}] {r['a_title'][:48]}")
print()


def table(title, key):
    c, y = Counter(key(r) for r in rows), Counter(key(r) for r in rows if r["yes"])
    print(f"-- {title}")
    for k, n in c.most_common():
        print(f"   {str(k)[:46]:46} 후보 {n:4} · 같은 발표 {y.get(k, 0)}")
    print()


table("B 매체 분야", lambda r: r["b_cat"])
table("B 매체", lambda r: r["b_media"])
table("A 와의 날짜 차(일)", lambda r: r["gap"])
table("링크한 호스트", lambda r: r["host"])
table("A 매체 분야", lambda r: r["a_cat"])

per_day = defaultdict(int)
for r in rows:
    per_day[r["run_date"]] += 1
print("날짜별 후보:", dict(sorted(per_day.items())))
print("하루 최대", max(per_day.values()), "· 평균", round(len(rows) / 17, 1))

print("\n-- B 당 후보 수(상위)")
per_b = Counter((r["run_date"], r["b_media"], r["b_title"][:50]) for r in rows)
for (rd, m, t), n in per_b.most_common(8):
    print(f"   {n:3}  {rd[5:]} [{m[:14]}] {t}")

for label, pred in [
    ("B 가 News & Media·Community 만", lambda r: r["b_cat"] in ("News & Media", "Community")),
    ("B 가 The Decoder·PyTorch Korea 만", lambda r: "Decoder" in r["b_media"] or "PyTorch" in r["b_media"]),
    ("A 와 3일 이내", lambda r: r["gap"] <= 3),
    ("A 와 4일 이내", lambda r: r["gap"] <= 4),
    ("B News&Media·Community + 4일 이내", lambda r: r["b_cat"] in ("News & Media", "Community") and r["gap"] <= 4),
]:
    sub = [r for r in rows if pred(r)]
    d = Counter(r["run_date"] for r in sub)
    print(f"\n{label}: 후보 {len(sub)} · 같은 발표 {sum(r['yes'] for r in sub)}/{sum(r['yes'] for r in rows)} · 하루 최대 {max(d.values()) if d else 0} · 평균 {len(sub) / 17:.1f}")
