"""집계 통계 — 기사 단위 짝 부트스트랩·반복 표준편차·'차이 없음' 판정(설계 §8-4).

같은 기사를 두 조건이 각각 요약했으므로 기사별 차이(조건 − 비교 대상)를 짝지어 보고,
기사를 복원 추출로 재표집해 평균 차이의 95% 신뢰구간을 구한다(기사가 12건뿐이라 정규 근사 대신).
"""
from __future__ import annotations

import math
import random
import statistics

from .common import SEED


def _percentile(sorted_vals: list[float], q: float) -> float:
    """선형 보간 백분위(q 는 0–100)."""
    idx = (len(sorted_vals) - 1) * q / 100
    lo, hi = math.floor(idx), math.ceil(idx)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (idx - lo)


def paired_bootstrap(diffs: dict[str, float], *, n: int = 10_000, seed: int = SEED) -> tuple[float, float, float]:
    """기사별 차이 → (평균, 2.5 백분위, 97.5 백분위). 짝이 하나도 없으면 NaN 세 개."""
    vals = [diffs[k] for k in sorted(diffs)]          # 정렬해 시드가 같으면 결과도 같게
    if not vals:
        return (math.nan, math.nan, math.nan)
    k = len(vals)
    rng = random.Random(seed)
    means = sorted(sum(rng.choices(vals, k=k)) / k for _ in range(n))
    return (sum(vals) / k, _percentile(means, 2.5), _percentile(means, 97.5))


def rep_sd(values: dict[str, list[float]]) -> float:
    """기사마다 같은 조건 반복 사이 표본표준편차(n−1)를 구해 평균. 반복이 2회 미만인 기사는 뺀다."""
    sds = [statistics.stdev(v) for v in values.values() if len(v) >= 2]
    return sum(sds) / len(sds) if sds else 0.0


def no_difference(ci: tuple[float, float, float], rep_sd: float) -> bool:
    """'차이 없음' = 구간이 0 을 포함하거나 평균 차이가 반복 표준편차보다 작다. 짝이 없으면(NaN) 차이를 주장할 수 없다."""
    mean, lo, hi = ci
    if any(math.isnan(x) for x in ci):
        return True
    return lo <= 0 <= hi or abs(mean) < rep_sd
