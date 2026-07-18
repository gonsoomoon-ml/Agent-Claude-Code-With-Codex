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


# ── v3 요약 계약 (represent-v3) — 실측이 근거인 조항들. 지워지면 lead bias 가 돌아온다 ──
#
# 근거(2026-07-17 프로덕션 감사, 원문 1500자+ 카드 101장): 요약이 도달한 최심 위치 median 0.614 vs
# **같은 카드·같은 호출의 claims 0.905**. 요약이 claims 보다 앞쪽 편중 77%, 원문 중간 미도달 39%.
# author 는 기사를 다 읽었는데(claims 가 끝까지 도달) summary 에서만 버렸다 = **사양 부재**였다.


def _fact_layer_prompt() -> str:
    """프로덕션 사실층과 **동일한 조립** — lens 는 general 하나뿐이고 skill 은 안 붙는다.

    pipeline._FACT_USER(lens=DEFAULT_LENS, skill_md="") 가 그렇게 고정한다. base 만 검사하면
    lens 문구가 base 와 충돌하는 회귀(예: general 의 옛 '왜 중요한가를 간결히')를 못 잡는다.
    """
    from briefing.core.lenses import resolve_lens
    from briefing.core.pipeline import _FACT_USER

    return build_system_prompt(
        lens_guidance=resolve_lens(_FACT_USER.lens).guidance, skill_md=_FACT_USER.skill_md
    )


def test_author_system_pins_summary_selection_rule():
    """요약의 선택 기준 = '위치가 아니라 무게'. v3 의 심장이며 lead bias 의 유일한 방어선이다.

    (certifier 는 envelope 4필드만 봐서 '빠진 게 있나'를 원리적으로 못 본다 → 생성 계약이 전부다.)
    """
    s = _fact_layer_prompt()
    assert "위치가 아니라 사실의 무게" in s
    assert "도입부만 옮긴 요약은 원문을 대표하지 않는다" in s


def test_author_system_pins_stance_preservation():
    """논조·귀속 보존 — 사실이 다 맞아도 여기서 무너진다.

    실측: 헤지 보유 claims 59장 중 32장(54%)의 요약에 유보가 전무 → 비판 기사가 홍보 요약이 됐다.
    """
    s = _fact_layer_prompt()
    assert "귀속" in s and "유보" in s
    assert "동사의 세기를 바꾸지 마라" in s


def test_author_system_budget_forces_selection():
    """분량 = **예산**이며 선택 규칙에 묶여 있다. 지워지면 요약이 기사 축약본이 된다.

    A/B 실측(2026-07-17, lead bias 최악 4건): 예산 없는 v3 는 앵커 최심을 0.162→0.888 로 고쳤지만
    요약이 317→**1,149자**(10문장)로 폭증하고 author 가 2배 느려져 4건 중 1건이 240s 타임아웃 =
    프로덕션이면 카드 유실. **예산이 없으면 "무엇을 버릴지 고르는 일"이라는 규칙이 공허해진다.**
    (문헌: 문장 수 지시 준수율 84~99% vs 문자 수 7% → 단위는 문장.)
    """
    s = _fact_layer_prompt()
    assert "3~5문장" in s
    assert "예산" in s and "무게로 골라 버려라" in s        # 예산 ↔ 선택 규칙 결합
    assert "짧은 요약이 부풀린 요약보다 낫다" in s          # 분량 채우기 금지(예산은 목표가 아니다)


def test_author_system_length_rules_do_not_contradict():
    """예산(문장 수)과 형식(문장 길이)이 서로 싸우면 안 된다.

    v3.1 초안이 실제로 그랬다: 형식은 '150자 넘으면 두 문장으로 나눈다', 예산은 '쪼개지 말고
    사실을 버려라' — 같은 프롬프트 안의 모순. 문장을 쪼개면 예산을 먹으므로 둘은 실제로 충돌한다.
    """
    s = _fact_layer_prompt()
    assert "문장을 쪼개지 말고" not in s                    # 형식의 분할 규칙과 충돌하던 문구
    assert "사실을 하나 더 버려라" in s                     # 해소된 형태: 분할이 아니라 폐기


def test_fact_layer_prompt_has_no_qualitative_length_word():
    """'간결' 류 정성 수식어 금지 — base·lens 어디에도.

    문헌(Retkowski 2025): short/concise/brief 는 통계적으로 무구별이고 무지시 대비 17.8%만 줄인다.
    lens 의 옛 문구('핵심 사실과 "왜 중요한가"를 간결히')는 v3 의 '요약에 의의를 쓰지 마라'와
    **정면 충돌**했다 — base 만 보면 안 보이는 회귀라 프로덕션 조립으로 검사한다.
    """
    s = _fact_layer_prompt()
    assert "간결" not in s


def test_author_system_pins_claims_summary_coverage():
    """claims 스코프 = 요약 커버리지(원문 전체 아님). v3.3 — 근본은 타임아웃/비용, 불변식은 안전망.

    근거(2026-07-18 순차 실측): v3 의 "claims 원문 전체 빠짐없이"가 밀집 기사에서 35~39 claims 를 뽑아
    author 지연 240s+ → 카드 유실. claims 는 발행물(요약)의 검증 안전망이지 기사 색인이 아니다.
    ★ 안전망 불변식(비협상): 요약이 진술한 사실은 여전히 전부 claim — claim 없는 사실은 검증을 우회한다.
    """
    s = _fact_layer_prompt()
    # 안전망: 요약 사실은 빠짐없이 claim
    assert "요약의 어떤 사실도 claim 없이 남기지 마라" in s
    assert "검증을 우회" in s
    # 좁힘: 요약 밖 사실은 제외
    assert "요약에 담지 않은 사실은 claim 으로 만들지 않는다" in s
    assert "기사 전체의 색인이 아니다" in s
    # 옛 '원문 전체 빠짐없이' 언어는 사라졌는지(회귀 방지)
    assert "claims 는 원문 전체를 덮는다" not in s


def test_author_system_has_no_headline_contradiction():
    """base 가 headline 을 요구하고 출력 계약이 금지하던 실재 모순(v2)이 사라졌는지.

    _to_draft_card 는 이미 data 의 headline 을 버리고 source.title 을 쓴다 — md 만 stale 이었다.
    """
    s = _fact_layer_prompt()
    assert '"headline"' not in s and "{headline" not in s
    assert "제목은 만들지 않는다" in s


def test_user_prompt_flags_truncated_source():
    """원문 28.6%가 8,000자에서 잘린다 — '본문 전체를 근거로'가 없는 뒷부분 추측 압력이 되면 안 된다."""
    from briefing.core.retrieval.sources import MAX_SOURCE_CHARS

    full = FrozenSource("id", "u", "t", "가" * MAX_SOURCE_CHARS, "ts")
    short = FrozenSource("id", "u", "t", "가" * 500, "ts")
    assert "절단" in build_user_prompt(full, today="2026-07-17")
    assert "절단" not in build_user_prompt(short, today="2026-07-17")


def test_prompt_version_matches_contract():
    """PROMPT_VERSION 은 fact_card_key 성분 — 계약을 바꾸고 안 올리면 구 카드가 새 것인 척 서빙된다."""
    from briefing.core.authoring.author import PROMPT_VERSION

    assert PROMPT_VERSION == "represent-v3.3"


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

    card = _to_draft_card("s", "제목", {"summary": "s", "why_it_matters": "w",
                                       "claims": [{"id": "C1", "text": "t"}]})
    assert card.claims[0].claim_type == "arithmetic"
    assert card.headline == "제목"   # headline = title 인자(기사 원제목), data 의 headline 무시
