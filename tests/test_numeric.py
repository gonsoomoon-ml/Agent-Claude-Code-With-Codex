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
