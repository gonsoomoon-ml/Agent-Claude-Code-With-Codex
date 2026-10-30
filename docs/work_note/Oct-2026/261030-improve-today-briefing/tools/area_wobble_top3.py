"""문제 #3 재료 — 분야(area) 흔들림이 배포 규칙(#2c, v65)의 핵심 3 에 주는 영향.
기준 = 좁힌 프롬프트 재생 라벨(배포 프롬프트). 변형 = 같은 라벨에서 area 만 다른 재생(현 프롬프트)의 값으로 바꿈.
→ area 흔들림만으로 핵심 3 이 바뀐 날을 센다(type·importance·org·event 는 고정)."""
import json
from pathlib import Path

from briefing.core import top_picks as tp
from briefing.core.retrieval.sources import CATALOG

HERE = Path(__file__).parent
cur = json.loads((HERE / "toppicks_replay_out" / "replay.json").read_text(encoding="utf-8"))
ref = json.loads((HERE / "toppicks_replay_out2" / "replay.json").read_text(encoding="utf-8"))
cat_of = {s.name: s.category for s in CATALOG}


def top3(rows):
    secs = [cat_of.get(r["media"], "") for r in rows]
    pub = [dict(r) for r in rows if r["decision"] == "PUBLISH"]
    return tp.assign_top(pub, secs, 3)


changed_days = 0
for day in sorted(ref["days"]):
    base = sorted(ref["days"][day]["prompts"]["refined"]["labels"], key=lambda r: r["n"])
    cur_pr = cur["days"].get(day, {}).get("prompts", {}).get("current")
    if not cur_pr or "error" in cur_pr:
        continue
    cur_area = {r["headline"]: r["area"] for r in cur_pr["labels"]}
    alt = [dict(r, area=cur_area.get(r["headline"], r["area"])) for r in base]
    flips = [(r["headline"][:50], r["area"], a["area"]) for r, a in zip(base, alt) if r["area"] != a["area"]]
    t_base, t_alt = top3(base), top3(alt)
    by_n = {r["n"]: r for r in base}
    same = t_base == t_alt
    changed_days += not same
    print(f"{day}: 분야 바뀐 카드 {len(flips)} · 핵심 3 {'같음' if same else '★바뀜'}")
    for h, a, b in flips:
        print(f"    {a} → {b} | {h}")
    if not same:
        print("    기준:", " / ".join(by_n[i]["headline"][:40] for i in t_base))
        print("    변형:", " / ".join(by_n[i]["headline"][:40] for i in t_alt))
print(f"\narea 흔들림만으로 핵심 3 이 바뀐 날 = {changed_days}/10")
