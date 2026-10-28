"""relevance_bedrock — 라벨 호출 헬퍼(LABEL_MODEL_ID·모델별 Converse 파라미터)와 관련성 헬퍼의 불변(2026-10-24)."""
import dataclasses
import json

import pytest

from briefing.core.authoring.author import Claim, DraftCard
from briefing.core.config import load_settings
from briefing.core.gate import GatedCard
from briefing.core.retrieval import relevance_bedrock as rb
from briefing.core.top_picks import LabelIncomplete
from briefing.core.verification.certifier import CertVerdict


def _settings(**overrides):
    """test_runtime._settings 와 같은 모양 — load_settings() 기본값 위에 override."""
    return dataclasses.replace(load_settings(), region="us-east-1", **overrides)


def _g(sid):
    card = DraftCard(sid, f"제목-{sid}", f"요약-{sid}", "", (Claim("C1", "x", "entailment", "core"),))
    return GatedCard(card, (CertVerdict("C1", "VERIFIED", "ev"),), "PUBLISH", 1)


def test_label_request_fields_by_model():
    assert rb.label_request_fields("global.anthropic.claude-haiku-5-5") == {"thinking": {"type": "disabled"}}
    assert "disabled" not in json.dumps(rb.label_request_fields("global.anthropic.claude-sonnet-5-5"))   # Sonnet 5.5: disabled = 400
    assert "disabled" not in json.dumps(rb.label_request_fields("global.anthropic.claude-opus-5-5"))


def test_relevance_helper_still_sends_thinking_disabled():
    """관련성·선별·헤드라인 선별 경로(_converse_text)는 바이트 동일 — Haiku 5.5 함정(2026-10-17) 그대로 방어."""
    sent = {}

    class C:
        def converse(self, **kw):
            sent.update(kw)
            return {"output": {"message": {"content": [{"text": "YES"}]}}}

    assert rb._converse_text(C(), "m", "s", "u", 8) == "YES"
    assert sent["additionalModelRequestFields"] == {"thinking": {"type": "disabled"}}
    assert "temperature" not in sent["inferenceConfig"] and sent["inferenceConfig"]["maxTokens"] == 8


def test_make_bedrock_labels_uses_label_model_and_falls_back_to_relevance(monkeypatch, capsys):
    seen = []

    class C:
        def converse(self, **kw):
            seen.append(kw["modelId"])
            return {"output": {"message": {"content": [{"text": "[]"}]}}}

    monkeypatch.setattr(rb, "_client", lambda region: C())
    s = _settings(label_model_id="global.anthropic.claude-sonnet-5-5")
    with pytest.raises(LabelIncomplete):
        rb.make_bedrock_labels(s)([_g("s1")], [""])
    assert seen == ["global.anthropic.claude-sonnet-5-5"] * 2                      # 재시도 포함 2회, 모델 = LABEL
    assert "model=global.anthropic.claude-sonnet-5-5" in capsys.readouterr().err     # 첫 프로덕션 run 증명용 로그
    seen.clear()
    with pytest.raises(LabelIncomplete):
        rb.make_bedrock_labels(_settings(label_model_id=""))([_g("s1")], [""])
    assert seen[0] == _settings().relevance_model_id                              # 빈 값 = RELEVANCE 상속


def test_label_converse_reads_text_block_even_after_reasoning(monkeypatch):
    """thinking 이 켜진 모델은 reasoningContent 블록이 먼저 온다 — 첫 블록 고정 금지(2026-10-17 Haiku 함정과 동형)."""

    class C:
        def converse(self, **kw):
            assert kw["inferenceConfig"]["maxTokens"] == rb.LABEL_MAX_TOKENS
            return {"output": {"message": {"content": [{"reasoningContent": {"reasoningText": {"text": "..."}}},
                                                       {"text": "[{\"n\": 1}]"}]}}}

    assert rb._converse_label_text(C(), "global.anthropic.claude-sonnet-5-5", "s", "u") == '[{"n": 1}]'


def test_make_bedrock_rereport_uses_relevance_model_thinking_disabled(monkeypatch):
    """재보도 판정자(2026-10-28) — RELEVANCE_MODEL_ID(Haiku 5.5)·thinking disabled·temperature 없음."""
    from briefing.core.retrieval.rereport import RereportVerdict
    sent = {}

    class C:
        def converse(self, **kw):
            sent.update(kw)
            return {"output": {"message": {"content": [{"text": '{"same": true, "reason": "r"}'}]}}}

    monkeypatch.setattr(rb, "_client", lambda region: C())
    s = _settings()
    assert rb.make_bedrock_rereport(s)("A 본문", "B 본문") == RereportVerdict(True, "r")
    assert sent["modelId"] == s.relevance_model_id
    assert sent["additionalModelRequestFields"] == {"thinking": {"type": "disabled"}}
    assert "temperature" not in sent["inferenceConfig"]
