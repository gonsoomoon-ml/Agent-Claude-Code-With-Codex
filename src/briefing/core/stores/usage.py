"""usage — 브리핑 1회의 LLM 실비용 누적 sink(선택 주입, ledger/card_cache 와 동일 패턴).

author 는 `claude -p` 봉투의 total_cost_usd(정확)를, gate.verify_card 는 certify 추정치를
같은 recorder 에 add 한다. run_briefing 이 사용자 iteration 전후 델타를 스냅샷 → UserBriefing.cost_usd.
캐시히트(사실층 memo/cache)면 실제 LLM 콜이 없어 델타 0 → '실제 발생 비용'(스펙 C1).
"""
from __future__ import annotations

# certify 함의 1콜 추정 단가(v1) — cost 분석: GPT-5.5 $5/$30, ~4k in/~400 out ≈ $0.032.
# codex usage 정밀 파싱은 v1.1. author 는 봉투로 이미 정확하므로 추정 대상 아님.
EST_CERTIFY_USD_PER_ENTAILMENT = 0.032


class UsageRecorder:
    """run 1회의 비용 누적기. mutable — pure 테스트에서 미주입 시 계측 0(결정론 유지)."""

    def __init__(self) -> None:
        self._cost_usd = 0.0

    def add(self, cost_usd: float) -> None:
        self._cost_usd += cost_usd

    def total(self) -> float:
        return self._cost_usd
