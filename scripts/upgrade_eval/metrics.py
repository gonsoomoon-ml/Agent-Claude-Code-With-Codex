"""코드로 재는 요약 지표 — 판정자(LLM) 없이 결정론으로 재는 것만.

공통 기준(summary-evaluation-guide.md)과 연결: 6번(짧고 빽빽하게)·7번(이름 원어 표기)·
확인 목록 조건(숫자·이름이 claim 에 있나)·인용 대조·F2(숫자 검사 오판) 표기 식별.
유보 표현 목록과 최심 위치는 기존 A/B 도구(scripts/ab_prompt.py)를 그대로 쓴다 — 이전 측정과 같은 잣대.
"""
from __future__ import annotations

import re

import ab_prompt

from briefing.core.verification import numeric

# '다.' 로 끝나는 한국어 문장 경계 — 닫는 따옴표가 마침표 앞이나 뒤에 붙는 경우까지(소수점·약어 'U.S.'는 안 나뉨).
_SENT_SPLIT = re.compile(r"(?:(?<=다\.)|(?<=다\.[\"”’])|(?<=다[\"”’]\.))\s+")
_TRANSLIT = re.compile(r"앤트로픽|오픈AI|오픈에이아이|클로드|딥마인드|제미나이|챗GPT|구글|아마존|엔비디아|마이크로소프트|메타(?![데버])")
_LATIN_NAME = re.compile(r"[A-Z][A-Za-z0-9.\-]{2,}")
_DOUBLE_QUOTE = re.compile(r"[\"“]([^\"“”]+)[\"”]")
_HANGUL = re.compile(r"[가-힣]")
_TOKEN = re.compile(r"[가-힣A-Za-z0-9]+")
_F2_PATTERNS = re.compile(r"\d+만\s?(?:개|토큰)?\s?당|\d+배|\d+년간|\d+위|\d+분기|\d+만\s?\d{3,4}")


def split_sentences(text: str) -> list[str]:
    return [s for s in (p.strip() for p in _SENT_SPLIT.split(text.strip())) if s]


def long_sentence_ratio(sentences: list[str], limit: int = 150) -> float:
    """limit 자(공백 포함)를 넘는 문장의 비율."""
    return sum(len(s) > limit for s in sentences) / len(sentences) if sentences else 0.0


def has_hedge(text: str) -> bool:
    return any(h in text for h in ab_prompt._HEDGE)


def deepest_position(source: str, summary: str) -> float | None:
    """요약이 인용한 앵커(숫자·라틴 고유명사)의 원문 내 최심 상대 위치(보조 지표 — 최댓값이라 중간 누락을 가린다)."""
    return ab_prompt._depth(source, summary)[0]


def transliterated_names(text: str) -> list[str]:
    return _TRANSLIT.findall(text)


def _values(text: str) -> tuple[set[float], set[float]]:
    nums = numeric.scan(text)
    return set(nums.values), set(nums.percents)


def uncovered_numbers(summary: str, claims: list[str]) -> list[float]:
    """요약의 수량·퍼센트 중 어떤 claim 에도 (값으로) 없는 것 — 검증 우회 후보."""
    s_vals, s_pcts = _values(summary)
    c_vals: set[float] = set()
    c_pcts: set[float] = set()
    for c in claims:
        v, p = _values(c)
        c_vals |= v
        c_pcts |= p
    missing = [v for v in s_vals if not numeric.contains(v, c_vals)] + [p for p in s_pcts if not numeric.contains(p, c_pcts)]
    return sorted(missing)


def uncovered_names(summary: str, claims: list[str]) -> list[str]:
    """요약의 라틴 고유명사 중 어떤 claim 에도 없는 것(등장 순서 유지)."""
    joined = " ".join(claims)
    out: list[str] = []
    for name in _LATIN_NAME.findall(summary):
        if name not in joined and name not in out:
            out.append(name)
    return out


def why_new_numbers(why: str, summary: str, claims: list[str]) -> list[float]:
    """'왜 중요한가' 칸의 수치 중 요약·claim 어디에도 없는 것(새 사실 도입 신호)."""
    return uncovered_numbers(why, [summary, *claims])


def quote_mismatches(summary: str, source: str) -> list[str]:
    """요약의 큰따옴표 안 한글 인용 중 원문 부분 문자열이 아닌 것. 원문이 한국어가 아니면(번역 인용) 보지 않는다."""
    if not source or len(_HANGUL.findall(source)) / len(source) < 0.10:
        return []
    return [q for q in _DOUBLE_QUOTE.findall(summary) if _HANGUL.search(q) and q not in source]


def repeats_title(title: str, first_sentence: str) -> bool:
    """같은 언어일 때만 — 첫 문장이 제목 토큰을 거의 그대로 되풀이하는지(자카드 ≥ 0.6)."""
    if bool(_HANGUL.search(title)) != bool(_HANGUL.search(first_sentence)):
        return False
    a, b = set(_TOKEN.findall(title)), set(_TOKEN.findall(first_sentence))
    return bool(a and b) and len(a & b) / len(a | b) >= 0.6


def is_known_f2_block(claim_text: str, evidence: str) -> bool:
    """알려진 숫자 검사 오판(F2) 표기로 막힌 BLOCK 인지 — 'per million'·배수·환산·서수·만 혼합 표기."""
    return evidence.startswith("원문에 없는 수치") and bool(_F2_PATTERNS.search(claim_text))
