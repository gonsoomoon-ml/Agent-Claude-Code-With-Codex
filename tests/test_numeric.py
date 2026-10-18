"""numeric — 교차언어 수치 정규화의 불변식 고정.

여기 케이스 대부분은 **프로덕션 재생(replay)에서 실제로 터진 것**이다(2026-07-17, 원장 223카드·
결정론 판정 1,326건). `tests/eval_set/cases.jsonl`(위양성/catch 지표)이 못 덮는 *파서 내부* 함정을 덮는다.

★ 이 파일이 지키는 것: 동치를 넓히되 **거짓 VERIFIED 를 만들지 않는다**.
"""
from __future__ import annotations

import pytest

from briefing.core.verification import numeric
from briefing.core.verification.certifier import Envelope, _certify_arithmetic


def _v(text: str) -> set[float]:
    return numeric.scan(text).values


# ── 교차언어 동치: 이게 되라고 만든 모듈 ─────────────────────────────────────────

@pytest.mark.parametrize(("ko", "en"), [
    ("8개월도 채 안 되어", "after just eight months"),          # 기수 단어
    ("4조 달러를 초과", "could top four trillion dollars"),      # 스케일 + 기수
    ("약 3천만 명", "about 30 million"),                        # 만/억 (10^4) ↔ million (10^3)
    ("100만 토큰", "one million tokens"),
    ("70억 달러", "$7 billion"),
    ("316억 개의 파라미터", "31.6 billion parameters"),
    ("4억 6,600만 줄", "466 million lines"),                    # 만/억 체이닝
    ("16만 5천 줄", "165,000 lines"),                           # 만 + 천 꼬리
    ("1조 개의 매개변수", 'an agent with "a trillion parameters"'),  # 관사 a = 1
    ("2주 이내에 100만 줄", "A million lines in less than 2 weeks"),
    ("내부 사용량이 3배로 늘었다", "internal usage tripled"),      # 배수 동사
    ("3분의 2를 차지", "accounted for nearly two-thirds"),        # 분수(분모 먼저)
    ("4개 중 1개가 AI", "One in four posts is AI-generated"),
    ("3분의 1 이상", "more than a third of"),                    # 관사 분수
    ("0.8B 및 4B 파라미터", "trained at 0.8 and 4 billion parameters"),  # 등위 생략
])
def test_cross_lingual_equivalence(ko: str, en: str) -> None:
    """한국어 claim 의 값이 영어 원문의 값 집합에 존재해야 한다(= 위양성 0)."""
    ko_vals, en_vals = _v(ko), _v(en)
    for val in ko_vals:
        assert numeric.contains(val, en_vals), f"{val} ∉ {sorted(en_vals)} — '{ko}' vs '{en}'"


def test_month_and_ordinal_cross_lingual() -> None:
    assert numeric.scan("2025년 10월에 출시").months == numeric.scan("launched last October 2025").months
    assert numeric.scan("제3자 사이트").ordinals == numeric.scan("redistributed third-party material").ordinals


# ── 네임스페이스 분리: 동치를 넓히면서도 거짓 VERIFIED 를 막는 장치 ───────────────

def test_month_does_not_leak_into_quantities() -> None:
    """'July 27' 은 월 7 을 주지만 **수량 7 은 주지 않는다** — 근거 없는 '7종' claim 방어(eval SY04)."""
    src = numeric.scan("Full weights ship by July 27.")
    assert 7 in src.months
    assert not numeric.contains(7.0, src.values)


def test_ordinal_does_not_leak_into_quantities() -> None:
    """'third-party' 는 서수 3 을 주지만 수량 3 은 주지 않는다 — 작은 정수 오염 차단."""
    src = numeric.scan("redistributed third-party material")
    assert 3 in src.ordinals
    assert not numeric.contains(3.0, src.values)


def test_small_ordinal_not_justified_by_quantity() -> None:
    """적대 검증에서 실증: 원문 수량 3('three co-chairs')이 없는 서수 3('제3자 감사')을 인증했다.

    서수↔수량 완화는 법조문('제109조' ↔ 'Article 109')용이므로 큰 수로만 제한한다.
    """
    v = _certify_arithmetic("C1", Envelope(
        "Andreessen is one of three co-chairs of a working group.", "제3자 감사가 수행됐다.",
        "arithmetic", "{}"))
    assert v.verdict == "BLOCKED"


@pytest.mark.parametrize(("claim", "source"), [
    ("국가미디어협약 제109조를 위반했다고 인정했다.", "The rulings found violations of Article 109 of the treaty."),
    ("여러 제3자 사이트의 자료를 결합했다.", "combined from third-party sites rather than redistributed material."),
])
def test_ordinal_equivalence_still_holds(claim: str, source: str) -> None:
    """구멍을 막으면서 원래 살리려던 동치(법조문·서수↔서수)까지 죽이면 안 된다."""
    assert _certify_arithmetic("C1", Envelope(source, claim, "arithmetic", "{}")).verdict == "VERIFIED"


def test_scale_phrase_is_consumed_whole() -> None:
    """'one million' = 1e6 하나. {1, 100, ...} 로 흩어지면 '100개' 날조가 통과한다(eval SY02)."""
    vals = _v("896 experts and one million tokens")
    assert vals == {896.0, 1_000_000.0}


# ── 자릿수(magnitude) 보존: 이 모듈의 존재 이유 ────────────────────────────────

@pytest.mark.parametrize(("claim", "source"), [
    ("약 3억 명", "about 30 million"),              # 10배 오류
    ("500만 토큰", "one million tokens"),           # 5배 오류
    ("3160억 개", "31.6 billion parameters"),       # 10배 오류
    ("총 25명", "The team of 15"),
])
def test_magnitude_errors_are_caught(claim: str, source: str) -> None:
    """배수 오류는 반드시 잡힌다 — 반올림 관용을 넣으면 여기가 무너진다."""
    v = _certify_arithmetic("C1", Envelope(source, claim, "arithmetic", "{}"))
    assert v.verdict == "BLOCKED", f"'{claim}' vs '{source}' → {v.verdict} ({v.evidence})"


def test_third_party_injection_cannot_justify_myriad() -> None:
    """실증된 함정: 순진한 정규화기는 'third'→3 을 원문에 주입해 '3억'(3e8)을 통과시켰다.

    값 비교는 이 함정이 원리적으로 무해하다 — 3e8 ≠ 3.
    """
    v = _certify_arithmetic("C1", Envelope("about 30 million third-party users", "약 3억 명", "arithmetic", "{}"))
    assert v.verdict == "BLOCKED"


def test_fraction_order_inversion_is_caught() -> None:
    """한국어 'N분의 M' = M/N. 순서를 안 지키면 '2분의 3'(=1.5)이 two-thirds 로 통과한다(eval SY07)."""
    assert _v("2분의 3") == {1.5}
    assert _v("3분의 2") == {2 / 3}


# ── 한국어 형태소 함정: 만/억/조는 다른 단어의 일부이기도 하다(프로덕션 회귀) ──────

def test_myriad_chars_inside_other_words_are_not_quantities() -> None:
    """'조차'(even)의 조, 'Fable 5만 K3'(만=only)의 만을 단위로 읽으면 유령 BLOCK 이 된다."""
    assert _v("Veo 3.1조차 어려움을 겪는다") == {3.1}                       # 3.1e12 아님
    assert _v("Claude Fable 5만 K3보다 높은 점수") == {5.0, 3.0}            # 50000 아님


def test_myriad_still_parsed_with_normal_boundaries() -> None:
    """경계 가드가 정상 표기까지 죽이면 안 된다(위 테스트의 대조군)."""
    assert _v("4조 달러") == {4e12}
    assert _v("270억) 파라미터") == {2.7e10}
    assert _v("3천만 명") == {3e7}


def test_month_pattern_ignores_duration() -> None:
    """'8개월'(기간)은 월(月)이 아니다."""
    n = numeric.scan("출시한 지 8개월도 채 안 되어")
    assert n.months == set()
    assert numeric.contains(8.0, n.values)


def test_may_lowercase_is_not_month() -> None:
    """'may'(조동사)를 월 5 로 읽으면 '5월' 날조가 통과한다 — 월 이름은 대소문자 구분."""
    assert numeric.scan("this may be a problem").months == set()
    assert numeric.scan("in May, the team shipped").months == {5}


def test_lexical_digits_are_not_quantities() -> None:
    """'1인당'(per capita)의 1 은 수량 주장이 아니다 — 원문엔 대응 수사가 없다."""
    assert _v("캐나다인의 1인당 사용률은 4배 이상") == {4.0}


# ── 값 대조가 잡아내는 진짜 환각 (2026-07-17 프로덕션 재생에서 발견) ──────────────
#
# 정규화 도입 *덕분에* 드러난 것이다: 그 전엔 BLOCKED 243건이 전부 표기 잡음이라
# 진짜 오류가 그 안에 묻혀 구분되지 않았다. 이제 BLOCK 은 신호다.

def test_catches_real_hallucination_miscounted_list() -> None:
    """실제 프로덕션 claim: 원문이 'five reasoning levels' 라 명시하는데 author 가 '7가지'라고 셌다.

    (원문은 Light·Low·Medium·High·xhigh 다섯을 레벨로 들고, Max·Ultra 는 "work differently" 라며
    별개 축으로 설명한다 — author 가 일곱을 다 레벨로 합쳐 셌다.)
    """
    src = ("OpenAI employee Vaibhav Srivastav explains when each of GPT-5.6 Sol's five "
           'reasoning levels fits. "Light" and "Low" are for quick, clear-cut tasks. "Medium" '
           'works for planning. "High" and "xhigh" handle complex work. "Max" and "Ultra" work '
           'differently: "Max" lets a model spend more time on a single problem.')
    claim = "기사 본문은 GPT-5.6 Sol의 추론 레벨로 Light, Low, Medium, High, xhigh, Max, Ultra 총 7가지를 명시한다."
    assert _certify_arithmetic("C1", Envelope(src, claim, "arithmetic", "{}")).verdict == "BLOCKED"


def test_known_false_positive_composite_time_unit() -> None:
    """'2시간 30분'(2h30m) ↔ 'two and a half hours'(2.5h) — **의미는 같은데 값이 다르다.**

    claim 은 {2, 30}, 원문은 {2.5} 라 값 대조로는 영영 안 맞는다. 맞추려면 시간 단위 산술
    (2 + 30/60 = 2.5)이 필요한데, 그건 '단위를 알아야' 가능하고 그 문을 열면 규칙이 값을
    합성하기 시작한다 — 오늘 거짓 VERIFIED 3종이 정확히 그렇게 생겼다. **의도적 BLOCK 유지.**

    ★ 이 케이스는 내가 처음에 'author 의 환각'으로 오판했던 것이다(원문의 다른 문단에 있던
    'four hours' 만 보고 단정). 원문은 실제로 "after roughly two and a half hours had a working
    environment that was about 90%" 라고 쓰여 있고 **claim 이 정확하다**. 위양성이다.
    """
    src = ("When a product manager wanted to bring native mobile app building inside Base44, he "
           "pointed Claude Fable 5 at the job and after roughly two and a half hours had a working "
           "environment that was about 90% of what the team needed to move to production.")
    claim = "프로덕트 매니저가 Claude Fable 5를 투입한 지 약 2시간 30분 후, 필요로 하는 것의 약 90%가 만들어졌다."
    assert _certify_arithmetic("C1", Envelope(src, claim, "arithmetic", "{}")).verdict == "BLOCKED"


# ── 적대적 검증에서 발견된 거짓 VERIFIED (2026-07-17 — 실제로 뚫렸던 것들) ───────
#
# 아래 셋은 *내가 그날 추가한 규칙*(관사 a=1 · 배수 동사)이 만든 구멍이다. 공격 에이전트가 찾았고
# 실행으로 재현됐다. 교훈: **동치를 넓히는 규칙은 값을 창조할 수 있다** — 이게 이 모듈에서 가장
# 위험한 실패 방식이다(위양성은 아플 뿐이지만 거짓 VERIFIED 는 신뢰를 깬다).

@pytest.mark.parametrize(("claim", "source", "why"), [
    ("스타트업은 100만 달러를 유치했다", "The startup raised half a million dollars.",
     "half a million = 5e5. 'half'를 분수로 먹고 'a million'을 통짜 1e6 으로 먹으면 원문에 없는 1e6 창조"),
    ("약 100만 명이 가입했다", "About a quarter of a million users signed up.",
     "a quarter of a million = 2.5e5 — 같은 창조 경로"),
    ("이 회사는 2배 성장했다", "The company saw double-digit growth this quarter.",
     "double-digit = 두 자릿수이지 2배가 아니다 — 배수 어휘가 관용구에서 값 2 를 창조"),
    ("오픈AI는 전략을 2배로 늘렸다", "OpenAI doubled down on its enterprise strategy.",
     "doubled down = 강화했다 — 배수 아님"),
])
def test_scale_composition_does_not_invent_values(claim: str, source: str, why: str) -> None:
    v = _certify_arithmetic("C1", Envelope(source, claim, "arithmetic", "{}"))
    assert v.verdict == "BLOCKED", f"거짓 VERIFIED: {why}"


@pytest.mark.parametrize(("claim", "source"), [
    ("스타트업은 50만 달러를 유치했다", "The startup raised half a million dollars."),
    ("약 25만 명이 가입했다", "About a quarter of a million users signed up."),
    ("내부 사용량이 3배로 늘었다", "When the team plugged it into Devin, internal usage tripled."),
])
def test_scale_composition_still_verifies_true_claims(claim: str, source: str) -> None:
    """구멍을 막으면서 정상 동치까지 죽이면 안 된다(위 테스트의 대조군)."""
    v = _certify_arithmetic("C1", Envelope(source, claim, "arithmetic", "{}"))
    assert v.verdict == "VERIFIED", v.evidence


@pytest.mark.parametrize("text", ["0분의 5 확률", "0개 중 3개", "one in 0 cases", "0분의 0"])
def test_zero_denominator_does_not_raise(text: str) -> None:
    """★ scan() 은 certifier 안에서 돈다 — 여기서 예외가 나면 그 카드를 통째로 잃는다.

    2026-07-02 인시던트(한 카드의 예외가 브리핑 전체를 붕괴)와 같은 계열. author 오타 하나면 충분하다.
    """
    numeric.scan(text)  # 예외 없이 끝나면 통과(분모 0 은 값을 만들지 않는다)


def test_idiomatic_one_is_not_a_quantity() -> None:
    """'one of the co-chairs'(여럿 중 하나)의 one 은 수량 주장이 아니다.

    값 1 로 수확하면 기사에 널린 관용구가 claim 의 '1명'·'1개'를 무상으로 인증한다.
    """
    assert not numeric.contains(1.0, numeric.scan("Andreessen is one of the co-chairs.").values)
    v = _certify_arithmetic("C1", Envelope(
        "Andreessen is one of the co-chairs.", "안드레센은 1명의 공동의장이다", "arithmetic", "{}"))
    assert v.verdict == "BLOCKED"


def test_idiomatic_one_does_not_break_counted_phrase() -> None:
    """'one of three co-chairs' 의 3 은 그대로 잡혀야 한다(위 규칙의 대조군)."""
    v = _certify_arithmetic("C1", Envelope(
        "Andreessen is one of three co-chairs.", "안드레센은 3인의 공동의장 중 한 명이다", "arithmetic", "{}"))
    assert v.verdict == "VERIFIED"


# ── 문맥 칸(F2, 2026-10-18): '~당·~배·~위·~분기' 숫자만 원문의 같은 문맥 표현으로 확인 ──────
#
# 30일 운영 재생에서 BLOCKED 64건 중 다수가 이 표기였다: 'per million'↔'100만 개당',
# 'triple'↔'3배', 'ranks second'↔'2위', 'the second quarter'↔'2분기'. 원문 쪽 표현은 *수량이 아니므로*
# values 에 넣지 않고 문맥 칸(ctx)에만 담는다 — 넣으면 'per million' 이 '100만 달러' 날조를 인증한다.

def test_bare_per_scale_goes_to_context_not_values() -> None:
    n = numeric.scan("Pricing sits at $2 per million input tokens and $6 per million output tokens.")
    assert n.ctx["per"] == {1e6}
    assert n.values == {2, 6}          # 1e6 은 수량이 아니다


def test_korean_context_markers_split_claim_values() -> None:
    """claim 쪽: 문맥 표지 앞 숫자는 문맥 칸으로, 나머지는 plain 으로. values 의미는 그대로(기존 소비자 보호)."""
    n = numeric.scan("입력 100만 개당 2달러, 121개국 중 2위, 기부액의 3배, 2분기부터")
    assert n.values == {1e6, 2, 121, 3}
    assert n.plain == {2, 121}         # '2달러'·'121개국'
    assert n.ctx["per"] == {1e6}
    assert n.ctx["rank"] == {2}
    assert n.ctx["mult"] == {3}
    assert n.ctx["quarter"] == {2}


@pytest.mark.parametrize(("text", "kind", "val"), [
    ("with early employees receiving triple their donation's value", "mult", 3),
    ("to improve accuracy more than fivefold", "mult", 5),
    ("Singapore ranks second of 121 countries", "rank", 2),
    ("the model currently sits in first place", "rank", 1),
    ("early estimates put it in eighth on the Math ECI", "rank", 8),
    ("working alongside 3,000 internal employees since the second quarter", "quarter", 2),
    ("revenue grew in Q3 2026", "quarter", 3),
])
def test_english_context_phrases(text: str, kind: str, val: int) -> None:
    assert val in numeric.scan(text).ctx.get(kind, set())


@pytest.mark.parametrize(("text", "kind"), [
    ("As Western mathematicians push back against AI, China is doubling down.", "mult"),
    ("double-digit growth", "mult"),
    ("a double-blind trial", "mult"),
    ("checking how well third-party models could browse the web", "rank"),
    ("for the first time in over a year", "rank"),
])
def test_idioms_do_not_enter_context(text: str, kind: str) -> None:
    """관용구의 double·first·third 는 배수·순위가 아니다 — 문맥 칸이 비어야 한다."""
    assert not numeric.scan(text).ctx.get(kind)


@pytest.mark.parametrize(("text", "inverted"), [
    ("거의 2분의 3을 차지했다", True),       # = 1.5 — '3분의 2'를 뒤집어 쓴 꼴
    ("거의 3분의 4 수준으로", True),
    ("전체의 3분의 2를", False),
    ("입력 가격의 10분의 1", False),
    ("분수 없음 2.5배", False),
])
def test_inverted_ko_fraction(text: str, inverted: bool) -> None:
    assert numeric.inverted_ko_fraction(text) is inverted


@pytest.mark.parametrize("claim", ["학습은 3배치로 나눠 진행했다.", "이 기능은 3배포 채널로 나갔다."])
def test_bae_inside_other_words_is_not_multiplier(claim: str) -> None:
    """'배치'(batch)·'배포'의 '배'는 배수가 아니다 — 원문 'triple' 이 '3배치'를 인증하면 안 된다."""
    src = "with early employees receiving triple their donation's value."
    assert _certify_arithmetic("C1", Envelope(src, claim, "arithmetic", "{}")).verdict == "BLOCKED"


def test_context_phrases_never_become_quantities() -> None:
    """문맥 표현은 values 에 아무것도 넣지 않는다 — 'triple' 이 수량 3 을 인증하면 안 된다(SY11)."""
    assert numeric.scan("triple their value, ranks second, since the second quarter, per million tokens").values == set()


# ── 만 + 맨숫자 꼬리(F2): '1만2000'·'1만 9,500' = 한 값 ─────────────────────────────

@pytest.mark.parametrize(("text", "val"), [
    ("건당 평균 약 1만2000달러", 12000),
    ("약 1만 9,500건", 19500),
    ("매달 72만5,000건 이상", 725000),
    ("총 14만1006건의 테스트 세션", 141006),
])
def test_myriad_with_plain_digit_tail(text: str, val: int) -> None:
    assert numeric.scan(text).values == {val}


def test_myriad_tail_does_not_chain_lists_or_next_group() -> None:
    assert numeric.scan("1만, 2000원").values == {10000, 2000}       # 쉼표 = 목록
    assert numeric.scan("1만 2000만 원").values == {10000, 2e7}      # 꼬리가 아니라 다음 그룹


# ── decades·centuries(F2): 환산값 ──────────────────────────────────────────────────

@pytest.mark.parametrize(("text", "val"), [
    ("started nearly four decades of research", 40),
    ("practiced for two decades", 20),
    ("for more than a decade", 10),
    ("over 3 decades", 30),
    ("two centuries ago", 200),
])
def test_decades_convert_to_years(text: str, val: int) -> None:
    assert numeric.scan(text).values == {val}    # 기수(4·2)는 따로 새지 않는다(SY15)


# ── F2 2차: 운영 재생에서 나온 파서 버그 8종 ────────────────────────────────────────

def test_year_is_not_a_fraction_denominator() -> None:
    """'45,000 in 2025' 는 'one in four' 같은 분수가 아니다 — 두 값이 그대로 남아야 한다."""
    assert numeric.scan("approximately 45,000 in 2025, 32,000 in 2024").values == {45000, 2025, 32000, 2024}
    assert numeric.scan("One in four posts is AI-generated").values == {0.25}     # 진짜 분수는 그대로


@pytest.mark.parametrize(("text", "vals"), [
    ("binned to 2k-step means", {2000}),
    ("Through ~800k steps", {800000}),
    ("over the full ~5.93T-token / 1.41M-step budget", {5.93e12, 1.41e6}),
    ("a 128k context window", {128000}),
])
def test_lowercase_k_and_T_suffix(text: str, vals: set[float]) -> None:
    assert numeric.scan(text).values == vals


@pytest.mark.parametrize(("text", "val"), [
    ("while using about an eighth of the output tokens", 0.125),
    ("about a tenth of traditional production costs", 0.1),
    ("at one-tenth of the cost", 0.1),
])
def test_fraction_of_beyond_fifth(text: str, val: float) -> None:
    assert numeric.scan(text).values == {val}


def test_sixth_without_of_stays_ordinal() -> None:
    """'A sixth agent'(여섯째)는 분수가 아니다 — 'of' 가 없으면 서수로 남는다(SY24)."""
    n = numeric.scan("A sixth agent, the Nakama's coordinator, is the fleet's operations manager.")
    assert n.values == set() and n.ordinals == {6}


def test_percentile_bae_is_not_hundred() -> None:
    """'11백분위'의 백은 보조배수(100)가 아니다 — 1100 으로 읽으면 원문 '11-percentile' 과 안 맞는다."""
    assert numeric.scan("약 11백분위 포인트 상승").values == {11}


def test_je_inside_word_is_not_ordinal_prefix() -> None:
    """'과제 17'의 제는 서수 접두어가 아니다 — '제3자'처럼 낱말 첫머리일 때만 서수."""
    n = numeric.scan("자동 생성 과제 17개 × 시드 3개")
    assert n.values == {17, 3} and n.ordinals == set()
    assert numeric.scan("제3자 감사").ordinals == {3}


def test_latex_thousands_separator() -> None:
    assert numeric.scan("첫 토큰 지연이 508 ms에서 3{,}420 ms로 늘었습니다").values == {508, 3420}


@pytest.mark.parametrize(("text", "vals"), [
    ("Twenty-five Fields Medal winners", {25}),
    ("a thirty-two layer network", {32}),
    ("twenty-five million users", {25e6}),
])
def test_hyphenated_compound_cardinals(text: str, vals: set[float]) -> None:
    """'Twenty-five'를 twenty·five 로 쪼개면 거짓 '20명'·'5명'이 통과한다(SY28·SY29)."""
    assert numeric.scan(text).values == vals


@pytest.mark.parametrize(("text", "val"), [
    ("That's roughly two and a half times higher.", 2.5),
    ("after one and a half hours", 1.5),
    ("two and a half million users", 2.5e6),
])
def test_and_a_half(text: str, val: float) -> None:
    """'two and a half' = 2.5 — two(2)·a half(0.5)로 쪼개면 거짓 '2배'가 통과한다(SY30)."""
    assert numeric.scan(text).values == {val}


# ── 알려진 잔여 위양성 (값 대조로는 못 고침 — 문서화해 둔다) ─────────────────────
#
# 둘 다 "원문에 그 숫자가 *수사로* 없지만 근거는 텍스트에 있다"는 종류라, 결정론 산술이 아니라
# 함의 판정(codex)의 영역이다. 결정론 코드로 이걸 통과시키려면 '원문에 없는 수를 만들어도 된다'는
# 규칙이 필요한데 그건 위 두 테스트(진짜 환각)를 동시에 통과시킨다 = 거짓 VERIFIED.
# **의도적으로 BLOCK 을 유지한다**(fail-closed). 빈도: 프로덕션 1,326건 중 4건(0.3%).

def test_known_false_positive_prose_enumeration() -> None:
    """산문 열거 카운트 — 원문이 항목을 나열만 하고 개수를 안 쓴 경우. 세는 건 산술이 아니다."""
    src = "The case lifecycle has states: Ready, In Progress, Successful, Failed, Pending Resolution."
    claim = "케이스 생명주기 상태는 Ready, In Progress, Successful, Failed, Pending Resolution의 5가지로 구성된다."
    assert _certify_arithmetic("C1", Envelope(src, claim, "arithmetic", "{}")).verdict == "BLOCKED"


def test_known_false_positive_article_less_year() -> None:
    """'In the past year' → '지난 1년' — 영어는 관사 없이 기간을 쓰고 한국어는 1 을 명시한다."""
    src = "In the past year, you've created millions of videos in Google Vids."
    claim = "지난 1년 동안 사용자들은 Google Vids에서 수백만 개의 영상을 제작했다."
    assert _certify_arithmetic("C1", Envelope(src, claim, "arithmetic", "{}")).verdict == "BLOCKED"
