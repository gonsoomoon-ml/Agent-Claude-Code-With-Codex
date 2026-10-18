"""요약 AI·해석층의 모델·effort 배선(F3·F7) — `claude -p` 에 실제로 넘어가는 argv·env 를 본다.

0단계 약속: effort 를 설정하지 않으면 배선 전과 *같은 명령*이 나간다(`--effort` 없음, 모델 = AUTHOR_MODEL_ID).
해석층은 INTERP_* 가 비면 요약 AI 값을 따르고, 'default' 는 플래그를 빼서 CLI 기본값을 강제한다.
"""
from __future__ import annotations

import dataclasses
import json

import pytest

from briefing.core.authoring import author
from briefing.core.authoring.author import Claim
from briefing.core.config import UserConfig, load_settings
from briefing.core.stores.source_store import FrozenSource

_CARD = json.dumps({"summary": "요약.", "why_it_matters": "왜.",
                    "claims": [{"id": "C1", "text": "주장.", "claim_type": "entailment"}]}, ensure_ascii=False)
_INTERP = json.dumps({"why_it_matters": "해석.", "based_on": ["C1"]}, ensure_ascii=False)
_SRC = FrozenSource("sid", "https://example.com/a", "제목", "원문 본문.", "2026-10-18")
_USER = UserConfig(id="u", recipient="u@example.com", type="ai-news", sources=(), depth="summary",
                   lens="general", send_hour=5, timezone="Asia/Seoul", skill_md="")


def _settings(**kw):
    base = dict(author_model_id="M-author", author_effort="", interp_model_id="", interp_effort="")
    return dataclasses.replace(load_settings(), **(base | kw))


class _Calls(list):
    """가로챈 호출 기록(argv·env) + 다음 호출들이 돌려줄 출력(`outputs`, 비면 카드 JSON)."""
    outputs: list[str]


@pytest.fixture
def calls(monkeypatch):
    """subprocess.run 을 가로채 argv·env 를 모은다(실제 claude 호출 0)."""
    seen = _Calls()
    seen.outputs = []

    def fake_run(argv, **kw):
        seen.append({"argv": argv, "env": kw["env"]})

        class _Proc:
            returncode = 0
            stderr = ""
            stdout = json.dumps({"result": seen.outputs.pop(0) if seen.outputs else _CARD, "total_cost_usd": 0.0})
        return _Proc()

    monkeypatch.setattr(author.subprocess, "run", fake_run)
    return seen


def test_unset_effort_sends_the_same_command_as_before(calls):
    """0단계 = 동작 불변: effort 미설정이면 `--effort` 가 없고 argv 모양이 배선 전과 같다."""
    author._run_author("SYS", "USR", _settings())
    argv = calls[0]["argv"]
    assert argv == ["claude", "-p", "--system-prompt", "SYS", "--output-format", "json", "USR"]
    assert calls[0]["env"]["ANTHROPIC_MODEL"] == "M-author"


def test_author_effort_adds_flag_before_user_prompt(calls):
    author._run_author("SYS", "USR", _settings(author_effort="medium"))
    argv = calls[0]["argv"]
    assert argv[-3:] == ["--effort", "medium", "USR"]   # 사용자 프롬프트는 마지막 위치 인자 그대로


def test_default_effort_omits_flag(calls):
    author._run_author("SYS", "USR", _settings(author_effort="default"))
    assert "--effort" not in calls[0]["argv"]


def test_fact_layer_uses_author_values_even_when_interp_is_set(calls):
    s = _settings(author_effort="medium", interp_model_id="M-interp", interp_effort="high")
    author.draft_card(_SRC, _USER, s)
    assert calls[0]["env"]["ANTHROPIC_MODEL"] == "M-author"
    assert calls[0]["argv"][-3:-1] == ["--effort", "medium"]


def test_interpretation_uses_interp_model_and_default_effort(calls):
    """U8② 의 .env(요약 Sonnet 5.5·medium, 해석층 Sonnet 5·default) — 해석층은 지금 명령 그대로."""
    calls.outputs.append(_INTERP)
    s = _settings(author_effort="medium", interp_model_id="M-interp", interp_effort="default")
    author.draft_interpretation(_SRC, (Claim("C1", "주장.", "entailment"),), _USER, s, "요약.")
    assert calls[0]["env"]["ANTHROPIC_MODEL"] == "M-interp"
    assert "--effort" not in calls[0]["argv"]


def test_interpretation_inherits_author_values_when_interp_unset(calls):
    calls.outputs.append(_INTERP)
    s = _settings(author_effort="medium")
    author.draft_interpretation(_SRC, (Claim("C1", "주장.", "entailment"),), _USER, s, "요약.")
    assert calls[0]["env"]["ANTHROPIC_MODEL"] == "M-author"
    assert calls[0]["argv"][-3:-1] == ["--effort", "medium"]
