"""업그레이드 비교 실험 — Stage B(검증 AI 비교) 테스트: claim 세트·심은 오류 검사·채점·승자 규칙·비용."""
import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from upgrade_eval import codex_runner, costs, stage_b  # noqa: E402
from upgrade_eval.codex_runner import VERIFIERS, CodexRun  # noqa: E402
from upgrade_eval.common import read_jsonl  # noqa: E402
from upgrade_eval.stage_b import PLANTED_TYPES, ClaimItem, ModelScore  # noqa: E402

from briefing.core.stores.source_store import FrozenSource  # noqa: E402

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
    """1·2차 전부 + 처리 시간 측정(seq) 1건 — 측정이 없으면 승자를 고르지 않는다."""
    first = next(iter(verdict_for))
    return [{"model": model, "pass": p, "claim_key": k, "verdict": v, "usage": {"input_tokens": 1000, "output_tokens": 10},
             "duration_ms": 1000, "error": None} for p in (1, 2) for k, v in verdict_for.items()] + [
            {"model": model, "pass": "seq", "claim_key": first, "verdict": verdict_for[first], "usage": {},
             "duration_ms": 1000, "error": None}]


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
    scores = stage_b.score_stage_b(records, claims, prices, models=["lazy", "gpt-5.5", "m2", "m3", "m4"])
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


# ── 사전 리뷰 반영: 기록 감사·재시도·예산·채점 완전성·건강 필터 ──
MODELS5 = ["gpt-5.5", "m2", "m3", "m4", "m5"]
PRICES5 = {m: costs.Price(1.0, 1.0, None, False, "test") for m in MODELS5}
OK = CodexRun('{"verdict":"VERIFIED","evidence":"e"}', {"input_tokens": 1_000_000, "output_tokens": 0}, 5, 0, None)


class _Store:
    def get_source(self, sid):
        return FrozenSource(sid, "https://x.test/a", "제목", "원문 본문이다. " * 5, "2026-10-17T00:00:00Z")


def _rec(model, p, key, verdict, *, error=None, cert=None, usage=None, ms=1000):
    return {"model": model, "pass": p, "claim_key": key, "verdict": verdict, "error": error,
            "cert_model": cert or f"codex:{model}", "duration_ms": ms,
            "usage": {"input_tokens": 1000, "output_tokens": 10} if usage is None else usage}


def test_certify_record_keeps_audit_fields(monkeypatch, tmp_path):
    monkeypatch.setattr(codex_runner, "EXP_ROOT", tmp_path)
    home = VERIFIERS["gpt-6-sol"].codex_home
    home.mkdir(parents=True)
    (home / "config.toml").write_text('model_reasoning_effort = "medium"\n', encoding="utf-8")
    run = CodexRun('{"verdict":"BLOCKED","evidence":"반대"}', {"input_tokens": 9}, 5, 0, None)
    rec = stage_b._certify("gpt-6-sol", ORIGINALS[0], _Store(), 1, runner=lambda *a, **k: run)
    assert rec["cert_model"] == "codex:gpt-6-sol" and rec["final_text"].startswith('{"verdict"')
    assert (rec["codex_version"], rec["effort"], rec["attempt"], rec["verdict"]) == ("0.163.0", "medium", 1, "BLOCKED")


def test_run_task_retries_infra_errors_only():
    calls = []

    def flaky(prompt, model, timeout_s=120):
        calls.append(1)
        return CodexRun(None, {}, 5, 1, "rc=1: throttled") if len(calls) == 1 else OK

    recs = stage_b.run_task("gpt-6-sol", ORIGINALS[0], _Store(), 1, runner=flaky, sleep=lambda s: None)
    assert [r["attempt"] for r in recs] == [1, 2] and stage_b.is_infra_error(recs[0]) and recs[1]["verdict"] == "VERIFIED"
    timeout = CodexRun(None, {}, 120_000, None, "timeout")
    recs = stage_b.run_task("gpt-6-sol", ORIGINALS[0], _Store(), 1, runner=lambda *a, **k: timeout, sleep=lambda s: None)
    assert len(recs) == 1 and not stage_b.is_infra_error(recs[0])        # 시간 초과는 모델 행동 — 재시도 안 함


def _patch_run(monkeypatch, tmp_path, claims):
    monkeypatch.setattr(stage_b, "RECORDS", tmp_path / "records.jsonl")
    monkeypatch.setattr(stage_b, "_load_claims", lambda: (claims, []))
    monkeypatch.setattr(stage_b, "_store", lambda: _Store())


def test_run_stops_at_budget_and_finishes_pass1_first(monkeypatch, tmp_path):
    _patch_run(monkeypatch, tmp_path, ORIGINALS[:5])
    prices = {m: costs.Price(2.0, 10.0, None, False, "t") for m in VERIFIERS}       # 호출당 $2
    kw = {"runner": lambda *a, **k: OK, "sleep": lambda s: None, "prices": prices, "models": ["gpt-6-sol"]}
    assert stage_b.cmd_run(2, 1, budget=7.0, **kw) is False
    recs = read_jsonl(tmp_path / "records.jsonl")
    assert len(recs) == 4 and all(r["pass"] == 1 for r in recs)                    # $8 ≥ $7 에서 멈춤
    assert stage_b.cmd_run(2, 1, budget=1000.0, **kw) is True                       # 재개: 앞의 $8 도 예산에 든다
    passes = [r["pass"] for r in read_jsonl(tmp_path / "records.jsonl")]
    assert passes == [1] * 5 + [2] * 5                                               # 1차를 다 끝낸 뒤 2차


def test_run_breaker_stops_failing_model_and_errors_are_rerun(monkeypatch, tmp_path):
    _patch_run(monkeypatch, tmp_path, ORIGINALS[:15])
    bad = CodexRun(None, {}, 5, 1, "rc=1: AccessDenied")
    kw = {"sleep": lambda s: None, "prices": {}, "models": ["gpt-6-sol"]}
    assert stage_b.cmd_run(1, 1, budget=100.0, runner=lambda *a, **k: bad, **kw) is False
    assert len(read_jsonl(tmp_path / "records.jsonl")) == 12                        # 4건 × 3번 시도 = 연속 12회 ≥ 10
    assert stage_b.cmd_run(1, 1, budget=100.0, runner=lambda *a, **k: OK, **kw) is True
    assert len(read_jsonl(tmp_path / "records.jsonl")) == 12 + 15                   # 인프라 오류는 '끝남'이 아니다


def test_score_refuses_incomplete_pass1():
    claims = ORIGINALS[:3]
    recs = [_rec(m, 1, c.key, "VERIFIED") for m in MODELS5[:4] for c in claims]     # m5 기록 없음
    with pytest.raises(ValueError, match="1차"):
        stage_b.score_stage_b(recs, claims, PRICES5, models=MODELS5)


def test_score_dedupes_latest_and_skips_infra_errors():
    claims = ORIGINALS[:2]
    recs = [_rec(m, 1, c.key, "VERIFIED") for m in MODELS5 for c in claims]
    recs.append(_rec("m2", 1, claims[0].key, "BLOCKED"))                             # 재실행 — 최신 기록만
    recs.append(_rec("m3", 1, claims[1].key, "DEMOTED", error="rc=1: throttled", cert="codex-error", usage={}))
    s = stage_b.score_stage_b(recs, claims, PRICES5, models=MODELS5)
    assert s["m2"].fp_rate == pytest.approx(0.5) and s["m3"].fp_rate == 0.0
    assert s["m2"].n_true == 2                                                       # C0 은 VERIFIED 4표 ≥ 4


def test_errors_never_help_and_timeouts_count_in_latency():
    claims = ORIGINALS[:2] + _planted({PLANTED_TYPES[0]: 2})
    recs = []
    for m in MODELS5:
        recs += [_rec(m, 1, c.key, "VERIFIED") for c in claims[:2]] + [_rec(m, 1, c.key, "BLOCKED") for c in claims[2:]]
    recs = [r for r in recs if not (r["model"] == "m5" and r["claim_key"] == claims[2].key)]
    recs.append(_rec("m5", 1, claims[2].key, "DEMOTED", error="timeout", cert="codex-error", usage={}, ms=120_000))
    recs += [_rec("m5", "seq", claims[0].key, "VERIFIED"),
             _rec("m5", "seq", claims[1].key, "DEMOTED", error="timeout", cert="codex-error", usage={}, ms=120_000)]
    s = stage_b.score_stage_b(recs, claims, PRICES5, models=MODELS5)
    assert s["m5"].catch_rate == pytest.approx(0.5) and s["m5"].error_rate == pytest.approx(0.25)
    assert s["m5"].cost_per_claim == pytest.approx(s["m4"].cost_per_claim)          # 사용량 없는 기록은 비용 평균에서 뺀다
    assert s["m5"].p95_ms > 100_000 and s["m5"].errors == {"timeout": 2}
    assert math.isnan(s["m4"].p95_ms)                                                # 처리 시간 측정 없음 → NaN


def test_pick_winner_healthy_filter_closes_the_hole():
    s = {"gpt-5.5": ms(.85, .05, .04, 9000), "a": ms(.88, .06, .03, 8000), "b": ms(.90, .08, .02, 7000),
         "cautious": ms(.97, .30, .01, 5000)}
    assert stage_b.pick_winner(s) == "cautious"                   # 승인된 규칙 그대로: 최고 검출률만 후보로 남는다
    assert stage_b.pick_winner(s, healthy_only=True) == "a"      # 오탐 > 기준선+10%p 를 빼고 같은 규칙 적용
    s["b"].error_rate = 0.2
    assert stage_b.pick_winner(s, healthy_only=True) == "a"
    s["gpt-5.5"].error_rate = 0.2
    with pytest.raises(ValueError, match="기준선"):
        stage_b.pick_winner(s, healthy_only=True)


def test_pick_winner_refuses_nan():
    with pytest.raises(ValueError, match="NaN"):
        stage_b.pick_winner({"gpt-5.5": ms(.85, .05, math.nan, 9000), "a": ms(.88, .06, .03, 8000)})
