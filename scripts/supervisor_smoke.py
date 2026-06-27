"""Strands supervisor 오케스트레이션 라이브 스모크 — 1 출처/1 기사로 제한(빠름·저렴).

supervisor(LLM)가 도구를 순서대로 호출: curate_sources → verify_and_produce_card → render_briefing.
발행 결정은 supervisor 가 아니라 verify_and_produce_card 안의 결정론 게이트가 소유.

실행 (저장소 루트에서):
    uv run python scripts/supervisor_smoke.py
    uv run python scripts/supervisor_smoke.py aitimes     # 다른 clean RSS 출처
"""
from __future__ import annotations

import sys

from briefing.runtime.supervisor import run_supervisor


def main() -> None:
    source_key = sys.argv[1] if len(sys.argv) > 1 else "aws-ml"
    print(f"=== Strands supervisor orchestration ({source_key}, 1 item) ===")
    print("supervisor(LLM)가 도구 순서 통제 · 발행 결정은 도구(결정론) 소유\n")

    out = run_supervisor("gonsoo", window_hours=0, source_keys=[source_key], max_items=1)

    print("--- SUPERVISOR TRANSCRIPT (LLM 의 오케스트레이션 서술) ---")
    print(out["transcript"][:1500])
    print("\n--- CARDS (도구가 결정한 verdict) ---")
    for c in out["cards"]:
        print(f"  {c.card.source_id[:12]}: {c.decision}  ({c.attempts} attempts, {len(c.verdicts)} claims)")
    print(f"\n--- EMAIL ({len(out['email'])} bytes) ---")
    print(out["email"][:700])


if __name__ == "__main__":
    main()
