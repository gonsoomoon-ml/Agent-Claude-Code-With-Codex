"""업그레이드 비교 실험 — 통계 테스트: 짝 부트스트랩·반복 표준편차·차이 없음 판정."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from upgrade_eval import stats  # noqa: E402


def test_bootstrap_deterministic():
    d = {"a": 1.0, "b": 1.0, "c": 1.0}
    assert stats.paired_bootstrap(d) == (1.0, 1.0, 1.0)
    d2 = {"a": 0.1, "b": -0.2, "c": 0.4}
    assert stats.paired_bootstrap(d2, seed=7) == stats.paired_bootstrap(d2, seed=7)
    mean, lo, hi = stats.paired_bootstrap(d2, seed=7)
    assert mean == pytest.approx(0.1) and lo <= mean <= hi and lo >= -0.2 - 1e-12 and hi <= 0.4 + 1e-12


def test_rep_sd():
    assert stats.rep_sd({"a": [1.0, 1.0, 1.0], "b": [0.0, 2.0]}) == pytest.approx(2 ** 0.5 / 2)   # (0 + √2) / 2, 표본표준편차
    assert stats.rep_sd({"a": [3.0]}) == 0.0                                                      # 반복 1회뿐이면 잴 수 없음


def test_bootstrap_empty_is_nan_and_counts_as_no_difference():
    import math
    ci = stats.paired_bootstrap({})
    assert all(math.isnan(x) for x in ci)
    assert stats.no_difference(ci, 0.0)            # 짝이 없으면 '차이 있음'을 주장할 수 없다


def test_no_difference():
    assert stats.no_difference((0.1, -0.05, 0.25), 0.0)
    assert stats.no_difference((0.1, 0.05, 0.15), 0.2)
    assert not stats.no_difference((0.1, 0.05, 0.15), 0.01)
