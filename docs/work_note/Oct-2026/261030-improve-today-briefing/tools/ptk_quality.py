"""PyTorch KR 글 품질 — importance(1~5, 라벨 LLM) 분포를 다른 소스와 비교(10일 재생 라벨, 배포 프롬프트).
+ 같은 event 키를 1차 발행처와 PTK 가 같은 날 공유한 짝(발행처 태그 편향 점검) + PTK 글 전체 목록(importance 순)."""
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean

HERE = Path(__file__).parent
ref = json.loads((HERE / "toppicks_replay_out2" / "replay.json").read_text(encoding="utf-8"))
PTK = "PyTorch Korea"
rows = [(day, r) for day in sorted(ref["days"]) for r in ref["days"][day]["prompts"]["refined"]["labels"]]
ptk = [r for _, r in rows if r["media"].startswith(PTK)]
oth = [r for _, r in rows if not r["media"].startswith(PTK)]

def hist(xs):
    c = Counter(r["importance"] for r in xs)
    return " ".join(f"{k}:{c.get(k,0)}" for k in range(1, 6))
print(f"PyTorch KR {len(ptk)}장 — importance 분포 {hist(ptk)} · 평균 {mean(r['importance'] for r in ptk):.2f}")
print(f"그 외      {len(oth)}장 — importance 분포 {hist(oth)} · 평균 {mean(r['importance'] for r in oth):.2f}")
print("\n== 소스별 평균 importance(장수) ==")
by_media = defaultdict(list)
for _, r in rows:
    by_media[r["media"]].append(r["importance"])
for m, xs in sorted(by_media.items(), key=lambda kv: -mean(kv[1])):
    print(f"  {mean(xs):.2f} ({len(xs):2d}) {m}")
print("\n== PTK 분야별 평균 ==")
by_area = defaultdict(list)
for r in ptk:
    by_area[r["area"]].append(r["importance"])
for a, xs in sorted(by_area.items(), key=lambda kv: -len(kv[1])):
    print(f"  {a:28s} {len(xs):2d}장 · 평균 {mean(xs):.2f}")
print("\n== PTK 와 1차 소스가 같은 날 같은 event 키(편향 점검) ==")
for day in sorted(ref["days"]):
    ev = defaultdict(list)
    for r in ref["days"][day]["prompts"]["refined"]["labels"]:
        ev[r["event"].lower()].append(r)
    for k, rs in ev.items():
        if len(rs) > 1 and any(r["media"].startswith(PTK) for r in rs) and any(not r["media"].startswith(PTK) for r in rs):
            print(f"  {day} [{k}] " + " | ".join(f"{r['media'][:14]} imp{r['importance']} {r['headline'][:36]}" for r in rs))
print("\n== PTK 글 전체(importance 내림차순) ==")
for r in sorted(ptk, key=lambda r: (-r["importance"], r["area"])):
    org = r.get("org") or "-"
    print(f"  {r['importance']} · {r['type']:7s} · {r['area'][:14]:14s} · {org[:12]:12s} · {r['headline'][:70]}")
