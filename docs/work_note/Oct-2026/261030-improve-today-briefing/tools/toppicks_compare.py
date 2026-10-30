"""날짜별 핵심 3 비교표 — 운영 실제 선정(CloudWatch `top picks 선정`) · 현 프롬프트 재생 · 좁힌(refined) 프롬프트 재생."""
import json
from pathlib import Path

HERE = Path(__file__).parent
cur = json.loads((HERE / "toppicks_replay_out" / "replay.json").read_text(encoding="utf-8"))
ref = json.loads((HERE / "toppicks_replay_out2" / "replay.json").read_text(encoding="utf-8"))

# 운영 정기 run(20:xx UTC) 선정 — 2026-10-30 CloudWatch 조회. 같은 날 묶음이 둘이면 첫 묶음.
PROD = {
    "2026-10-20": ["p1 Google: Integrating TorchTPU into TorchTitan", "p1 Anthropic: Claude Opus 5.5 / Sonnet 5.5 now available in Google…", "p2 applied: AI 에이전트 시대의 기업 토큰 경제학(Bedrock)"],
    "2026-10-21": ["p1 Anthropic: Introducing Claude Duet", "p1 OpenAI: Google Cloud expands model choice (OpenAI models)", "p2 applied: Beyond the KV cache: Training and serving i14's…"],
    "2026-10-22": ["p1 Amazon: Amazon Polly major upgrade to Generative engine", "p1 Anthropic: Donating Agent Skills to the AAIF", "p2 Anthropic: Building agents: When to fold subagents…"],
    "2026-10-23": ["p1 Anthropic: Claude Cowork and chat come together for Enterprise", "p1 Google: Expanding Claude availability on Google Cloud", "p2 applied: LiteLLM v1.107.0 공급망 공격 (다른 묶음: Multi-Turn RL on SageMaker)"],
    "2026-10-24": ["p1 OpenAI: OpenAI's isolated AI agents found ways to talk…", "p2 applied: Fancy harnesses make coding agents more expensive", "p3 launch: Kimi K3.1 Pro 출시 (다른 묶음: Anthropic Scion)"],
    "2026-10-25": ["p1 OpenAI: OpenAI가 AAIF에 기증한 Open Responses", "p3 launch: OpenMobile-2 open-source smartphone agents", "p3 launch: NVIDIA Nemotron 3 소형 모델(4GB VRAM)"],
    "2026-10-26": ["p1 Anthropic: Anthropic files S-1 with the SEC", "p1 Google: Scale agents securely with IAM Helper Agent Skills", "p2 Amazon: Fleet-wide computer vision lifecycle at the edge (다른 묶음: Groundhog Day prompt caching)"],
    "2026-10-27": ["p1 Google: Genie 4: A new generation of world simulation", "p1 OpenAI: GPT-6.1 Terra halves OpenAI's API prices", "p2 applied: Fix evaluation bias to unlock better models on Amazon…"],
    "2026-10-28": ["p1 Google: Gemini 4 Carbon: Our next frontier model", "p1 Anthropic: Expanding our partnership with GSA", "p2 Anthropic: Early progress on accelerating drug development with Claude"],
    "2026-10-29": ["p1 Amazon: Lend and borrow resources… AWS Batch quota management", "p1 Anthropic: AI for Science expands to foundations and institutions", "p2 applied: Building intent-driven UI testing with Amazon Nova Act"],
}


def picks(rep, day, variant):
    d = rep["days"].get(day, {}).get("prompts", {}).get(variant)
    if not d or "error" in d:
        return ["(없음)"]
    return d["picks"]["0"]


def tier1(rep, day, variant):
    d = rep["days"].get(day, {}).get("prompts", {}).get(variant)
    if not d or "error" in d:
        return []
    return [f"{r['importance']} {r['org']}·{r['type']}: {r['headline'][:40]}" for r in d["labels"]
            if r["tier"] == 1 and r["decision"] == "PUBLISH"]


lines = ["# 날짜별 핵심 3 — 운영 vs 현 프롬프트 재생 vs 좁힌 프롬프트 재생", ""]
for day in sorted(set(cur["days"]) | set(ref["days"])):
    lines.append(f"## {day}")
    lines.append("- **운영(실발송)** → " + " | ".join(PROD.get(day, ["?"])))
    lines.append("- **현 프롬프트 재생** → " + " | ".join(picks(cur, day, "current")))
    lines.append("- **좁힌 프롬프트 재생** → " + " | ".join(picks(ref, day, "refined")))
    t_cur, t_ref = tier1(cur, day, "current"), tier1(ref, day, "refined")
    lines.append(f"  - 1티어 후보: 현 {len(t_cur)}장 → 좁힌 {len(t_ref)}장" + (f" (좁힌: {'; '.join(t_ref)})" if t_ref else ""))
    lines.append("")
g = ref.get("golden_candidate")
if g:
    lines.append(f"## 분야 골든 게이트({ref.get('golden_variant')}): {g['correct']}/{g['scored']} = {g['accuracy']:.1%} "
                 f"→ {'PASS' if g['gate_pass'] else 'FAIL'} (경계 {g['mismatch_boundary']} · 비경계 {g['mismatch_nonboundary']})")
out = HERE / "toppicks_compare.md"
out.write_text("\n".join(lines), encoding="utf-8")
print("\n".join(lines))
