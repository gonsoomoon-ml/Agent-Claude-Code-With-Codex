"""숫자 검사가 막은 claim 의 codex 2차 판정(2026-10-18) — 가짜 codex 로 분기마다 고정한다.

실측 근거(work_note F2): 30일 운영 BLOCKED 64건 중 숫자가 틀린 claim 은 0건이었다. 숫자 claim 전용 엄격 지시 +
'뒤집힌 한국어 분수는 코드가 최종' 규칙으로, 날조 51건 통과 0 · 맞는 claim 18건 전부 풀림(GPT-5.5·Luna 각 2회).
"""
from pathlib import Path

import pytest

from briefing.core.verification import certifier as cert
from briefing.core.verification.certifier import Envelope, certify

_LEO_SRC = 'Pope Leo XIV said that "algorithms lack the spark of humanity."'
_LEO_CLAIM = "교황 레오 14세는 알고리즘에 인간성의 불꽃이 없다고 말했다."


def _codex(monkeypatch, reply: str = "", exc: Exception | None = None) -> list[str]:
    """가짜 codex — 받은 프롬프트를 기록하고 정해진 답(또는 예외)을 낸다."""
    calls: list[str] = []

    def fake(prompt, **kw):
        calls.append(prompt)
        if exc is not None:
            raise exc
        return reply

    monkeypatch.setattr(cert, "_run_codex", fake)
    return calls


def test_numbers_that_match_never_call_codex(monkeypatch):
    calls = _codex(monkeypatch, '{"verdict":"BLOCKED","evidence":"x"}')
    v = certify("C1", Envelope("Revenue reached $7 billion.", "매출은 70억 달러였다.", "arithmetic", "{}"))
    assert (v.verdict, v.model) == ("VERIFIED", "deterministic")
    assert calls == []


def test_blocked_number_is_released_when_codex_confirms(monkeypatch):
    """'Leo XIV' ↔ '레오 14세' — 숫자가 말로 쓰인 같은 뜻은 코드가 못 보고 codex 가 본다."""
    _codex(monkeypatch, '{"verdict":"VERIFIED","evidence":"Pope Leo XIV said it"}')
    v = certify("C1", Envelope(_LEO_SRC, _LEO_CLAIM, "arithmetic", "{}"))
    assert (v.verdict, v.model) == ("VERIFIED", "deterministic→codex")
    assert "원문에 없는 수치" in v.evidence and "Pope Leo XIV said it" in v.evidence   # 두 판정 모두 감사 기록에


@pytest.mark.parametrize("reply", [
    '{"verdict":"DEMOTED","evidence":"not determinable"}',
    '{"verdict":"BLOCKED","evidence":"XIV is not 15"}',
    "not json at all",
])
def test_block_stays_unless_codex_verifies(monkeypatch, reply):
    _codex(monkeypatch, reply)
    v = certify("C1", Envelope(_LEO_SRC, _LEO_CLAIM, "arithmetic", "{}"))
    assert (v.verdict, v.model) == ("BLOCKED", "deterministic")


def test_codex_failure_keeps_the_block(monkeypatch):
    _codex(monkeypatch, exc=RuntimeError("codex down"))
    assert certify("C1", Envelope(_LEO_SRC, _LEO_CLAIM, "arithmetic", "{}")).verdict == "BLOCKED"


def test_inverted_korean_fraction_is_final_without_codex(monkeypatch):
    """'2분의 3'(=1.5)을 codex 는 '3분의 2'로 좋게 읽는다(실측, 지시로도 안 고쳐짐) — 코드가 최종 판정."""
    calls = _codex(monkeypatch, '{"verdict":"VERIFIED","evidence":"two-thirds"}')
    v = certify("C1", Envelope("LinkedIn accounted for nearly two-thirds of all detected AI content.",
                               "LinkedIn은 탐지된 AI 콘텐츠의 거의 2분의 3을 차지했다.", "arithmetic", "{}"))
    assert v.verdict == "BLOCKED"
    assert calls == []


def test_codex_sees_only_the_envelope_plus_numeric_rules(monkeypatch):
    calls = _codex(monkeypatch, '{"verdict":"VERIFIED","evidence":"e"}')
    certify("C1", Envelope(_LEO_SRC, _LEO_CLAIM, "arithmetic", "{}"))
    prompt = calls[0]
    assert "원문에 없는 수치" not in prompt and "deterministic" not in prompt   # 코드 판정은 안 보여준다(독립성)
    assert _LEO_SRC in prompt and _LEO_CLAIM in prompt
    assert "Check EVERY number" in prompt                                     # 숫자 claim 전용 엄격 지시


def test_entailment_prompt_has_no_numeric_rules():
    """숫자 없는 claim 의 codex 지시는 그대로다(Stage B 로 잰 판정을 바꾸지 않는다)."""
    assert "Check EVERY number" not in cert._build_codex_prompt(Envelope("s", "c", "entailment", "{}"))


def test_second_opinion_tokens_reach_cost_recording(monkeypatch):
    """2차 판정의 codex 토큰도 verdict 에 실린다 → F5 비용 기록에 들어간다(이 표본의 최종 답은 BLOCKED)."""
    sample = (Path(__file__).parent / "fixtures" / "codex_json_sample_0163.jsonl").read_text(encoding="utf-8")
    _codex(monkeypatch, sample)
    v = certify("C1", Envelope(_LEO_SRC, _LEO_CLAIM, "arithmetic", "{}"))
    assert v.verdict == "BLOCKED"
    assert v.usage["input_tokens"] == 10964
