"""검증 AI 를 `codex exec --json` 으로 부르고, 이벤트 줄에서 최종 답과 토큰 사용량을 읽는다(F5).

실제 출력 표본 = tests/fixtures/codex_json_sample_{0142,0163}.jsonl
(codex 0.142.2·GPT-5.5 / 0.163.0·GPT-6 Sol — 실험 U3 에서 받은 그대로).
"""
from pathlib import Path

import pytest

from briefing.core.verification import certifier as cert
from briefing.core.verification.certifier import Envelope

FIX = Path(__file__).parent / "fixtures"


def _fixture(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def test_codex_runs_with_json_events():
    assert "--json" in cert._CODEX_CMD


@pytest.mark.parametrize("name, tokens_in, tokens_out", [
    ("codex_json_sample_0142.jsonl", 7900, 127),
    ("codex_json_sample_0163.jsonl", 10964, 88),
])
def test_parse_events_returns_final_answer_and_usage(name, tokens_in, tokens_out):
    text, usage = cert._parse_codex_events(_fixture(name))
    assert cert._last_json_object(text)["verdict"] == "BLOCKED"
    assert (usage["input_tokens"], usage["output_tokens"]) == (tokens_in, tokens_out)


def test_parse_events_falls_back_to_plain_output():
    """--json 이 아닌 평문(예전 형식)도 그대로 읽힌다 — 마지막 JSON object 규칙 유지, 사용량은 없음."""
    text, usage = cert._parse_codex_events('생각 중...\n{"verdict":"VERIFIED","evidence":"e"}\n')
    assert cert._last_json_object(text)["verdict"] == "VERIFIED" and usage == {}


def test_entailment_verdict_carries_token_usage(monkeypatch):
    monkeypatch.setattr(cert, "_run_codex", lambda prompt, **kw: _fixture("codex_json_sample_0163.jsonl"))
    v = cert.certify("C1", Envelope("원문", "주장", "entailment", "{}"))
    assert (v.verdict, v.model) == ("BLOCKED", "codex")
    assert v.usage["input_tokens"] == 10964


def test_events_without_final_answer_fail_closed(monkeypatch):
    """최종 답 없이 끝난 이벤트(오류 등)는 절대 VERIFIED 가 아니다 — 마지막 이벤트를 답으로 오인하지 않는다."""
    events = '{"type":"thread.started"}\n{"type":"turn.completed","usage":{"input_tokens":5,"output_tokens":1}}\n'
    monkeypatch.setattr(cert, "_run_codex", lambda prompt, **kw: events)
    assert cert.certify("C1", Envelope("원문", "주장", "entailment", "{}")).verdict == "DEMOTED"


def test_codex_model_id_reads_codex_config(tmp_path, monkeypatch):
    """검증 모델은 codex 설정이 소유 — 우리는 단가를 고르려고 읽기만 한다."""
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    assert cert.codex_model_id() == ""                       # 설정 없음 → 빈 값
    (tmp_path / "config.toml").write_text('model_provider = "amazon-bedrock"\nmodel = "openai.gpt-6-luna"\n',
                                          encoding="utf-8")
    assert cert.codex_model_id() == "openai.gpt-6-luna"
