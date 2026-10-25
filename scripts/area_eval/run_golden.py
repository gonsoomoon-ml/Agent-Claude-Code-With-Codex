#!/usr/bin/env python
"""run_golden — 골든셋(`scripts/area_eval/golden_7d.json`)으로 분야 라벨 호출을 평가한다(머지 게이트, 스펙 §7).

지표(고유·분류 가능 카드 기준, 1회차):
- 정확 일치율(`accuracy`) — **하드 게이트 ≥ 0.85**
- 불일치의 boundary / non-boundary 분해(소프트: non-boundary 는 건별 사유 기록 대상)
- 안정성(`stability`) — 2회차가 있으면 1·2회차 일치율(보고만)
- run_date 묶음별 핵심 3 선택(`picks`) — CloudWatch "top picks 선정" 로그와 나란히 보는 관찰(게이트 아님)
입력은 실제 호출 크기 = run_date 묶음(반복 행 포함 — 그날 메일에 실린 그대로), 점수는 고유 카드만.

usage: BACKEND=dynamo uv run python scripts/area_eval/run_golden.py [--passes 2] [--dry-run] [--out-dir DIR]
  --dry-run = 골든 라벨을 그대로 돌려주는 fake(러너 자체 점검, $0). 실 호출 = LABEL_MODEL_ID(Sonnet 5.5) ≈ $0.5/2회.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, OrderedDict
from datetime import datetime, timezone
from pathlib import Path

from briefing.core.areas import AREAS
from briefing.core.authoring.author import DraftCard
from briefing.core.gate import GatedCard
from briefing.core.top_picks import pick_top

GATE = 0.85
GOLDEN = Path(__file__).with_name("golden_7d.json")
DEFAULT_OUT = Path("docs/work_note/Oct-2026/261024-Reorder-Content")


def load_golden(path: Path = GOLDEN) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def build_cards(rows: list[dict]) -> list[GatedCard]:
    """골든 행 → 라벨 입력 카드(사실층 제목·요약만; 검증 결과는 평가와 무관이라 빈 튜플)."""
    return [GatedCard(DraftCard(r["source_id"], r["headline"], r.get("summary") or "", "", ()), (), r["decision"], 1)
            for r in rows]


def evaluate(golden: dict, label_fn, passes: int = 2) -> dict:
    rows = golden["cards"]
    by_run: dict[str, list[dict]] = OrderedDict()
    for r in rows:
        by_run.setdefault(r["run_date"], []).append(r)
    preds: list[dict[str, str]] = [{} for _ in range(passes)]
    failures: list[dict] = []
    picks: dict[str, list[str]] = {}
    for p in range(passes):
        for rd, rs in by_run.items():
            cards = build_cards(rs)
            secs = [r.get("category") or "" for r in rs]
            try:
                labels = list(label_fn(cards, secs))
            except Exception as err:  # noqa: BLE001 — 묶음 실패는 기록하고 다음 묶음
                failures.append({"pass": p + 1, "run_date": rd, "reason": f"{type(err).__name__}: {err}"})
                continue
            for lb in labels:
                preds[p].setdefault(cards[lb["n"]].card.source_id, lb.get("area"))
            if p == 0:
                sids = pick_top(cards, labels, secs)
                heads = {g.card.source_id: g.card.headline for g in cards}
                picks[rd] = [heads[s][:70] for s in sids]
    scored = [r for r in rows if r.get("area") and not r.get("repeat_of_earlier_run")]
    mismatches = []
    for r in scored:
        pred = preds[0].get(r["source_id"])
        if pred != r["area"]:
            mismatches.append({"run_date": r["run_date"], "source_id": r["source_id"], "headline": r["headline"][:80],
                               "gold": r["area"], "pred": pred, "boundary": bool(r.get("boundary")),
                               "alt_old_code": r.get("alt_old_code"), "reason": ""})
    correct = len(scored) - len(mismatches)
    stability = None
    if passes >= 2:
        both = [s for s in preds[0] if s in preds[1]]
        stability = (sum(1 for s in both if preds[0][s] == preds[1][s]) / len(both)) if both else 0.0
    confusion = Counter((r["area"], preds[0].get(r["source_id"]) or "(없음)") for r in scored)
    return {
        "scored": len(scored), "correct": correct, "accuracy": (correct / len(scored)) if scored else 0.0,
        "gate": GATE, "gate_pass": bool(scored) and (correct / len(scored)) >= GATE,
        "mismatches": mismatches,
        "mismatch_boundary": sum(1 for m in mismatches if m["boundary"]),
        "mismatch_nonboundary": sum(1 for m in mismatches if not m["boundary"]),
        "stability": stability, "failures": failures, "picks": picks,
        "confusion": [{"gold": g, "pred": p, "n": n} for (g, p), n in sorted(confusion.items(), key=lambda x: -x[1])],
        "pred_by_area": dict(Counter(a for a in preds[0].values())),
        "predictions": preds,
    }


def render_report(res: dict, *, model: str, passes: int, prompt_note: str = "") -> str:
    out = [f"# 골든셋 평가 — 분야 라벨 ({datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%MZ')})\n",
           f"- 모델 `{model}` · 회차 {passes} · 고유 분류 가능 카드 {res['scored']} · {prompt_note}",
           f"- **정확 일치 {res['correct']}/{res['scored']} = {res['accuracy']:.1%}** → 게이트 {res['gate']:.0%}: "
           f"**{'PASS' if res['gate_pass'] else 'FAIL'}**",
           f"- 불일치 {len(res['mismatches'])} = 경계(boundary) {res['mismatch_boundary']} + 비경계 {res['mismatch_nonboundary']}"
           + (f" · 안정성(1·2회 일치) {res['stability']:.1%}" if res["stability"] is not None else ""),
           f"- 묶음 실패 {len(res['failures'])}" + (": " + "; ".join(f"{f['pass']}회차 {f['run_date']} {f['reason'][:60]}" for f in res["failures"]) if res["failures"] else ""),
           "\n## 예측 분포(1회차)\n", "| 분야 | 예측 수 |", "|---|---|"]
    out += [f"| {a} | {res['pred_by_area'].get(a, 0)} |" for a in AREAS]
    out += ["\n## 혼동(정답 → 예측, 불일치만)\n", "| 정답 | 예측 | 건 |", "|---|---|---|"]
    out += [f"| {c['gold']} | {c['pred']} | {c['n']} |" for c in res["confusion"] if c["gold"] != c["pred"]]
    out += ["\n## 불일치 목록 (사유 칸은 손으로 채움 — 비경계는 정의·규칙 수정 재료)\n",
            "| run | 경계 | 정답 | 예측 | 제목 | 사유 |", "|---|---|---|---|---|---|"]
    out += [f"| {m['run_date'][5:]} | {'*' if m['boundary'] else ''} | {m['gold']} | {m['pred']} | {m['headline']} | {m['reason']} |"
            for m in res["mismatches"]]
    out += ["\n## 핵심 3 선택(관찰 — CloudWatch 'top picks 선정' 로그와 나란히; 티어 규칙 손 확인)\n"]
    out += [f"- {rd}: " + (" | ".join(hs) if hs else "(선정 없음)") for rd, hs in res["picks"].items()]
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--passes", type=int, default=2)
    ap.add_argument("--dry-run", action="store_true", help="골든 라벨을 돌려주는 fake(호출 없음)")
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--golden", type=Path, default=GOLDEN)
    a = ap.parse_args(argv)
    golden = load_golden(a.golden)
    if a.dry_run:
        gold = {c["source_id"]: (c.get("area") or "AI Agents") for c in golden["cards"]}
        label_fn = lambda cards, secs: [{"n": i, "org": "", "type": "other", "importance": 3, "event": "e",  # noqa: E731
                                         "area": gold[g.card.source_id]} for i, g in enumerate(cards)]
        model = "dry-run(fake)"
    else:
        from briefing.core.config import load_settings
        from briefing.core.retrieval.relevance_bedrock import _label_model, make_bedrock_labels
        settings = load_settings()
        label_fn, model = make_bedrock_labels(settings), _label_model(settings)
    res = evaluate(golden, label_fn, passes=a.passes)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    a.out_dir.mkdir(parents=True, exist_ok=True)
    (a.out_dir / f"golden-eval-{ts}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    report = render_report(res, model=model, passes=a.passes, prompt_note=f"골든 {a.golden.name}")
    (a.out_dir / f"golden-eval-{ts}.md").write_text(report, encoding="utf-8")
    print(report.split("\n## ")[0])
    print(f"→ {a.out_dir / f'golden-eval-{ts}.md'}")
    return 0 if res["gate_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
