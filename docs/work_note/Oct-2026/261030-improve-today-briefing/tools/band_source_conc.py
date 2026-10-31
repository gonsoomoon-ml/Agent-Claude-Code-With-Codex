"""문제 #4 — (날짜, 밴드, 소스) 별 카드 수: 한 소스가 한 밴드에 3장 이상인 경우가 PyTorch KR 에만 있는지(10일, 재생 라벨).
+ v65 규칙으로 핵심 3 에 PyTorch KR 카드가 든 날 수(핵심으로 올라간 카드는 밴드에서 빠지므로 밴드 잔여도 같이 계산)."""
import json
from collections import Counter
from pathlib import Path

from briefing.core import top_picks as tp
from briefing.core.retrieval.sources import CATALOG

HERE = Path(__file__).parent
ref = json.loads((HERE / "toppicks_replay_out2" / "replay.json").read_text(encoding="utf-8"))
cat_of = {s.name: s.category for s in CATALOG}
PTK = "PyTorch Korea"

conc = Counter()           # (source) → 횟수(날×밴드에서 3장 이상)
cases = []
ptk_top_days = 0; ptk_top_cards = 0
print("날짜 | 핵심 3 중 PyTorch KR | 핵심 제외 뒤 AI Agents 밴드(전체/PyTorch KR)")
for day in sorted(ref["days"]):
    rows = sorted(ref["days"][day]["prompts"]["refined"]["labels"], key=lambda r: r["n"])
    secs = [cat_of.get(r["media"], "") for r in rows]
    pub = [dict(r) for r in rows if r["decision"] == "PUBLISH"]
    top = set(tp.assign_top(pub, secs, 3))
    by_n = {r["n"]: r for r in rows}
    ptk_in_top = [by_n[i] for i in top if by_n[i]["media"].startswith(PTK)]
    ptk_top_days += bool(ptk_in_top); ptk_top_cards += len(ptk_in_top)
    rest = [r for r in rows if r["n"] not in top]
    ag = [r for r in rest if r["area"] == "AI Agents"]
    ag_ptk = [r for r in ag if r["media"].startswith(PTK)]
    print(f"{day} | {len(ptk_in_top)} {'· '.join(r['headline'][:28] for r in ptk_in_top)} | {len(ag)}/{len(ag_ptk)}")
    c = Counter((r["area"], r["media"]) for r in rest)
    for (area, media), n in c.items():
        if n >= 3:
            conc[media] += 1
            cases.append((day, area, media, n))
print(f"\n핵심 3 에 PyTorch KR 카드가 든 날 {ptk_top_days}/10 (카드 {ptk_top_cards}장)")
print("\n== 한 소스가 한 밴드(핵심 제외)에 3장 이상인 경우 ==")
for day, area, media, n in cases:
    print(f"  {day} {area:28s} {media:24s} {n}")
print("소스별 횟수:", dict(conc))
