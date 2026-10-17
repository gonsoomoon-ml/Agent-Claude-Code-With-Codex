"""업그레이드 비교 실험 — Stage B(검증 AI 비교) 테스트: claim 세트·심은 오류 검사·채점·승자 규칙·비용."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from upgrade_eval import costs, stage_b  # noqa: E402
from upgrade_eval.stage_b import PLANTED_TYPES, ClaimItem, ModelScore  # noqa: E402

ORIGINALS = [ClaimItem(f"s:C{i}", "s", f"원본 문장 {chr(0xAC00 + i)}", "original") for i in range(40)]


def _planted(type_counts: dict[str, int], digit_text: str | None = None) -> list[ClaimItem]:
    items, n = [], 0
    for t, k in type_counts.items():
        for _ in range(k):
            items.append(ClaimItem(f"p:{n}", "s", f"바꾼 문장 {chr(0xAC00 + n)}", "planted", t, ORIGINALS[n % 40].key))
            n += 1
    if digit_text:
        items.append(ClaimItem(f"p:{n}", "s", digit_text, "planted", PLANTED_TYPES[0], ORIGINALS[0].key))
    return items


def _records(model: str, verdict_for: dict[str, str]) -> list[dict]:
    return [{"model": model, "pass": p, "claim_key": k, "verdict": v, "usage": {"input_tokens": 1000, "output_tokens": 10},
             "duration_ms": 1000, "error": None} for p in (1, 2) for k, v in verdict_for.items()]


def ms(catch, fp, cost, p95):
    return ModelScore(catch, catch, fp, fp, 0.0, 1.0, cost, False, p95 / 2, p95, 0, 10, 0)


def test_original_claims_entailment_only():
    sid = "s" * 12
    cards = [{"decision": "PUBLISH", "card": {"source_id": sid, "based_on": [], "claims": [
        {"id": "C1", "text": "A사는 출시했다", "claim_type": "entailment", "importance": "core"},
        {"id": "C2", "text": "가격은 2달러다", "claim_type": "arithmetic", "importance": "core"},
        {"id": "C3", "text": "B는 3배다", "claim_type": "entailment", "importance": "supporting"}]}}]
    assert [c.key for c in stage_b.original_claims(cards, {sid})] == [f"{sid}:C1"]


def test_validate_planted_counts_and_digits():
    counts = {t: 6 for t in PLANTED_TYPES} | {"유보→단정": 5}
    errs = stage_b.validate_planted(_planted(counts, digit_text="X사는 3배 빨라졌다고 밝혔다"), ORIGINALS)
    assert any("유보→단정" in e and "5" in e for e in errs) and any("숫자" in e for e in errs)
    assert stage_b.validate_planted(_planted({t: 6 for t in PLANTED_TYPES}), ORIGINALS) == []


def test_degenerate_demote_everything_loses():
    planted = _planted({t: 6 for t in PLANTED_TYPES})
    claims = ORIGINALS[:10] + planted
    good = {c.key: "VERIFIED" for c in ORIGINALS[:10]} | {c.key: "BLOCKED" for c in planted}
    records = _records("lazy", {c.key: "DEMOTED" for c in claims})
    for m in ("gpt-5.5", "m2", "m3", "m4"):
        records += _records(m, good)
    prices = {m: costs.Price(1.0, 1.0, None, False, "test") for m in ("lazy", "gpt-5.5", "m2", "m3", "m4")}
    scores = stage_b.score_stage_b(records, claims, prices)
    assert scores["lazy"].catch_rate == 1.0 and scores["lazy"].fp_rate == 1.0
    assert scores["m2"].fp_rate == 0.0 and scores["m2"].n_true == 10
    assert stage_b.pick_winner(scores) != "lazy"


def test_pick_winner_rules():
    s = {"gpt-5.5": ms(catch=.80, fp=.05, cost=.04, p95=9000), "a": ms(catch=.90, fp=.08, cost=.10, p95=8000),
         "b": ms(catch=.87, fp=.07, cost=.02, p95=7000), "c": ms(catch=.70, fp=.01, cost=.001, p95=5000)}
    assert stage_b.pick_winner(s) == "b"   # c 는 기준선 미만, a·b 는 오탐 2%p 이내 → 비용이 낮은 b


def test_codex_cost_with_cache():
    p = costs.Price(2.0, 10.0, 0.5, False, "2차")
    usage = {"input_tokens": 10_000, "cached_input_tokens": 4_000, "output_tokens": 100, "reasoning_output_tokens": 50}
    assert costs.codex_cost(usage, p) == pytest.approx((6_000 * 2.0 + 4_000 * 0.5 + 100 * 10.0) / 1e6)


def test_codex_cost_charges_cache_writes():
    p = costs.Price(2.0, 10.0, 0.2, False, "2차", cache_write=2.5)
    usage = {"input_tokens": 10_964, "cached_input_tokens": 0, "cache_write_input_tokens": 10_922, "output_tokens": 88}
    assert costs.codex_cost(usage, p) == pytest.approx((42 * 2.0 + 10_922 * 2.5 + 88 * 10.0) / 1e6)


def test_load_prices_falls_back_then_reads_verified_file(tmp_path):
    assert costs.load_prices(tmp_path / "missing.json") == costs.FALLBACK_PRICES
    f = tmp_path / "prices.json"
    f.write_text('{"gpt-6-sol": {"input": 2.2, "output": 11.0, "cache_read": 0.22, "verified": true, '
                 '"source": "AWS Price List API 2026-10-17", "cache_write": null}}', encoding="utf-8")
    prices = costs.load_prices(f)
    assert prices["gpt-6-sol"] == costs.Price(2.2, 11.0, 0.22, True, "AWS Price List API 2026-10-17", None)
    assert prices["gpt-6-astra"] == costs.FALLBACK_PRICES["gpt-6-astra"]   # 파일에 없는 모델은 2차 출처 유지
