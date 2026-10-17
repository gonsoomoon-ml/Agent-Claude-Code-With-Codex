"""가격과 비용 계산 — 단위는 $/1M 토큰. 확인하지 않은 가격은 verified=False 로 끝까지 따라다닌다('미확인' 표기).

Task 7 은 자료형·2차 출처 가격·codex 비용만 두고, Task 11 이 공식 가격 조회·Cost Explorer·카드당 비용을 더한다.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .common import EXP_ROOT

PRICES_PATH = EXP_ROOT / "results" / "prices.json"   # Task 11 이 공식 가격으로 쓴다


@dataclass(frozen=True)
class Price:
    input: float
    output: float
    cache_read: float | None
    verified: bool
    source: str
    cache_write: float | None = None   # codex 0.163.0 이 cache_write_input_tokens 를 보고한다(Task 1). 모르면 입력 단가.


_SECONDARY = "2차 출처(2026-10, Bedrock 미확인)"
FALLBACK_PRICES: dict[str, Price] = {
    "gpt-6-astra": Price(10.0, 50.0, None, False, _SECONDARY),
    "gpt-6-sol": Price(2.0, 10.0, None, False, _SECONDARY),
    "gpt-6.1-sol": Price(2.0, 10.0, None, False, _SECONDARY),
    "gpt-6-luna": Price(0.10, 0.50, None, False, _SECONDARY),
    "gpt-5.5": Price(5.0, 30.0, None, False, _SECONDARY),
}


def load_prices(path: Path | None = None) -> dict[str, Price]:
    """확인된 가격 파일(Task 11)이 있으면 그 값으로 덮고, 없는 모델은 2차 출처(verified=False)를 유지한다."""
    path = path or PRICES_PATH
    prices = dict(FALLBACK_PRICES)
    if path.exists():
        for key, fields in json.loads(path.read_text(encoding="utf-8")).items():
            prices[key] = Price(**fields)
    return prices


def codex_cost(usage: dict, price: Price, *, reasoning_in_output: bool = True) -> float:
    """codex `turn.completed.usage` → 달러. 캐시 읽기·쓰기 단가를 모르면 입력 단가로 센다(보수적)."""
    total_in = usage.get("input_tokens", 0) or 0
    cached = usage.get("cached_input_tokens", 0) or 0
    written = usage.get("cache_write_input_tokens", 0) or 0
    out = usage.get("output_tokens", 0) or 0
    if not reasoning_in_output:
        out += usage.get("reasoning_output_tokens", 0) or 0
    uncached = max(total_in - cached - written, 0)
    read_rate = price.input if price.cache_read is None else price.cache_read
    write_rate = price.input if price.cache_write is None else price.cache_write
    return (uncached * price.input + cached * read_rate + written * write_rate + out * price.output) / 1e6
