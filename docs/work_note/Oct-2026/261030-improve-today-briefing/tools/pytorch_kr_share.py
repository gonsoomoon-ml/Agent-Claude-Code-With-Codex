"""문제 #4 재료 — AI Agents 밴드에서 PyTorch Korea(커뮤니티 2차 큐레이션) 비중, 10일(재생 라벨 = 배포 프롬프트).
날짜별: 보이는 카드 수 · PyTorch KR 카드 수 · AI Agents 밴드 카드 수 · 그중 PyTorch KR · PyTorch KR 카드의 분야 분포."""
import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).parent
ref = json.loads((HERE / "toppicks_replay_out2" / "replay.json").read_text(encoding="utf-8"))
PTK = "PyTorch Korea"

tot_agents = tot_agents_ptk = tot_ptk = tot_cards = 0
ptk_area = Counter()
print("날짜 | 카드 | PyTorch KR | AI Agents 밴드 | 그중 PyTorch KR | PyTorch KR 글의 분야")
for day in sorted(ref["days"]):
    rows = ref["days"][day]["prompts"]["refined"]["labels"]
    ptk = [r for r in rows if r["media"].startswith(PTK)]
    agents = [r for r in rows if r["area"] == "AI Agents"]
    agents_ptk = [r for r in agents if r["media"].startswith(PTK)]
    dist = Counter(r["area"] for r in ptk)
    ptk_area.update(dist)
    tot_cards += len(rows); tot_ptk += len(ptk); tot_agents += len(agents); tot_agents_ptk += len(agents_ptk)
    print(f"{day} | {len(rows):2d} | {len(ptk)} | {len(agents)} | {len(agents_ptk)} | " + ", ".join(f"{a} {n}" for a, n in dist.most_common()))
print(f"합계 | {tot_cards} | {tot_ptk} | {tot_agents} | {tot_agents_ptk} ({tot_agents_ptk/tot_agents:.0%} of AI Agents)")
print("PyTorch KR 글 분야 합:", dict(ptk_area))

print("\n== 10-29 AI Agents 밴드 카드(재생 라벨 기준) ==")
for r in ref["days"]["2026-10-29"]["prompts"]["refined"]["labels"]:
    if r["area"] == "AI Agents":
        print(f"  [{r['media']}] {r['type']}/{r['importance']} · {r['headline'][:90]}")
print("\n== 10-29 PyTorch KR 카드 전부 ==")
for r in ref["days"]["2026-10-29"]["prompts"]["refined"]["labels"]:
    if r["media"].startswith(PTK):
        print(f"  {r['area']} · {r['type']}/{r['importance']} · {r['headline'][:90]}")
