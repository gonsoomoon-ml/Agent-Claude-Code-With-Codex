"""eval set 회귀 — certifier 산술 검증기의 catch-rate / 위양성률 pin.

tests/eval_set/README.md 의 슬롯을 채운다: "검증 게이트가 rubber-stamp 가 아님을 catch-rate 로
증명하는 라벨 회귀셋 … 위양성(유령 BLOCK)도 함께".

★ 이 파일의 존재 이유 = **교차언어 숫자 정규화 PR 의 머지 게이트**.
   위양성(현재 100%)을 낮추는 수정은 catch-rate(현재 100%)를 **한 건도** 떨어뜨리면 안 된다.
   실측: 순진한 정규화기(영어 수사→숫자를 source 토큰집합에 주입)는 위양성 100%→20% 로 '성공'해 보이지만
   catch-rate 를 100%→50% 로 무너뜨린다(SY02·SY04·SY05·SY07). 위양성만 보고 머지하면
   verify-before-publish 의 중심 신뢰 속성이 *조용히* 붕괴한다.

LLM 호출 0 (arithmetic = 결정론 코드). entailment 케이스(GEN*)는 codex subprocess 가 필요해 CI 제외.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from briefing.core.verification.certifier import Envelope, _certify_arithmetic

_CASES = Path(__file__).parent / "eval_set" / "cases.jsonl"

# 2026-07-17 교차언어 숫자 정규화(numeric.py) 도입 후 기준. 도입 전 baseline 은 위양성 100%였다.
FALSE_POSITIVE_MAX = 0.10   # 유령 BLOCK — 정규화가 없애야 할 것
CATCH_RATE_MIN = 1.00       # ← 비협상: 절대 낮추지 말 것


def _load(kind: str | None = None) -> list[dict]:
    cases = [json.loads(line) for line in _CASES.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [c for c in cases if kind is None or c["claim_type"] == kind]


def _verdict(case: dict) -> str:
    env = Envelope(case["source_excerpt"], case["claim_text"], "arithmetic", "{}")
    return _certify_arithmetic(case["id"], env).verdict


def test_eval_set_wellformed() -> None:
    cases = _load()
    assert len(cases) >= 20, "README 스펙: ~20–30건"
    required = {"source_excerpt", "claim_text", "claim_type", "gold_verdict", "lang"}
    for c in cases:
        assert required <= set(c), f"{c['id']}: README 포맷 필드 누락"
        assert c["gold_verdict"] in {"VERIFIED", "DEMOTED", "BLOCKED"}


def test_false_positive_rate() -> None:
    """유령 BLOCK — gold=VERIFIED 인데 막히는 비율. 교차언어 숫자표기가 원인."""
    fp = [c for c in _load("arithmetic") if c["gold_verdict"] == "VERIFIED"]
    ghosts = [c for c in fp if _verdict(c) != "VERIFIED"]
    rate = len(ghosts) / len(fp)
    assert rate <= FALSE_POSITIVE_MAX, f"위양성률 {rate:.0%} > {FALSE_POSITIVE_MAX:.0%}: {[c['id'] for c in ghosts]}"


def test_catch_rate_no_regression() -> None:
    """catch-rate — gold=BLOCKED 를 실제로 잡는 비율. **정규화가 이걸 깎으면 머지 금지.**"""
    cat = [c for c in _load("arithmetic") if c["gold_verdict"] == "BLOCKED"]
    missed = [c for c in cat if _verdict(c) == "VERIFIED"]
    rate = (len(cat) - len(missed)) / len(cat)
    assert rate >= CATCH_RATE_MIN, f"catch-rate {rate:.0%} < {CATCH_RATE_MIN:.0%} — 진양성 유실: {[c['id'] for c in missed]}"


@pytest.mark.parametrize("cid", ["SY02", "SY04", "SY07", "SY08"])
def test_adversarial_shortcut_cases(cid: str) -> None:
    """정규화기가 택하기 쉬운 지름길을 정조준한 케이스 — 개별로 이름 붙여 실패 원인을 즉시 읽히게."""
    c = next(x for x in _load() if x["id"] == cid)
    assert _verdict(c) != "VERIFIED", f"{cid} ({c['bug_class']}) 통과됨 — {c['note']}"


@pytest.mark.skip(reason="entailment = codex subprocess 필요(CI 에서 LLM 호출 0 유지). 수동 실행용 기록.")
def test_entailment_genuine_refutations() -> None:
    for c in _load("entailment"):
        assert c["gold_verdict"] == "DEMOTED"
