"""오늘 기준선 — 현 프롬프트로 분야 골든 게이트 1회(passes=1). 좁힌 프롬프트 87.8% 와 같은 날 비교용(run 간 변동 분리)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd() / "scripts"))
from area_eval.run_golden import evaluate, load_golden  # noqa: E402

from briefing.core.config import load_settings  # noqa: E402
from briefing.core.retrieval.relevance_bedrock import _label_model, make_bedrock_labels  # noqa: E402

settings = load_settings()
res = evaluate(load_golden(), make_bedrock_labels(settings), passes=1)
out = Path(__file__).with_name("golden_current.json")
out.write_text(json.dumps({k: res[k] for k in ("scored", "correct", "accuracy", "gate", "gate_pass", "mismatch_boundary",
                                                 "mismatch_nonboundary", "failures", "mismatches")},
                          ensure_ascii=False, indent=1), encoding="utf-8")
print(f"model={_label_model(settings)} current prompt golden: {res['correct']}/{res['scored']} = {res['accuracy']:.1%} "
      f"→ {'PASS' if res['gate_pass'] else 'FAIL'} (경계 {res['mismatch_boundary']} · 비경계 {res['mismatch_nonboundary']} · 실패 {len(res['failures'])})")
for m in res["mismatches"]:
    print(f"  {'B' if m['boundary'] else '-'} {m['gold']:>26} -> {str(m['pred']):<26} | {m['headline'][:60]}")
