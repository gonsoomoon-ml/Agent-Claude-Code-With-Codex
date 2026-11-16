#!/usr/bin/env python3
"""results.jsonl 요약 — 변형별 정답률(첫 JSON / 마지막 JSON), 틀린 쌍, 흔들린 쌍, 사고 블록 비율, 토큰.

    uv run python summarize.py <pairs.json> <results.jsonl>
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict

pairs = json.load(open(sys.argv[1]))
res = [json.loads(ln) for ln in open(sys.argv[2])]
by = defaultdict(list)
for r in res:
    by[(r["variant"], r["idx"])].append(r)

for v in sorted({r["variant"] for r in res}):
    rows = [r for r in res if r["variant"] == v]
    errs = [r for r in rows if "error" in r]
    ok = [r for r in rows if "error" not in r]
    think = sum("reasoningContent" in r["kinds"] for r in ok)
    print(f"\n===== {v}: 호출 {len(rows)} · 오류 {len(errs)} · 사고 블록 {think}/{len(ok)} · "
          f"평균 출력 {sum(r['out_tokens'] for r in ok) / max(len(ok), 1):.0f}토큰 · 평균 입력 {sum(r['in_tokens'] for r in ok) / max(len(ok), 1):.0f} · "
          f"max_tokens 잘림 {sum(r['stop'] == 'max_tokens' for r in ok)} · JSON 2개 이상 {sum(r['n_json'] > 1 for r in ok)} · JSON 없음 {sum(r['n_json'] == 0 for r in ok)}")
    for key in ("first", "last"):
        stat = defaultdict(lambda: [0, 0])   # (group, expect) → [맞음, 전체]
        wrong, flips = [], []
        for i, p in enumerate(pairs):
            rs = [r for r in by.get((v, i), []) if "error" not in r]
            if not rs:
                continue
            vals = [r[key] for r in rs]
            if p["expect"] is None:
                continue
            g = (p["group"], p["expect"])
            for val in vals:
                stat[g][1] += 1
                stat[g][0] += val == p["expect"]
            if any(val != p["expect"] for val in vals):
                wrong.append((p, vals))
            if len(set(vals)) > 1:
                flips.append(p)
        tot_ok, tot = sum(a for a, _ in stat.values()), sum(b for _, b in stat.values())
        print(f"  [{key} JSON] 정답 {tot_ok}/{tot} · " + " · ".join(f"{g[0]}/{'제외' if g[1] else '유지'} {a}/{b}" for g, (a, b) in sorted(stat.items(), key=str)) + f" · 흔들린 쌍 {len(flips)}")
        if key == "first":
            for p, vals in wrong:
                print(f"     ✗ {p['group']:7} 정답={'제외' if p['expect'] else '유지'} 판정={['T' if x else ('F' if x is False else '-') for x in vals]} {p['b_media'][:14]} {p['b_title'][:46]!r} ← {p['a_title'][:34]!r}")
    skipped = [(p, [r["first"] for r in by.get((v, i), []) if "error" not in r]) for i, p in enumerate(pairs) if p["expect"] is None]
    for p, vals in skipped:
        print(f"     (경계) {['T' if x else ('F' if x is False else '-') for x in vals]} {p['b_title'][:46]!r} ← {p['a_title'][:34]!r}")
