"""업그레이드 비교 실험 — codex --json 러너 테스트(이벤트 파서·fail-closed 판정·허용 목록 env)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from upgrade_eval import codex_runner  # noqa: E402
from upgrade_eval.codex_runner import VERIFIERS, CodexRun  # noqa: E402

from briefing.core.verification.certifier import Envelope  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"
ENV = Envelope(source_excerpt="원문", claim_text="A사는 출시했다", claim_type="entailment", schema="{}")


def test_parse_takes_last_agent_message_and_usage():
    out = "\n".join([
        '{"type":"thread.started","thread_id":"t"}',
        '{"type":"item.completed","item":{"type":"agent_message","text":"draft"}}',
        "not json",
        '{"type":"item.completed","item":{"type":"agent_message","text":"{\\"verdict\\":\\"VERIFIED\\",\\"evidence\\":\\"e\\"}"}}',
        '{"type":"turn.completed","usage":{"input_tokens":9000,"cached_input_tokens":0,"output_tokens":40,"reasoning_output_tokens":12}}',
    ])
    text, usage = codex_runner.parse_codex_jsonl(out)
    assert text.startswith('{"verdict"')
    assert usage == {"input_tokens": 9000, "cached_input_tokens": 0, "output_tokens": 40, "reasoning_output_tokens": 12}


def test_parse_recorded_samples():
    for name in ("codex_json_sample_0142.jsonl", "codex_json_sample_0163.jsonl"):
        text, usage = codex_runner.parse_codex_jsonl((FIXTURES / name).read_text(encoding="utf-8"))
        assert text and "verdict" in text and usage["input_tokens"] > 0


def test_parse_missing_message():
    assert codex_runner.parse_codex_jsonl('{"type":"turn.completed","usage":{}}') == (None, {})


def test_certify_is_fail_closed():
    for run in (CodexRun(None, {}, 5, 1, "rc=1"), CodexRun(None, {}, 120000, None, "timeout"),
                CodexRun("not json", {}, 5, 0, None), CodexRun('{"verdict":"MAYBE"}', {}, 5, 0, None)):
        v, _ = codex_runner.certify_entailment_json("C1", ENV, VERIFIERS["gpt-6-sol"], runner=lambda *a, run=run, **k: run)
        assert v.verdict == "DEMOTED" and v.model == "codex-error"


def test_certify_passes_verdict_through():
    run = CodexRun('{"verdict":"BLOCKED","evidence":"반대"}', {"input_tokens": 1}, 5, 0, None)
    v, r = codex_runner.certify_entailment_json("C1", ENV, VERIFIERS["gpt-5.5"], runner=lambda *a, **k: run)
    assert (v.verdict, v.model, r.usage) == ("BLOCKED", "codex:gpt-5.5", {"input_tokens": 1})


def test_codex_env_is_allowlisted(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.setenv("CLAUDECODE", "1")
    model = VERIFIERS["gpt-6-sol"]
    env = codex_runner.build_codex_env(model, home_dir=tmp_path)
    assert env["CODEX_HOME"] == str(model.codex_home) and env["HOME"] == str(tmp_path)
    assert env["AWS_REGION"] == "us-east-1"
    assert "ANTHROPIC_API_KEY" not in env and "CLAUDECODE" not in env
    assert str(model.codex_bin.parent) in env["PATH"].split(":")
