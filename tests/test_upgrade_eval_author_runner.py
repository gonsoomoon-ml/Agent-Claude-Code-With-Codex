"""업그레이드 비교 실험 — author 러너 테스트(허용 목록 env·DI 함수·오류 기록)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from upgrade_eval import author_runner  # noqa: E402
from upgrade_eval.author_runner import AuthorRun  # noqa: E402

from briefing.core.config import load_settings  # noqa: E402
from briefing.core.pipeline import _FACT_USER as FACT_USER  # noqa: E402
from briefing.core.stores.source_store import FrozenSource  # noqa: E402

CARD = '{"summary":"S","why_it_matters":"W","claims":[{"id":"C1","text":"t","claim_type":"entailment","importance":"core"}]}'
SRC = FrozenSource("sid0001", "https://www.aitimes.com/news/x", "원제목", "본문 원문입니다. " * 20, "2026-10-17T00:00:00Z")
SETTINGS = load_settings()


def test_env_is_allowlisted(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.setenv("CLAUDECODE", "1")
    env = author_runner.build_env(author_runner.ARMS["A3"], home_dir=tmp_path)
    assert env["HOME"] == str(tmp_path) and env["ANTHROPIC_MODEL"] == "global.anthropic.claude-sonnet-5-5"
    assert env["AWS_REGION"] == "us-east-1" and env["CLAUDE_CODE_USE_BEDROCK"] == "1"
    assert "ANTHROPIC_API_KEY" not in env and "CLAUDECODE" not in env
    if author_runner.EFFORT_VIA == "env":
        assert env["CLAUDE_CODE_EFFORT_LEVEL"] == "high"
    assert "CLAUDE_CODE_EFFORT_LEVEL" not in author_runner.build_env(author_runner.ARMS["A0"], home_dir=tmp_path)


def test_arms_pin_cli_versions_and_models():
    arms = author_runner.ARMS
    assert (arms["A0"].cli_version, arms["A1"].cli_version) == ("2.1.195", "2.1.301")
    assert arms["A0"].model_id == arms["A1"].model_id == "global.anthropic.claude-sonnet-5"
    assert (arms["A4"].model_id, arms["A5"].model_id) == ("global.anthropic.claude-opus-5-5", "global.anthropic.claude-haiku-5-5")


def test_draft_and_revise_fns_parse_and_log():
    fake = lambda s, u, arm, timeout_s: AuthorRun("", CARD, 0.01, {}, "end_turn", 10, 0, None)  # noqa: E731
    log = []
    draft, revise = author_runner.make_author_fns(author_runner.ARMS["A2"], log=log, runner=fake)
    d = draft(SRC, FACT_USER, SETTINGS)
    assert d.summary == "S" and d.headline == SRC.title
    revise(SRC, FACT_USER, SETTINGS, prior=d, failed_ids=("C1",))
    assert [r.kind for r in log] == ["draft", "revise"]


def test_runner_error_raises_after_logging():
    bad = lambda *a, **k: AuthorRun("", "", None, {}, None, 600000, None, "timeout")  # noqa: E731
    log = []
    draft, _ = author_runner.make_author_fns(author_runner.ARMS["A2"], log=log, runner=bad)
    with pytest.raises(RuntimeError):
        draft(SRC, FACT_USER, SETTINGS)
    assert log[0].error == "timeout"


def test_prompts_pin_today_across_runs():
    """요약 지시에 '오늘 날짜'가 들어간다 — 조건마다 실행일이 달라도 같은 날짜를 줘야 비교가 공정하다."""
    seen = []

    def fake(system_prompt, user_prompt, arm, timeout_s):
        seen.append(user_prompt)
        return AuthorRun("", CARD, 0.01, {}, "end_turn", 10, 0, None)

    draft, revise = author_runner.make_author_fns(author_runner.ARMS["A2"], log=[], runner=fake)
    d = draft(SRC, FACT_USER, SETTINGS)
    revise(SRC, FACT_USER, SETTINGS, prior=d, failed_ids=("C1",))
    assert author_runner.EVAL_TODAY == "2026-10-17"
    assert all(f"오늘 날짜: {author_runner.EVAL_TODAY}" in u for u in seen) and len(seen) == 2


# ── S1(2026-10-18): 초안 A('같은 확신도') 한 가지만 다른 두 조건 ─────────────────────────────

def test_s1_arms_differ_only_by_draft_a():
    """S1C(대조) = 운영 예정 구성(Sonnet 5.5·CLI 2.1.301·medium) + 현재 지시문, S1A = 그 위에 초안 A 만 더함."""
    from briefing.core.authoring.author import build_system_prompt
    from briefing.core.lenses import resolve_lens

    c, a = author_runner.ARMS["S1C"], author_runner.ARMS["S1A"]
    assert (c.model_id, c.cli_version, c.effort) == (a.model_id, a.cli_version, a.effort) == (
        "global.anthropic.claude-sonnet-5-5", "2.1.301", "medium")
    prod = build_system_prompt(lens_guidance=resolve_lens(FACT_USER.lens).guidance, skill_md=FACT_USER.skill_md)
    assert author_runner.system_prompt_for(c, FACT_USER) == prod                     # 대조군 = 운영 지시문 그대로
    s = author_runner.system_prompt_for(a, FACT_USER)
    assert s.index("## 논조·귀속 보존") < s.index("3-1. 확신도와 범위를") < s.index("## 요약 계약")
    block = a.rules_patch.rstrip("\n") + "\n\n"                                       # 넣은 것은 초안 A 블록 하나뿐
    assert s.replace(block, "", 1) == prod and len(s) == len(prod) + len(block)


def test_insert_rules_fails_loudly_without_anchor():
    """넣을 자리('## 논조·귀속 보존' 절)가 없으면 조용히 빠뜨리지 않고 실패한다 — 초안 없이 돈 실험은 무의미하다."""
    with pytest.raises(ValueError):
        author_runner.insert_rules("## 다른 절\n내용\n", "추가 규칙")
