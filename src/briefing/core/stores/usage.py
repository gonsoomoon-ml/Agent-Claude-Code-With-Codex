"""usage — 브리핑 1회의 LLM 실비용 누적 sink(선택 주입, ledger/card_cache 와 동일 패턴).

author 는 `claude -p` 봉투의 total_cost_usd(정확)를, gate.verify_card 는 검증 AI 의 실측 토큰 × 단가를
같은 recorder 에 add 한다. run_briefing 이 사용자 iteration 전후 델타를 스냅샷 → UserBriefing.cost_usd.
캐시히트(사실층 memo/cache)면 실제 LLM 콜이 없어 델타 0 → '실제 발생 비용'(스펙 C1).
"""
from __future__ import annotations

# 검증 AI(codex) 단가 — 100만 토큰당 (입력, 출력) 달러. 키 = codex 설정의 model id.
# 2차 출처(2026-10, Bedrock 가격표에 아직 없음) — 확인되면 갱신. 표에 없는 모델은 '단가 미상'(값을 지어내지 않는다).
# (F5, 2026-10-18: 예전 claim 당 고정 추정치 $0.032 를 대체.)
CERTIFIER_PRICES: dict[str, tuple[float, float]] = {
    "openai.gpt-5.5": (5.0, 30.0),
    "openai.gpt-6-luna": (0.10, 0.50),
}


def certify_cost_usd(model: str, usage: dict) -> float | None:
    """codex `turn.completed.usage` → 달러. 단가표에 없는 모델이면 None(단가 미상).

    캐시 읽기·쓰기 단가는 몰라 입력 토큰 전체를 입력 단가로 센다(보수적 — 실험 costs.codex_cost 와 같은 식).
    추론 토큰은 output_tokens 에 이미 들어 있다.
    """
    price = CERTIFIER_PRICES.get(model)
    if price is None:
        return None
    tokens_in = usage.get("input_tokens", 0) or 0
    tokens_out = usage.get("output_tokens", 0) or 0
    return (tokens_in * price[0] + tokens_out * price[1]) / 1e6


class UsageRecorder:
    """run 1회의 비용 누적기. mutable — pure 테스트에서 미주입 시 계측 0(결정론 유지)."""

    def __init__(self) -> None:
        self._cost_usd = 0.0

    def add(self, cost_usd: float) -> None:
        self._cost_usd += cost_usd

    def total(self) -> float:
        return self._cost_usd
