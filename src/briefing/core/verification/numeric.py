"""numeric — 교차언어(cross-lingual) 수치 정규화. 산술 재도출의 *값* 추출기.

**왜 필요한가(실측):** 우리 파이프라인은 영어 원문 → 한국어 claim 이다. 그런데 영어는 수를 **단어**로,
한국어는 **숫자**로 쓴다("eight months" → "8개월", "four trillion" → "4조", "October" → "10월").
문자열 대조 검증기는 원문에서 리터럴 "8" 을 찾다 실패해 **BLOCK** 한다.
2026-07-17 감사(13일·223카드): BLOCKED **243/243(100%)이 이 위양성**이었고 진짜 오류 차단은 0건이었다.

**설계의 심장 — 문자열이 아니라 `값`을 비교한다.** 순진한 접근(영단어 수사를 숫자로 바꿔 원문
토큰집합에 *주입*)은 위양성을 100%→20% 로 낮추면서 **catch-rate 를 100%→50% 로 붕괴**시킨다
(실증됨): 원문 'third-party' 의 'third'→'3' 주입이 '3천만→3억'(10배 오류) claim 을 통과시킨다.
값 비교는 이 함정이 원리적으로 무해하다 — '3억'은 **3e8** 이라 'third'가 준 **3** 과 애초에 다른 값이다.
자릿수(magnitude)를 보존하는 것이 이 모듈의 존재 이유다.

**불변식(비협상):** 이 모듈은 *동치(equivalence)만* 넓힌다. 거짓 VERIFIED 를 만들 수 있는 규칙은 금지.
- **네임스페이스 분리** — 수량·월·서수를 각각 다른 집합에 담는다. 'July 27' 은 월 7 을 주지만 수량 7 은
  주지 않고(근거 없는 "7종" claim 통과 방지 — 회귀셋 SY04), 'third-party' 는 서수 3 을 주지만 수량 3 은
  주지 않는다(작은 정수로 원문 집합을 오염시켜 진양성을 잃는 것 방지).
- **소비(consume) 순서** — 큰 표현을 먼저 먹는다. 'one million' 은 **1e6 하나**이지 {1, ...} 가 아니다
  (안 그러면 "100개" claim 이 통과 — SY02). 분수를 맨숫자보다 먼저 먹어야 '2분의 3'(=1.5)의 순서 반전을
  잡는다(SY07).
- **반올림 관용 금지** — 부동소수 표현 오차(rel 1e-9)만. '500만 vs one million'(5배)을 놓치면 안 된다.
- **월 이름은 대소문자 구분** — 'May'(월) vs 'may'(조동사). 소문자까지 먹으면 원문의 흔한 'may' 가
  월 5 를 만들어 거짓 VERIFIED 를 낸다.

회귀셋 `tests/eval_set/cases.jsonl` 이 이 규칙들을 케이스로 고정한다(위양성 20 + 진양성 8, 지름길 정조준).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# ── 어휘 테이블 ────────────────────────────────────────────────────────────────

# 한국어 만/억/조 = 10^4 그룹핑(영어 thousand/million/billion = 10^3 그룹핑과 어긋난다 — 위양성의 큰 축).
_KO_MYRIAD = {"만": 10**4, "억": 10**8, "조": 10**12}
_KO_SUB = {"십": 10, "백": 10**2, "천": 10**3}  # 만/억/조 앞의 보조 배수: '3천만' = 3 × 천 × 만
_KO_RANK = {"만": 1, "억": 2, "조": 3}  # 체이닝 판정용(내림차순 인접만 결합): '4억 6,600만'

_EN_SCALE = {"hundred": 10**2, "thousand": 10**3, "million": 10**6,
             "billion": 10**9, "trillion": 10**12}
_EN_SUFFIX = {"k": 10**3, "m": 10**6, "b": 10**9}  # '27B' = 27e9 (모델 파라미터 표기 관행)

_EN_CARD = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
    "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}
# 배수 동사/부사 — 영어 'tripled' ↔ 한국어 '3배로 늘었다'(실측 위양성). _EN_CARD 와 분리한다:
# 이 어휘들은 관용구에서 배수를 뜻하지 않는데('double-digit growth'=두 자릿수, 'doubled down'=
# 강화했다) 기수 테이블에 섞으면 원문에 없는 2·3 을 창조해 '2배 성장' 같은 거짓 claim 을 통과시킨다.
# 그래서 **명확히 배수인 형태만** + 뒤에 배수 아닌 명사가 오면 배제(_RE_MULT).
_EN_MULT = {"twice": 2, "doubled": 2, "tripled": 3, "quadrupled": 4, "quintupled": 5}
_MULT_ALT = "|".join(sorted(_EN_MULT, key=len, reverse=True))
# 'doubled down'·'double-digit' 류 관용구 제외. 'doubled' 뒤에 down/up/digit 이 오면 배수가 아니다.
_RE_MULT = re.compile(rf"\b({_MULT_ALT})\b(?!\s*(?:down|up|digit))", re.I)
# 서수 — 수량과 *다른 네임스페이스*. 'third-party'↔'제3자' 동치는 인정하되 수량 3 은 못 만든다.
_EN_ORD = {
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6,
    "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10, "eleventh": 11, "twelfth": 12,
}
_MONTHS = {  # ★ 대소문자 구분 — 'may'(조동사)를 월 5 로 읽으면 안 된다.
    "January": 1, "February": 2, "March": 3, "April": 4, "May": 5, "June": 6,
    "July": 7, "August": 8, "September": 9, "October": 10, "November": 11, "December": 12,
}
_EN_DENOM = {"half": 2, "halves": 2, "third": 3, "thirds": 3, "quarter": 4, "quarters": 4,
             "fourth": 4, "fourths": 4, "fifth": 5, "fifths": 5}

_CARD_ALT = "|".join(sorted(_EN_CARD, key=len, reverse=True))
_ORD_ALT = "|".join(sorted(_EN_ORD, key=len, reverse=True))
_DENOM_ALT = "|".join(sorted(_EN_DENOM, key=len, reverse=True))
_MONTH_ALT = "|".join(_MONTHS)
_SCALE_ALT = "|".join(_EN_SCALE)

# ── 패턴 (선언 순서 = 소비 우선순위. 위에서 먹은 글자는 아래 패턴이 다시 못 읽는다) ──────────────

_NUM = r"\d[\d,]*(?:\.\d+)?"

_RE_PERCENT = re.compile(rf"({_NUM})\s*(?:%p|%|percentage points?|percent|퍼센트)", re.I)
# 한국어 분수는 **분모가 먼저**다: 'N분의 M' = M/N. 순서를 뒤집으면 SY07('2분의 3'=1.5)이 통과한다.
_RE_FRAC_KO = re.compile(rf"({_NUM})\s*분의\s*({_NUM})")
_RE_FRAC_KO_IN = re.compile(rf"({_NUM})\s*개\s*중\s*({_NUM})\s*개")
# 'a third'(=1/3) — 영어는 분자 1 을 관사로 쓴다. 없으면 'third' 가 서수로 새어 위양성이 된다(실측).
# 분수 × 스케일 결합 — 'half a million'(=5e5) · 'a quarter of a million'(=2.5e5) · 'two-thirds of
# a billion'. 분수 규칙보다 **먼저** 먹어야 한다: 아니면 'half' 가 분수로, 남은 'a million' 이
# 통짜 1e6 으로 잡혀 **원문에 없는 1e6 을 창조**하고 '100만 달러' 거짓 claim 이 통과한다(실증).
_RE_FRAC_SCALE = re.compile(
    rf"\b(?:(a|{_CARD_ALT}|{_NUM})[\s-]+)?({_DENOM_ALT})\s+(?:of\s+)?(?:a|an|one)\s+({_SCALE_ALT})s?\b", re.I)
_RE_FRAC_EN = re.compile(rf"\b(a|{_CARD_ALT}|{_NUM})[\s-]+({_DENOM_ALT})\b", re.I)
_RE_FRAC_EN_IN = re.compile(rf"\b({_CARD_ALT}|{_NUM})\s+in\s+({_CARD_ALT}|{_NUM})\b", re.I)
# 어휘화된 숫자 — 수량 주장이 아니라 고정 표현의 일부('1인당' = per capita; 원문엔 대응 수사가 없다).
_RE_LEXICAL = re.compile(rf"{_NUM}\s*인당")
_RE_ISO_DATE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_RE_MONTH_KO = re.compile(rf"({_NUM})\s*월")  # '8개월'(기간)은 digit 뒤가 '개'라 미매치
_RE_MONTH_EN = re.compile(rf"\b({_MONTH_ALT})\b")  # ★ re.I 금지 — 'may' 오독 방지
_RE_ORD_KO = re.compile(rf"제\s*({_NUM})")  # 제3자·제2차
_RE_ORD_EN = re.compile(rf"\b({_ORD_ALT})\b", re.I)
_RE_ORD_DIGIT = re.compile(r"\b(\d+)(?:st|nd|rd|th)\b", re.I)
# ★ 만/억/조 뒤 경계 — 한국어에서 이 글자들은 *다른 단어의 일부*이거나 *조사*이기도 하다(실측 회귀):
#   '3.1조차'(조차=even) → 3.1e12 오독 · 'Fable 5만 K3보다'(만=only) → 50000 오독.
#   그래서 뒤에 오는 것이 ① 단위 명사 ② 문장부호/끝 ③ 공백+한글 ④ 공백+숫자(체이닝 '4억 6,600만')
#   중 하나일 때만 수량으로 읽는다. 대가: '100만원'처럼 단위 명사가 목록에 없으면 놓친다(보수적 = 안전).
_KO_COUNTER = ("개월|개|명|원|달러|건|회|대|장|줄|년|배|가지|톤|여|권|점|번|채|마리|시간|분|초|일|주|달|"
               "판|호|위|쪽|자|석|편|병|잔|km|kg|억|만|조")
_KO_BOUND = rf"(?=(?:{_KO_COUNTER})|[^\s가-힣A-Za-z0-9]|$|\s+[가-힣]|\s*\d)"
_RE_KO_GROUP = re.compile(rf"({_NUM})\s*({'|'.join(_KO_SUB)})?\s*({'|'.join(_KO_MYRIAD)}){_KO_BOUND}")
# 만 단위 뒤에 붙는 천/백/십 자리 — '16만 5천'(=165,000). 이 꼬리를 못 읽으면 {160000, 5} 로 흩어져
# 원문 '165,000' 과 영영 안 맞는다(실측 위양성).
_RE_KO_TAIL = re.compile(rf"\s*({_NUM})\s*({'|'.join(_KO_SUB)}){_KO_BOUND}")
# 만/억/조 **없이** 쓰이는 보조배수 — '5천 명'(=5,000)·'3백 명'(=300). _RE_KO_GROUP 은 만/억/조를
# 필수로 요구해 이걸 놓쳤고, 그러면 뒤의 맨숫자 스캔이 '5' 만 주워 **1000배 축소된 값**이 된다
# → 원문의 무관한 맨숫자 5 가 '5천 명' claim 을 인증한다(적대 검증에서 실증). _RE_KO_GROUP 뒤에 적용.
_RE_KO_SUB_ONLY = re.compile(rf"({_NUM})\s*({'|'.join(_KO_SUB)}){_KO_BOUND}")
# 등위 생략(coordination ellipsis) — 'Orca was trained at 0.8 and 4 billion parameters' 는
# 0.8**billion** 과 4billion 을 뜻한다. 이걸 못 읽으면 claim '0.8B' 가 원문 맨숫자 0.8 과 어긋나
# 위양성이 된다(실측). 반드시 _RE_EN_SCALE 보다 먼저 소비.
#
# ★ **앞에 제품명이 오면 등위가 아니다** — 'Gemini 3.5 and 4.8 billion parameters' 의 3.5 는
# 버전 번호라 3.5e9 를 만들면 원문에 없는 값을 **창조**한다(적대 검증에서 실증). 제품명 뒤의 수는
# 스케일을 공유하지 않는다. 앞 문맥 검사는 아래 _RE_PROPER_BEFORE.
_RE_EN_SCALE_PAIR = re.compile(
    rf"\b({_NUM})\s*(?:and|or|to|~|–|-)\s*({_NUM})\s+({_SCALE_ALT})s?\b", re.I)
# 등위 판정: 앞 낱말이 대문자로 시작(= 제품·모델명)이면 등위 생략이 아니라 버전 번호다.
# (가변폭이라 정규식 lookbehind 로는 못 쓴다 — scan() 의 _pair 가 매치 앞 문맥에 적용한다.)
_RE_PROPER_BEFORE = re.compile(r"\b[A-Z][A-Za-z0-9.\-]*\s*$")
# TODO(v-next): 제품 버전 네임스페이스 — 'Claude Opus 4.8' 의 4.8 은 수량이 아니라 **식별자**인데
# 지금은 values 에 들어가 claim '4.8배 빠르다'를 인증한다(적대 검증에서 실증, 미해결).
# months·ordinals 처럼 별도 집합으로 빼야 한다. 휴리스틱('대문자 제품명 뒤 소수점 수')은 오탐
# 위험이 있어 eval set 케이스를 먼저 만들고 착수할 것.
# 'a' 를 분자 1 로 받는다 — 'a trillion parameters'(→1조)·'A million lines'(→100만). 관사 뒤가
# 스케일 단어일 때로 한정되므로 흔한 'a' 오독 위험 없음.
_RE_EN_SCALE = re.compile(rf"\b(?:({_NUM})|(a|{_CARD_ALT}))[\s-]+({_SCALE_ALT})s?\b", re.I)
# 뒤 경계를 `\b` 로 쓰면 안 된다 — 한글은 단어문자라 '27B를'(조사 결합)에서 경계가 안 생겨
# 접미사를 놓치고 맨숫자 27 로 새어나간다(회귀셋 FP10). 라틴 문자/숫자만 아니면 경계로 본다.
_RE_EN_SUFFIX = re.compile(rf"\b({_NUM})\s*([BMK])(?![A-Za-z0-9])")
# 관용구의 'one' 은 수량 주장이 아니다 — 'one of the co-chairs'(여럿 중 하나)·'one of its'.
# 이걸 값 1 로 수확하면 원문에 널린 관용구가 claim 의 '1명'·'1개'를 무상으로 인증한다(리뷰 지적).
# 'one of three co-chairs' 처럼 뒤에 수가 있으면 그 수는 별도로 잡히므로 손실 없음.
_RE_IDIOM_ONE = re.compile(r"\bone of (?:the|its|his|her|their|our)\b", re.I)
_RE_EN_CARD = re.compile(rf"\b({_CARD_ALT})\b", re.I)
_RE_PLAIN = re.compile(_NUM)


@dataclass(frozen=True)
class Nums:
    """텍스트 1건에서 뽑은 값들. **네임스페이스 분리가 안전성의 핵심**(모듈 docstring 불변식)."""
    values: set[float] = field(default_factory=set)    # 일반 수량(자릿수 보존)
    months: set[int] = field(default_factory=set)      # 1~12
    ordinals: set[int] = field(default_factory=set)    # 제N·Nth
    percents: set[float] = field(default_factory=set)  # 파생 가능 → 정책상 DEMOTED

    def empty(self) -> bool:
        return not (self.values or self.months or self.ordinals or self.percents)


def _val(s: str) -> float:
    return float(s.replace(",", ""))


def _num_or_word(tok: str) -> float:
    low = tok.lower()
    if low == "a":  # 'a third' = 1/3 — 영어는 분자 1 을 관사로 쓴다
        return 1.0
    return float(_EN_CARD[low]) if low in _EN_CARD else _val(tok)


def _mask(text: str, start: int, end: int) -> str:
    """소비된 구간을 공백으로 덮어 뒤 패턴이 재해석하지 못하게 한다(이중 계수 방지)."""
    return text[:start] + " " * (end - start) + text[end:]


def _ratio(numer: float, denom: float) -> float | None:
    """분수 값. 분모 0 이면 None(값 없음) — **예외를 던지면 안 된다.**

    이 모듈은 certifier 안에서 돈다. 여기서 ZeroDivisionError 가 나면 그 카드가 통째로 죽는다
    (2026-07-02 인시던트: 한 카드의 예외가 브리핑 전체를 무너뜨렸다 — 지금은 카드별 격리가
    있지만 여전히 카드 1장을 잃는다). '0분의 5' 같은 입력은 드물지만 author 오타 하나면 충분하다.
    """
    return None if denom == 0 else numer / denom


def scan(text: str) -> Nums:
    """텍스트 → 값 집합. 큰 표현부터 소비하며 마스킹한다 — **순서가 곧 정확성**이다."""
    values: set[float] = set()
    months: set[int] = set()
    ordinals: set[int] = set()
    percents: set[float] = set()
    work = text or ""

    def consume(rx: re.Pattern[str], fn) -> None:
        nonlocal work
        while True:
            m = rx.search(work)
            if not m:
                return
            fn(m)
            work = _mask(work, m.start(), m.end())

    # ① 퍼센트 — 원문 수치에서 *파생*됐을 수 있어 별도 정책(누락 시 BLOCK 아니라 DEMOTED).
    consume(_RE_PERCENT, lambda m: percents.add(_val(m.group(1))))

    # ② 분수 × 스케일 — 'half a million'=5e5. 분수·스케일 규칙 **둘 다보다 먼저**(위 패턴 주석 참조).
    #    분모는 _EN_DENOM(상수)이라 0 이 될 수 없다 — 분모 0 위험은 아래 ③(원문 숫자가 분모)에 있다.
    consume(_RE_FRAC_SCALE, lambda m: values.add(
        (_num_or_word(m.group(1)) if m.group(1) else 1.0)
        / _EN_DENOM[m.group(2).lower()] * _EN_SCALE[m.group(3).lower()]))

    # ③ 분수 — 맨숫자보다 먼저. 'two-thirds'를 {2,3}으로 흘리면 순서 반전 오류를 놓친다.
    #    분모 0 은 값을 만들지 않는다(_ratio → None). 소비는 하므로 뒤 패턴이 재해석하지 않는다.
    def _add_ratio(numer: float, denom: float) -> None:
        r = _ratio(numer, denom)
        if r is not None:
            values.add(r)
    consume(_RE_FRAC_KO, lambda m: _add_ratio(_val(m.group(2)), _val(m.group(1))))
    consume(_RE_FRAC_KO_IN, lambda m: _add_ratio(_val(m.group(2)), _val(m.group(1))))
    consume(_RE_FRAC_EN, lambda m: _add_ratio(_num_or_word(m.group(1)), _EN_DENOM[m.group(2).lower()]))
    consume(_RE_FRAC_EN_IN, lambda m: _add_ratio(_num_or_word(m.group(1)), _num_or_word(m.group(2))))

    # ④ 어휘화된 숫자 — 값으로 세지 않고 버린다.
    consume(_RE_LEXICAL, lambda m: None)

    # ④ 월 — 별도 네임스페이스. ISO 날짜는 연/월/일을 제자리에.
    def _iso(m: re.Match[str]) -> None:
        months.add(int(m.group(2)))
        values.update({_val(m.group(1)), float(int(m.group(3)))})
    consume(_RE_ISO_DATE, _iso)
    consume(_RE_MONTH_KO, lambda m: months.add(int(_val(m.group(1)))))
    consume(_RE_MONTH_EN, lambda m: months.add(_MONTHS[m.group(1)]))

    # ⑤ 서수 — 별도 네임스페이스('제3자' ↔ 'third-party').
    consume(_RE_ORD_KO, lambda m: ordinals.add(int(_val(m.group(1)))))
    consume(_RE_ORD_DIGIT, lambda m: ordinals.add(int(m.group(1))))
    consume(_RE_ORD_EN, lambda m: ordinals.add(_EN_ORD[m.group(1).lower()]))

    # ⑥ 한국어 만/억/조 — 체이닝('4억 6,600만' = 4.66e8)까지 한 값으로.
    work = _scan_ko_groups(work, values)

    # ⑥-b 만/억/조 없는 보조배수('5천 명'=5,000) — ⑥ 뒤라야 '5천만'의 천을 다시 읽지 않는다.
    consume(_RE_KO_SUB_ONLY, lambda m: values.add(_val(m.group(1)) * _KO_SUB[m.group(2)]))

    # ⑦ 등위 생략 스케일 — '0.8 and 4 billion' = {8e8, 4e9}. 반드시 단일 스케일 구보다 먼저.
    #    단 앞이 제품명이면(= 'Gemini 3.5 and 4.8 billion') 첫 수는 버전이라 스케일을 공유하지 않는다.
    def _pair(m: re.Match[str]) -> None:
        scale = _EN_SCALE[m.group(3).lower()]
        values.add(_val(m.group(2)) * scale)          # 뒤 수는 항상 스케일과 결합
        if not _RE_PROPER_BEFORE.search(work[:m.start()]):
            values.add(_val(m.group(1)) * scale)      # 등위일 때만 앞 수도 결합
        else:
            values.add(_val(m.group(1)))              # 버전 번호 — 그대로 둔다
    consume(_RE_EN_SCALE_PAIR, _pair)

    # ⑧ 영어 스케일 구 — 'one million' 을 통째로 1e6 으로 소비(SY02 방어의 핵심).
    consume(_RE_EN_SCALE, lambda m: values.add(
        (_val(m.group(1)) if m.group(1) else _num_or_word(m.group(2)))
        * _EN_SCALE[m.group(3).lower()]))
    consume(_RE_EN_SUFFIX, lambda m: values.add(_val(m.group(1)) * _EN_SUFFIX[m.group(2).lower()]))

    # ⑧ 배수 동사('tripled'=3배) — 관용구(doubled down·double-digit)는 _RE_MULT 가 배제.
    consume(_RE_MULT, lambda m: values.add(float(_EN_MULT[m.group(1).lower()])))

    # ⑧-b 관용구의 'one' 소비(값 없음) — 기수 스캔 전이라야 1 로 새지 않는다.
    consume(_RE_IDIOM_ONE, lambda m: None)

    # ⑨ 남은 기수 단어. 스케일 구 뒤라야 'one million' 의 'one' 이 1 로 새지 않는다.
    consume(_RE_EN_CARD, lambda m: values.add(float(_EN_CARD[m.group(1).lower()])))

    # ⑨ 남은 맨숫자.
    consume(_RE_PLAIN, lambda m: values.add(_val(m.group())))
    return Nums(values, months, ordinals, percents)


def _scan_ko_groups(text: str, values: set[float]) -> str:
    """한국어 만/억/조 그룹 → 값. **내림차순으로 인접하면 결합**한다.

    '4억 6,600만' 을 {4e8, 6.6e7} 로 흘리면 원문 '466 million'(=4.66e8)과 영영 안 맞는다.
    결합 조건 = 사이가 공백/쉼표뿐 + 단위 rank 가 strictly 내림차순('4억 6,600만' ✓ / '3만 4만' ✗).
    """
    ms = list(_RE_KO_GROUP.finditer(text))
    spans: list[tuple[int, int]] = []
    i = 0
    while i < len(ms):
        chain = [ms[i]]
        j = i + 1
        while j < len(ms):
            if text[chain[-1].end():ms[j].start()].strip(" ,") != "":
                break
            if _KO_RANK[ms[j].group(3)] >= _KO_RANK[chain[-1].group(3)]:
                break
            chain.append(ms[j])
            j += 1
        total = 0.0
        for m in chain:
            sub = _KO_SUB[m.group(2)] if m.group(2) else 1
            total += _val(m.group(1)) * sub * _KO_MYRIAD[m.group(3)]
            spans.append((m.start(), m.end()))
        tail = _RE_KO_TAIL.match(text, chain[-1].end())  # '16만' 뒤의 '5천'
        if tail:
            total += _val(tail.group(1)) * _KO_SUB[tail.group(2)]
            spans.append((tail.start(), tail.end()))
        values.add(total)
        i = j
    for start, end in spans:  # 소비 구간 마스킹 — 뒤의 맨숫자 스캔이 '4'·'6600' 을 다시 읽지 않게
        text = _mask(text, start, end)
    return text


def contains(needle: float, haystack: set[float]) -> bool:
    """부동소수 표현 오차만 허용(rel 1e-9). **반올림 관용은 금지** — 배수 오류를 놓친다."""
    return any(abs(needle - h) <= 1e-9 * max(abs(needle), abs(h), 1.0) for h in haystack)
