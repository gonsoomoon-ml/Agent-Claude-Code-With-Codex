#!/usr/bin/env python3
"""재생 결과(rereport_replay.py --json-out)를 측정값(same_site_measure.py 출력)과 기계적으로 대조한다(Bedrock 호출 없음).

    uv run python docs/work_note/Nov-2026/261114-duplicate-articles-7days/tools/same_site_diff.py \\
        <same-site-replay-….json> <same-site-measure.json>

- 제외된 (날짜, B) 집합 == 측정에서 2회 모두 "같은 발표"였던 (날짜, B) 집합인가.
- 같은 사이트로 판정한 쌍 ⊆ 측정의 A2 후보(B 가 News & Media·Community)인가 — 밖에 있으면 규칙이 측정보다 넓다.
- 측정 후보인데 판정하지 않은 쌍은 이유별로 센다(B 가 먼저 빠짐 = 첫 "같음"에서 멈춤 · 정확히 링크한 쌍이라 (a)(b) 가 맡음).
"""
from __future__ import annotations

import json
import sys
from collections import Counter

from briefing.core.retrieval.sources import CATALOG

cat = {s.name: s.category for s in CATALOG}
WIDE = ("News & Media", "Community")
replay = json.load(open(sys.argv[1], encoding="utf-8"))
near = json.load(open(sys.argv[2], encoding="utf-8"))

want = {(r["run_date"], r["b_sid"]) for r in near if r["same"] == [True, True]}
cand = {(r["a_sid"], r["b_sid"]): r for r in near if cat.get(r["b_media"]) in WIDE}
got = {(r["run_date"], r["b_sid"]) for r in replay if r["tag"] == "DROP"}
title = {r["b_sid"]: f"[{r['b_media'][:14]}] {r['b_title'][:60]}" for r in near} | \
        {r["b_sid"]: f"[{r['b_media'][:14]}] {r['b_title'][:60]}" for r in replay}

print(f"제외: 재생 {len(got)} · 측정 {len(want)} · 일치 {len(got & want)}")
for label, rows in (("재생에만 있음(측정 밖 제외)", got - want), ("측정에만 있음(놓침)", want - got)):
    for d, b in sorted(rows):
        print(f"  ★ {label}: {d} {title[b]}")

site = [r for r in replay if r["how"] == "SITE"]
link = [r for r in replay if r["how"] == "LINK"]
site_keys = {(r["a_sid"], r["b_sid"]) for r in site}
link_keys = {(r["a_sid"], r["b_sid"]) for r in link}
outside = site_keys - set(cand)
print(f"\n판정한 쌍: 정확히 링크 {len(link)} · 같은 사이트 {len(site)} (측정 A2 후보 {len(cand)})")
print(f"같은 사이트 판정 중 측정 후보 밖: {len(outside)}")
for r in site:
    if (r["a_sid"], r["b_sid"]) in outside:
        print(f"  ★ {r['run_date']} {r['tag']} [{r['b_media'][:14]}] {r['b_title'][:50]} ← [{r['a_media'][:14]}] {r['a_title'][:44]}")

dropped_b = {b for _d, b in got}
why = Counter()
unexplained = []
for key, r in cand.items():
    if key in site_keys:
        continue
    if key in link_keys:
        why["정확히 링크한 쌍이라 (a)(b) 가 판정"] += 1
    elif r["b_sid"] in dropped_b:
        why["B 가 먼저 빠져 남은 후보를 묻지 않음"] += 1
    else:
        why["설명 안 됨"] += 1
        unexplained.append(r)
print(f"측정 후보인데 같은 사이트로 판정하지 않은 쌍 {len(cand) - len(site_keys & set(cand))}: {dict(why)}")
for r in unexplained[:20]:
    print(f"  ★ {r['run_date']} [{r['b_media'][:14]}] {r['b_title'][:50]} ← [{r['a_media'][:14]}] {r['a_title'][:44]} ({r['cited'][:50]})")

per_day = Counter(r["run_date"] for r in replay)
site_day = Counter(r["run_date"] for r in site)
print("\n날짜별 판정 쌍(전체/같은 사이트): " +" ".join(f"{d[5:]}:{per_day[d]}/{site_day[d]}" for d in sorted(per_day)))
print(f"하루 최대 {max(per_day.values())} · 평균 {len(replay) / max(len(per_day), 1):.1f}(판정이 있던 날 기준)")
flips = [r for r in site if (r["a_sid"], r["b_sid"]) in cand and (r["same"] is True) != (cand[(r["a_sid"], r["b_sid"])]["same"] == [True, True])]
print(f"측정과 판정이 다른 같은 사이트 쌍: {len(flips)}")
for r in flips:
    print(f"  ★ {r['run_date']} 재생 same={r['same']} · 측정 {cand[(r['a_sid'], r['b_sid'])]['same']} [{r['b_media'][:14]}] {r['b_title'][:50]} ← {r['a_title'][:44]}")
