"""prompts — 브레이스-안전 로더 + 캐싱-인지 조립."""
import re

from briefing.shared.harness.author import build_system_prompt, build_user_prompt
from briefing.shared.prompts import apply_prompt_template, render
from briefing.shared.stores.source_store import FrozenSource


def test_render_brace_and_dollar_safe():
    out = render('리터럴 {x} {"k":1} $5 $bar 그리고 $known', known="OK")
    assert "{x}" in out and '{"k":1}' in out and "$5" in out and "$bar" in out
    assert "$known" not in out and "OK" in out  # 알려진 $var 만 치환


def test_system_prompt_static_and_brace_safe():
    s1 = build_system_prompt(lens_guidance="강조 {a} $5", skill_md="역할 {b} $z")
    s2 = build_system_prompt(lens_guidance="강조 {a} $5", skill_md="역할 {b} $z")
    assert s1 == s2  # 결정론 → 캐시 프리픽스 안정
    assert "CURRENT_DATE" not in s1
    assert re.search(r"20\d\d-\d\d-\d\d", s1) is None  # 날짜 값 없음(static)
    assert "{a}" in s1 and "$5" in s1  # lens/skill brace-safe


def test_user_prompt_has_date_and_source_brace_safe():
    src = FrozenSource("id", "u", "t", "원문 {코드} $5", "ts")
    u = build_user_prompt(src, today="2026-06-26")
    assert "2026-06-26" in u and "{코드}" in u and "$5" in u


def test_apply_prompt_template_loads_base():
    assert "claim_type" in apply_prompt_template("author_system")  # base 계약 로드
