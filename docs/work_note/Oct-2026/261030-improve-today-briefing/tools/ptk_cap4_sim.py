"""PyTorch KR 캡 5→4 시뮬(11-01, 배포된 A 안 확인) — ptk_cap3_sim 의 K=4 판. PTK 카드 5장이던 3일에 운영 선별자(Haiku pick-4) 2회.
(제목, 요약) 을 넣어 pick-3 을 2회 돌려 무엇이 남고 무엇이 빠지는지 + "importance 상위 3" 과 비교(동점 표시).
입력 근사: 운영은 제목+원문 앞 300자, 여기선 제목+요약 300자. 읽기 전용(DDB) + Haiku 호출 12회."""
import json
import sys
from pathlib import Path

from briefing.core.config import load_settings
from briefing.core.retrieval.relevance_bedrock import _client, _converse_text
from briefing.core.retrieval.selection import pick_indices
from briefing.core.stores.backends import make_stores

sys.path.insert(0, str(Path(__file__).parent))
from toppicks_replay import load_day_cards  # noqa: E402

HERE = Path(__file__).parent
ref = json.loads((HERE / "toppicks_replay_out2" / "replay.json").read_text(encoding="utf-8"))
DAYS = ("2026-10-23", "2026-10-26", "2026-10-29")   # PTK 카드 5장이던 날만(4장 이하는 캡 4 에서 무변화)
K = 4
settings = load_settings()
store, cache, ledger = make_stores(settings)
client = _client(settings.region)
invoke = lambda s, u: _converse_text(client, settings.relevance_model_id, s, u, 64)  # noqa: E731
print(f"selector model = {settings.relevance_model_id}")

tot_before = tot_after = ag_before = ag_after = 0
for day in DAYS:
    items, _ = load_day_cards(ledger, cache, store, day, settings.author_model_id)
    ptk = [i for i in items if i["media"].startswith("PyTorch Korea")]
    lab = {r["headline"]: r for r in ref["days"][day]["prompts"]["refined"]["labels"] if r["media"].startswith("PyTorch Korea")}
    cands = [(i["g"].card.headline, i["g"].card.summary) for i in ptk]
    picks = [set(pick_indices(cands, K, invoke=invoke)) for _ in range(2)]
    both = picks[0] & picks[1]
    imps = [lab.get(h, {}).get("importance", 0) for h, _ in cands]
    order = sorted(range(len(cands)), key=lambda i: -imps[i])
    cut = imps[order[K - 1]] if len(order) >= K else 0
    tie = sum(1 for v in imps if v == cut) > sum(1 for i in order[:K] if imps[i] == cut)
    print(f"\n{day} — PTK {len(cands)}장 → 캡 {K} (Haiku 2회 일치 {len(both)}/{K}{', 동점 경계 imp ' + str(cut) if tie else ''})")
    for i, (h, _) in enumerate(cands):
        mark = "유지" if i in both else ("흔들림" if i in picks[0] | picks[1] else "탈락")
        area = lab.get(h, {}).get("area", "?")[:14]
        print(f"   {mark:3s} · imp {imps[i]} · {area:14s} · {h[:66]}")
    kept = [i for i in range(len(cands)) if i in picks[0]]   # 1회차 기준 집계
    tot_before += len(cands)
    tot_after += len(kept)
    ag_before += sum(1 for h, _ in cands if lab.get(h, {}).get("area") == "AI Agents")
    ag_after += sum(1 for i in kept if lab.get(cands[i][0], {}).get("area") == "AI Agents")
print(f"\n3일 합계: PTK 카드 {tot_before} → {tot_after}장 · 그중 AI Agents 밴드행 {ag_before} → {ag_after}장 (나머지 날은 4장 이하라 무변화)")
