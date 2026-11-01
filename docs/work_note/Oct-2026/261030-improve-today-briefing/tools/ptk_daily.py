"""PyTorch KR 카드 — 날짜별 장수·제목·importance(10일 재생 라벨, 배포 프롬프트). 10-24 는 운영 라벨 재생 결측분 표시."""
import json
from pathlib import Path
HERE = Path(__file__).parent
ref = json.loads((HERE / "toppicks_replay_out2" / "replay.json").read_text(encoding="utf-8"))
tot = 0
for day in sorted(ref["days"]):
    rows = [r for r in ref["days"][day]["prompts"]["refined"]["labels"] if r["media"].startswith("PyTorch Korea")]
    rows.sort(key=lambda r: (-r["importance"], r["n"]))
    tot += len(rows)
    print(f"{day} ({len(rows)}장)")
    for r in rows:
        print(f"   {r['importance']} · {r['area'][:14]:14s} · {r['headline'][:72]}")
print(f"합계 {tot}장 / 10일 = {tot/10:.1f}장/일")
