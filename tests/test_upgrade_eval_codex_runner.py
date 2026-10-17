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


def test_certify_accepts_lowercase_verdict_like_production():
    run = CodexRun('{"verdict":"Verified","evidence":"e"}', {}, 5, 0, None)    # 운영은 .upper() 로 받는다
    v, _ = codex_runner.certify_entailment_json("C1", ENV, VERIFIERS["gpt-6-sol"], runner=lambda *a, **k: run)
    assert (v.verdict, v.model) == ("VERIFIED", "codex:gpt-6-sol")


def _fake_codex(root: Path, body: str) -> codex_runner.CodexModel:
    model = codex_runner.CodexModel("fake", "test", "x")
    bin_ = root / "bin" / "codex-test" / "node_modules" / ".bin" / "codex"
    bin_.parent.mkdir(parents=True)
    bin_.write_text("#!/bin/sh\n" + body, encoding="utf-8")
    bin_.chmod(0o755)
    return model


def _alive(pid: int) -> bool:
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
    except FileNotFoundError:
        return False
    return stat.rsplit(")", 1)[1].split()[0] != "Z"      # 좀비는 이미 죽은 것


def test_timeout_kills_wrapper_children(monkeypatch, tmp_path):
    """node 래퍼만 죽이면 네이티브 codex 가 고아로 남아 토큰을 계속 쓴다 — 프로세스 그룹째 꺼야 한다."""
    import time
    monkeypatch.setattr(codex_runner, "EXP_ROOT", tmp_path)
    pidfile = tmp_path / "child.pid"
    model = _fake_codex(tmp_path, f"sleep 300 &\necho $! > {pidfile}\nwait\n")
    run = codex_runner.run_codex_json("p", model, timeout_s=1)
    assert run.error == "timeout"
    pid = int(pidfile.read_text())
    deadline = time.monotonic() + 5
    while _alive(pid) and time.monotonic() < deadline:
        time.sleep(0.1)
    assert not _alive(pid)


def test_effort_read_from_codex_home_config(monkeypatch, tmp_path):
    monkeypatch.setattr(codex_runner, "EXP_ROOT", tmp_path)
    model = codex_runner.CodexModel("fake", "test", "x")
    assert model.effort is None
    model.codex_home.mkdir(parents=True)
    (model.codex_home / "config.toml").write_text('model_reasoning_effort = "medium"\nmodel = "x"\n', encoding="utf-8")
    assert model.effort == "medium"
