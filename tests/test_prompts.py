"""prompts — 브레이스-안전 로더 + 캐싱-인지 조립."""
import re

from briefing.core.authoring.author import build_system_prompt, build_user_prompt
from briefing.core.prompts import apply_prompt_template, render
from briefing.core.stores.source_store import FrozenSource


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


# ── 해석층 프롬프트·파서 (card-layering §5) ─────────────────────────


def test_interp_system_prompt_static_and_forbids_new_facts():
    from briefing.core.authoring.author import build_interp_system_prompt

    s = build_interp_system_prompt(lens_guidance="엔지니어 관점 {x} $5")
    assert s == build_interp_system_prompt(lens_guidance="엔지니어 관점 {x} $5")  # 결정론(캐시 프리픽스)
    assert "새 사실" in s and "based_on" in s        # no-new-facts 계약 + 인용 계약
    assert "{x}" in s and "$5" in s                  # lens brace-safe(raw 연결)
    assert re.search(r"20\d\d-\d\d-\d\d", s) is None  # 날짜 없음(static)


def test_interp_user_prompt_has_date_claims_and_source():
    from briefing.core.authoring.author import Claim, build_interp_user_prompt

    src = FrozenSource("id", "u", "t", "원문 {코드} $5", "ts")
    claims = (Claim("C1", "직원이 100명이다.", "arithmetic", "core"),)
    u = build_interp_user_prompt(src, claims, today="2026-07-06")
    assert "2026-07-06" in u and "C1" in u and "100명" in u and "{코드}" in u


def test_parse_interp_from_noisy_output():
    from briefing.core.authoring.author import Interpretation, _parse_interp

    text = '설명 텍스트...\n{"why_it_matters": "이유.", "based_on": ["C1", "C2"]}'
    assert _parse_interp(text) == Interpretation("이유.", ("C1", "C2"))


def test_to_draft_card_unknown_claim_type_defaults_arithmetic():
    # 계약 "애매하면 arithmetic"(더 엄격)과 정렬 — 미상 라벨 폴백을 entailment→arithmetic 으로 교정
    from briefing.core.authoring.author import _to_draft_card

    card = _to_draft_card("s", {"headline": "h", "summary": "s", "why_it_matters": "w",
                                "claims": [{"id": "C1", "text": "t"}]})
    assert card.claims[0].claim_type == "arithmetic"
