"""업그레이드 비교 실험 — 판정자 테스트: 스키마 파서·재시도·판정자 검증(세는 단위)·대체 규칙."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from upgrade_eval import judge  # noqa: E402
from upgrade_eval.judge import PlantedSummary  # noqa: E402

FOUR = "가는 출시했다. 나는 늘었다. 다는 밝혔다. 라는 예정이다."   # 4문장
ONE = "가는 출시했다."


class FakeConverse:
    def __init__(self, texts):
        self.texts, self.calls = list(texts), 0

    def converse(self, **kwargs):
        self.calls += 1
        text = self.texts.pop(0)
        return {"output": {"message": {"content": [{"reasoningContent": {"x": 1}}, {"text": text}]}},
                "usage": {"inputTokens": 10, "outputTokens": 5}, "metrics": {"latencyMs": 7}}


def test_parse_fidelity_rejects_unknown_label_and_bad_index():
    with pytest.raises(ValueError):
        judge.parse_fidelity({"sentences": [{"idx": 0, "labels": ["과장"]}]}, 3)
    with pytest.raises(ValueError):
        judge.parse_fidelity({"sentences": [{"idx": 5, "labels": []}]}, 3)
    assert judge.parse_fidelity({"sentences": [{"idx": 1, "labels": ["귀속 누락"], "evidence": "e"}]}, 3) == {1: ["귀속 누락"]}
    assert judge.parse_fidelity({"sentences": []}, 3) == {}


def test_parse_keyfacts_positions():
    src = "앞부분 문장. " + "가" * 100 + " 결론: 출시는 내년이다."
    facts = judge.parse_keyfacts({"facts": [{"id": "K1", "text": "출시는 내년", "quote": "출시는 내년이다",
                                             "category": "단서", "ai_related": False}]}, src)
    assert facts[0].tercile == "뒤" and facts[0].position > 0.66
    with pytest.raises(ValueError):
        judge.parse_keyfacts({"facts": [{"id": "K1", "text": "x", "quote": "x", "category": "기타", "ai_related": False}]}, src)
    with pytest.raises(ValueError):
        judge.parse_keyfacts({"facts": []}, src)
    missing = judge.parse_keyfacts({"facts": [{"id": "K2", "text": "y", "quote": "원문에 없음", "category": "수치",
                                               "ai_related": True}]}, src)
    assert missing[0].position is None and missing[0].tercile is None


def test_parse_align_requires_every_fact():
    covered, first_new = judge.parse_align({"covered": {"K1": True, "K2": False}, "first_sentence_is_new_fact": True},
                                           ["K1", "K2"], 4)
    assert covered == {"K1": True, "K2": False} and first_new is True
    with pytest.raises(ValueError):
        judge.parse_align({"covered": {"K1": True}, "first_sentence_is_new_fact": True}, ["K1", "K2"], 4)


def test_parse_pairwise_and_bypass():
    assert judge.parse_pairwise({"better": "second"}) == "second"
    with pytest.raises(ValueError):
        judge.parse_pairwise({"better": "B"})
    assert judge.parse_bypass({"uncovered": ["사실 하나"]}) == ["사실 하나"]


def test_converse_retries_once_then_errors():
    client = FakeConverse(["no json", "still no json"])
    call = judge.converse_json("m", "s", "u", client=client, validate=lambda o: None)
    assert call.obj is None and call.error and client.calls == 2


def test_converse_retries_on_validation_error_then_succeeds():
    client = FakeConverse(['{"better": "B"}', '{"better": "first"}'])
    call = judge.converse_json("m", "s", "u", client=client, validate=judge.parse_pairwise)
    assert call.obj == {"better": "first"} and call.error is None and client.calls == 2
    assert call.usage == {"inputTokens": 20, "outputTokens": 10}


def _gate_items():
    items = [PlantedSummary(f"orig-{i}", "s", FOUR, None, None, None) for i in range(4)]          # 깨끗한 문장 16개
    items += [PlantedSummary(f"lab-{i}", "s", ONE, "유보 삭제", 0, None) for i in range(4)]       # 라벨 결함 4개(깨끗한 문장 0)
    items += [PlantedSummary("omit-0", "s", FOUR, "뒤쪽 사실 삭제", None, "K9")]                  # 누락 결함 1개 + 깨끗한 문장 4개
    return items


def test_score_gate_units_and_adjudication():
    flags = {"lab-0": {0: ["부풀림-확신도"]}, "lab-1": {0: ["부풀림-확신도"]}, "lab-2": {0: ["귀속 누락"]}, "lab-3": {},
             "orig-0": {1: ["귀속 누락"]}, "orig-2": {3: ["부풀림-단계"]}, "orig-3": {1: ["인용 불일치"]}}
    uncovered = {"omit-0": {"K9"}}
    gate = judge.score_gate(flags, uncovered, _gate_items(), adjudicated_ok={("orig-3", 1)})
    assert gate.detection == pytest.approx(0.8)              # 결함 5개 중 4개 검출
    assert gate.false_flag_rate == pytest.approx(2 / 20)     # 깨끗한 문장 20개, 지적 3개 중 1개는 확인 결과 맞는 지적
    assert gate.passed


def test_select_judges_substitution():
    ok = {k: judge.JudgeGate(.9, .05, True) for k in ("astra", "sol61", "grok", "kimi")}
    assert judge.select_judges("gpt-6-sol", ok, ["grok", "kimi"]) == ("astra", "sol61", "grok")
    assert judge.select_judges("gpt-6-astra", ok, ["grok", "kimi"]) == ("sol61", "grok", "kimi")
    assert judge.select_judges("gpt-6.1-sol", ok, ["grok", "kimi"]) == ("astra", "grok", "kimi")
    bad = {**ok, "astra": judge.JudgeGate(.5, .3, False), "sol61": judge.JudgeGate(.5, .3, False)}
    with pytest.raises(judge.GateStop):
        judge.select_judges("gpt-6-sol", bad, ["grok", "kimi"])
    one_bad = {**ok, "astra": judge.JudgeGate(.5, .3, False)}
    assert judge.select_judges("gpt-6-sol", one_bad, ["grok", "kimi"]) == ("sol61", "grok", "kimi")


def test_fidelity_has_factual_error_label():
    """원문과 다른 사실(수치·주체 등)이나 원문에 없는 내용 — 라벨이 없으면 판정자가 표시할 수 없다(판정자 검증의 '숫자 변경')."""
    assert judge.parse_fidelity({"sentences": [{"idx": 0, "labels": ["사실 오류"], "evidence": "e"}]}, 2) == {0: ["사실 오류"]}
    assert "사실 오류" in judge.fidelity_messages("원문", ["요약 문장이다."])[0]
