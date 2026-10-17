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
