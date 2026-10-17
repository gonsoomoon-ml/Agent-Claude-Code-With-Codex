"""업그레이드 비교 실험 — Stage A(요약 AI 비교) 테스트: 운영 produce_card 경로·오류 기록·숫자 라우팅·재개."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from upgrade_eval import stage_a  # noqa: E402
from upgrade_eval.author_runner import ARMS  # noqa: E402
from upgrade_eval.codex_runner import VERIFIERS  # noqa: E402

from briefing.core.authoring.author import Claim, DraftCard  # noqa: E402
from briefing.core.config import load_settings  # noqa: E402
from briefing.core.gate import reroute_claim_types  # noqa: E402
from briefing.core.stores.source_store import SourceStore  # noqa: E402
from briefing.core.verification.certifier import CertVerdict  # noqa: E402

ARM, V, SETTINGS = ARMS["A2"], VERIFIERS["gpt-6-sol"], load_settings()


def _store(tmp_path):
    store = SourceStore(str(tmp_path / "src"))
    fs = store.freeze(url="https://www.aitimes.com/news/x", title="원제목", raw_text="본문 원문입니다. 가격은 2달러다. " * 30,
                      fetched_at="2026-10-17T00:00:00Z")
    return store, fs


def fake_author_fns(summary="S", raise_error=None):
    def draft(source, user, settings):
        if raise_error:
            raise RuntimeError(raise_error)
        return DraftCard(source.source_id, source.title, summary, "W",
                         (Claim("C1", "본문이 있다", "entailment", "core"),))

    def revise(source, user, settings, *, prior, failed_ids):
        return prior

    return draft, revise


def verified_all(card):
    return tuple(CertVerdict(c.id, "VERIFIED", "e", "test") for c in card.claims)


def test_run_one_records_publish(tmp_path):
    store, src = _store(tmp_path)
    rec = stage_a.run_one(ARM, src, 2, sequential=False, verifier=V, store=store, settings=SETTINGS,
                          author_fns=fake_author_fns(summary="S"), verify_fn=verified_all)
    assert (rec["decision"], rec["attempts"], rec["first_draft_summary"]) == ("PUBLISH", 1, "S")
    assert (rec["arm"], rec["rep"], rec["sequential"], rec["over_360"]) == ("A2", 2, False, False)


def test_run_one_records_error_on_timeout(tmp_path):
    store, src = _store(tmp_path)
    rec = stage_a.run_one(ARM, src, 2, sequential=False, verifier=V, store=store, settings=SETTINGS,
                          author_fns=fake_author_fns(raise_error="timeout"), verify_fn=lambda c: ())
    assert rec["decision"] == "ERROR" and rec["error"] == "timeout"


def test_verify_fn_routes_numbers_without_codex(monkeypatch, tmp_path):
    store, src = _store(tmp_path)
    called = []
    monkeypatch.setattr(stage_a, "certify_entailment_json", lambda *a, **k: called.append(1))
    log = []
    verify = stage_a.make_verify_fn(V, store, log)
    card = reroute_claim_types(DraftCard(src.source_id, "t", "s", "w", (Claim("C1", "가격은 2달러다", "entailment", "core"),)))
    (verdict,) = verify(card)
    assert called == [] and log == [] and verdict.model == "deterministic" and verdict.verdict == "VERIFIED"


def test_resume_skips_done(monkeypatch, tmp_path):
    store, src = _store(tmp_path)
    records = tmp_path / "records.jsonl"
    records.write_text(json.dumps({"arm": "A2", "source_id": src.source_id, "rep": 1}) + "\n", encoding="utf-8")
    monkeypatch.setattr(stage_a, "RECORDS", records)
    monkeypatch.setattr(stage_a, "load_manifest", lambda: [{"source_id": src.source_id}])
    monkeypatch.setattr(stage_a, "_store", lambda: store)
    calls = []
    monkeypatch.setattr(stage_a, "run_one", lambda *a, **k: calls.append(1) or {})
    stage_a.run_stage_a(["A2"], verifier="gpt-6-sol", reps=1, seq_rep=0)
    assert calls == []


# ── 유료 실행 전 보강: 순서·인프라 오류 재시도·예산 상한·검증 재시도 ──
from upgrade_eval.codex_runner import CodexRun  # noqa: E402
from upgrade_eval.common import read_jsonl  # noqa: E402


def test_plan_tasks_sequential_first_then_rep_blocks_by_arm():
    """순차(처리 시간) 회차를 먼저, 조건별로 이어서(캐시가 운영처럼 이어진다). 병렬은 회차 → 조건 → 기사 순 —
    상한에 걸려도 앞 회차는 모든 조건이 다 돈다."""
    arts = [{"source_id": "s1"}, {"source_id": "s2"}]
    seq, par = stage_a.plan_tasks(["A0", "A1"], arts, reps=3, seq_rep=1, done=set())
    assert [(a.key, s, r) for a, s, r in seq] == [("A0", "s1", 1), ("A0", "s2", 1), ("A1", "s1", 1), ("A1", "s2", 1)]
    assert [(a.key, s, r) for a, s, r in par] == [("A0", "s1", 2), ("A0", "s2", 2), ("A1", "s1", 2), ("A1", "s2", 2),
                                                   ("A0", "s1", 3), ("A0", "s2", 3), ("A1", "s1", 3), ("A1", "s2", 3)]
    _, par = stage_a.plan_tasks(["A0", "A1"], arts, reps=3, seq_rep=1, done={("A0", "s1", 2)})
    assert ("A0", "s1", 2) not in [(a.key, s, r) for a, s, r in par]


def test_infra_error_classification():
    assert stage_a.is_infra_error({"decision": "ERROR", "error": "rc=1: throttled"})
    assert stage_a.is_infra_error({"decision": "ERROR", "error": "is_error: API Error: 529 overloaded"})
    assert stage_a.is_infra_error({"decision": "ERROR", "error": "envelope 파싱 실패 rc=0: x"})
    assert not stage_a.is_infra_error({"decision": "ERROR", "error": "timeout"})                 # 느린 것은 모델 행동
    assert not stage_a.is_infra_error({"decision": "ERROR", "error": "Expecting value: line 1"})  # 카드 형식 실패도
    assert not stage_a.is_infra_error({"decision": "PUBLISH", "error": None})


def _patch_run(monkeypatch, tmp_path, store, sids):
    monkeypatch.setattr(stage_a, "RECORDS", tmp_path / "records.jsonl")
    monkeypatch.setattr(stage_a, "load_manifest", lambda: [{"source_id": s} for s in sids])
    monkeypatch.setattr(stage_a, "_store", lambda: store)


def _fake_run(outcome):
    """outcome(arm_key, sid) → (decision, error, author cost)."""
    def run(arm, source, rep, **k):
        d, e, cost = outcome(arm.key, source.source_id)
        return {"arm": arm.key, "source_id": source.source_id, "rep": rep, "decision": d, "error": e,
                "author_runs": [{"cost_usd": cost}], "codex_calls": [], "sequential": k["sequential"]}
    return run


def _sources(tmp_path, n):
    store = SourceStore(str(tmp_path / "src"))
    sids = [store.freeze(url=f"https://x.test/{i}", title="t", raw_text=f"본문 {i}. " * 30,
                         fetched_at="2026-10-17T00:00:00Z").source_id for i in range(n)]
    return store, sids


def test_run_retries_infra_errors_and_leaves_them_not_done(monkeypatch, tmp_path):
    store, sids = _sources(tmp_path, 1)
    _patch_run(monkeypatch, tmp_path, store, sids)
    outcomes = iter([("ERROR", "rc=1: throttled", 0.0), ("PUBLISH", None, 0.1)])
    kw = {"verifier": "gpt-6-luna", "reps": 1, "seq_rep": 0, "sleep": lambda s: None, "prices": {}}
    assert stage_a.run_stage_a(["A2"], run_one_fn=_fake_run(lambda a, s: next(outcomes)), **kw) is True
    assert [(r["decision"], r["attempt"]) for r in read_jsonl(tmp_path / "records.jsonl")] == [("ERROR", 1), ("PUBLISH", 2)]
    (tmp_path / "records.jsonl").write_text("", encoding="utf-8")
    stage_a.run_stage_a(["A2"], run_one_fn=_fake_run(lambda a, s: ("ERROR", "rc=1: throttled", 0.0)), **kw)
    stage_a.run_stage_a(["A2"], run_one_fn=_fake_run(lambda a, s: ("PUBLISH", None, 0.1)), **kw)
    assert read_jsonl(tmp_path / "records.jsonl")[-1]["decision"] == "PUBLISH"          # 인프라 오류는 '끝남'이 아니다
    calls = []
    stage_a.run_stage_a(["A2"], run_one_fn=lambda *a, **k: calls.append(1), **kw)
    assert calls == []                                                                   # 발행·모델 실패는 끝남


def test_run_stops_at_budget_with_rep_balance(monkeypatch, tmp_path):
    store, sids = _sources(tmp_path, 2)
    _patch_run(monkeypatch, tmp_path, store, sids)
    run = _fake_run(lambda a, s: ("PUBLISH", None, 1.0))                                # 카드당 $1
    done = stage_a.run_stage_a(["A0", "A1"], verifier="gpt-6-luna", reps=2, seq_rep=0, concurrency=1, budget=3.5,
                               run_one_fn=run, sleep=lambda s: None, prices={})
    recs = read_jsonl(tmp_path / "records.jsonl")
    assert done is False and len(recs) == 4 and {r["rep"] for r in recs} == {1}         # 1회차는 두 조건 모두 다 돈다


def test_run_breaker_stops_failing_arm(monkeypatch, tmp_path):
    store, sids = _sources(tmp_path, 4)
    _patch_run(monkeypatch, tmp_path, store, sids)
    run = _fake_run(lambda a, s: ("ERROR", "rc=1: AccessDenied", 0.0) if a == "A4" else ("PUBLISH", None, 0.0))
    done = stage_a.run_stage_a(["A0", "A4"], verifier="gpt-6-luna", reps=1, seq_rep=0, concurrency=1,
                               run_one_fn=run, sleep=lambda s: None, prices={})
    recs = read_jsonl(tmp_path / "records.jsonl")
    assert done is False and sum(r["arm"] == "A0" for r in recs) == 4
    assert sum(r["arm"] == "A4" for r in recs) == 3 * 3                                 # 3건 × 3번 시도 뒤 그 조건 중단


def test_verify_fn_retries_codex_infra_errors(tmp_path):
    store, src = _store(tmp_path)
    runs = iter([CodexRun(None, {}, 5, 1, "rc=1: throttled"),
                 CodexRun('{"verdict":"VERIFIED","evidence":"e"}', {"input_tokens": 1}, 5, 0, None)])
    log = []
    verify = stage_a.make_verify_fn(V, store, log, runner=lambda *a, **k: next(runs), sleep=lambda s: None)
    (v,) = verify(DraftCard(src.source_id, "t", "s", "w", (Claim("C1", "본문이 있다", "entailment", "core"),)))
    assert v.verdict == "VERIFIED" and [c["error"] for c in log] == ["rc=1: throttled", None]
