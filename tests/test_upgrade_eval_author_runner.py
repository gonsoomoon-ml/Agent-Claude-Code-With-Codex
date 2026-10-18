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


# ── S2(2026-10-18): 초안 B(분자형 claims·한정어 보존) 한 가지만 다른 조건 — 대조군은 S1C 재사용 ──────────

def test_s2_arm_swaps_atomic_wording_for_draft_b():
    """S2B = S1C + 초안 B. '원자적으로 쪼갠다' 문구는 초안 B 와 입도가 충돌해(리서치 부록) 함께 바꾼다.
    바꾼 것은 정해진 치환뿐이어야 한다 — 되돌리면 운영 지시문과 글자까지 같다."""
    c, b = author_runner.ARMS["S1C"], author_runner.ARMS["S2B"]
    assert (b.model_id, b.cli_version, b.effort) == (c.model_id, c.cli_version, c.effort)
    assert b.rules_name == "s2_draft_b" and not b.rules_patch
    prod = author_runner.system_prompt_for(c, FACT_USER)
    s = author_runner.system_prompt_for(b, FACT_USER)
    assert "원자" in prod and "원자" not in s
    assert (s.index("요약에 담지 않은 사실은 claim 으로 만들지 않는다") < s.index("· claim 하나는 요약의 한 절")
            < s.index("각 claim 에 **`claim_type`** 부여"))                       # 초안 B 위치 = 요약 커버리지 규칙 바로 아래
    back = s
    for old, new in reversed(b.system_edits):
        back = back.replace(new, old, 1)
    assert back == prod


def test_s2_draft_prompt_edited_revise_prompt_untouched():
    """draft 의 user 지시('원자적 claims 를 추출하라')만 바꾸고, 다시 쓰기 지시는 운영 그대로 둔다(그 안엔 원자 문구가 없다)."""
    from briefing.core.authoring.author import _build_revise_prompt, build_user_prompt

    seen = []

    def fake(system_prompt, user_prompt, arm, timeout_s):
        seen.append((system_prompt, user_prompt))
        return AuthorRun("", CARD, 0.01, {}, "end_turn", 10, 0, None)

    arm = author_runner.ARMS["S2B"]
    draft, revise = author_runner.make_author_fns(arm, log=[], runner=fake)
    d = draft(SRC, FACT_USER, SETTINGS)
    revise(SRC, FACT_USER, SETTINGS, prior=d, failed_ids=("C1",))
    (s1, u1), (s2, u2) = seen
    today = author_runner.EVAL_TODAY
    assert "원자" not in u1 and u1 == author_runner.apply_edits(build_user_prompt(SRC, today=today), arm.user_edits)
    assert u1 != build_user_prompt(SRC, today=today)
    assert u2 == _build_revise_prompt(SRC, d, ("C1",), today=today)
    assert s1 == s2 == author_runner.system_prompt_for(arm, FACT_USER)


def test_control_prompts_untouched_by_edit_machinery():
    """대조군 S1C 의 draft user 지시는 운영 build_user_prompt 그대로 — 치환 장치가 대조군에 새지 않는다."""
    from briefing.core.authoring.author import build_user_prompt

    seen = []

    def fake(system_prompt, user_prompt, arm, timeout_s):
        seen.append(user_prompt)
        return AuthorRun("", CARD, 0.01, {}, "end_turn", 10, 0, None)

    draft, _ = author_runner.make_author_fns(author_runner.ARMS["S1C"], log=[], runner=fake)
    draft(SRC, FACT_USER, SETTINGS)
    assert seen == [build_user_prompt(SRC, today=author_runner.EVAL_TODAY)]


def test_apply_edits_requires_exactly_one_match():
    """바꿀 문구가 없거나 두 번 이상 있으면 실패한다 — 운영 지시문이 바뀌어 치환이 조용히 빠지면 실험이 무의미하다."""
    assert author_runner.apply_edits("abc", (("b", "B"),)) == "aBc"
    with pytest.raises(ValueError):
        author_runner.apply_edits("abc", (("x", "y"),))
    with pytest.raises(ValueError):
        author_runner.apply_edits("aba", (("a", "c"),))
