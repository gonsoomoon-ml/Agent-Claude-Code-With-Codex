"""quality_checks — 요약 품질 그림자 검사(S3, 2026-10-18). **로그만** 남긴다 — 판정(gate)·메일(render)은 안 바꾼다.

왜: 요약 품질 공통 기준 점검(2026-10-17, work_note 01-research/criteria-application-audit.md)에서 코드로 잴 수 있는
위반을 찾았지만, 얼마나 자주 걸리는지 모른 채 실제 검사로 막으면 오탐으로 기사를 잃는다. 먼저 운영에서 재고(그림자),
결과를 보고 하나씩 실제 검사로 올릴지 정한다. S5(이름 표기)·U8 ②(요약 모델 교체) 전후 비교 도구이기도 하다.

검사(사실층 카드 1장당 — 결과 코드 = Finding.check):
- summary_number_not_in_claims — 요약의 숫자가 어떤 claim 에도 없음(검증을 안 거친 숫자)
- summary_name_not_in_claims  — 요약의 영문 고유명사가 어떤 claim 에도 없음
- qualifier_dropped           — 원문이 한정어로만 쓴 숫자('up to 2x')를 요약이 한정어 없이 씀('2배' — 과장)
- quote_not_verbatim          — 따옴표 인용이 원문에 그대로 없음(한국어 원문만 — 영어 원문은 번역이라 제외)
- transliterated_name         — 영문 이름이 확실한 회사·모델을 한글 음역으로 씀(D4: 원어로 통일)
- why_new_number              — 사실층 '왜 중요한가'에 요약·claim 에 없는 숫자
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .verification import numeric


@dataclass(frozen=True)
class Finding:
    check: str
    detail: str


# 영문 고유명사 — 대문자로 시작해 소문자가 이어지는 낱말('Anthropic'·'Claude'). 'AI'·'API' 같은 약어는 뺀다(흔하고 뜻이 일반).
_RE_NAME = re.compile(r"(?<![A-Za-z0-9])[A-Z][a-z][A-Za-z0-9\-]*")
# 수치 한정어 — 원문(영어·한국어)과 요약(한국어). 범위·근사를 나타내 같은 숫자라도 뜻이 달라진다('최대 2배' ≠ '2배').
_EN_QUAL = (r"up to|as many as|as much as|more than|over|at least|nearly|almost|about|around|roughly|"
            r"approximately|less than|under|fewer than|close to")
_KO_QUAL_BEFORE = r"최대|약|최소|거의|대략|평균"
_KO_QUAL_AFTER = r"이상|이하|미만|초과|이내|여|가량|넘게|넘는|안팎|정도|남짓|내외|가까이|까지|선|수준|전후|쯤|즈음"
_RE_QUAL_BEFORE = re.compile(rf"(?:{_EN_QUAL}|{_KO_QUAL_BEFORE})\s*\$?\s*$", re.I)
_RE_QUAL_AFTER = re.compile(rf"^\s*[^\s\d.,]{{0,4}}\s*(?:{_KO_QUAL_AFTER})")
_RE_DIGITS = re.compile(r"\d[\d,]*(?:\.\d+)?")
# 따옴표 인용(6자 이상) — 종류별로 여는·닫는 짝을 맞춘다. 곧은 작은따옴표(')는 영어 아포스트로피('Claude's')와
# 구분이 안 돼 뺀다(기준값 점검에서 아포스트로피부터 다음 따옴표까지를 인용으로 잡은 오탐이 나왔다).
_RE_QUOTES = (re.compile(r"“([^”]{6,}?)”"), re.compile(r'"([^"]{6,}?)"'), re.compile(r"‘([^’]{6,}?)’"),
              re.compile(r"「([^」]{6,}?)」"))
# 영문 이름이 확실한 회사·모델의 한글 음역. '메타'는 '메타데이터' 같은 다른 낱말과 구분하려고 조사·문장부호가 따를 때만.
_RE_TRANSLIT = re.compile(r"앤트로픽|오픈에이아이|오픈AI|딥마인드|제미나이|챗GPT|엔비디아|마이크로소프트|구글|아마존|클로드"
                          r"|메타(?=[은는이가의와과를도에로,.\s)]|$)")


def shadow_checks(card, source_text: str) -> list[Finding]:
    """사실층 카드 1장(DraftCard) + 동결 원문 → 걸린 검사 목록. 순수 함수(LLM·AWS 불필요)."""
    src = source_text or ""
    claim_nums = _union(_nums(c.text) for c in card.claims)   # claim 마다 따로 — 이어 붙이면 숫자가 서로 엮인다
    claims_text = " ".join(c.text for c in card.claims).lower()
    summary_nums = _nums(card.summary)
    out: list[Finding] = []

    if missing := sorted(v for v in summary_nums if not numeric.contains(v, claim_nums)):
        out.append(Finding("summary_number_not_in_claims", _fmt(missing)))
    names = dict.fromkeys(m.group() for m in _RE_NAME.finditer(card.summary))
    if missing_names := [n for n in names if n.lower() not in claims_text]:
        out.append(Finding("summary_name_not_in_claims", ", ".join(missing_names)))
    if dropped := _qualifier_dropped(card.summary, src):
        out.append(Finding("qualifier_dropped", ", ".join(dropped)))
    if _is_korean(src):
        norm_src = _norm(src)
        quotes = dict.fromkeys(q for rx in _RE_QUOTES for q in rx.findall(card.summary))
        bad = [q for q in quotes if _norm(q) not in norm_src]
        if bad:
            out.append(Finding("quote_not_verbatim", " | ".join(bad)))
    if translit := list(dict.fromkeys(_RE_TRANSLIT.findall(card.summary))):
        out.append(Finding("transliterated_name", f"{', '.join(translit)} (원문 {'ko' if _is_korean(src) else 'en'})"))
    if new := sorted(v for v in _nums(card.why_it_matters) if not numeric.contains(v, summary_nums | claim_nums)):
        out.append(Finding("why_new_number", _fmt(new)))
    return out


def _nums(text: str) -> set[float]:
    n = numeric.scan(text or "")
    return set(n.values) | set(n.percents)


def _union(sets) -> set[float]:
    out: set[float] = set()
    for s in sets:
        out |= s
    return out


def _occurrences(text: str) -> list[tuple[set[float], str]]:
    """숫자가 나온 자리마다 (값들, 붙은 한정어 — 없으면 ""). 값은 숫자 뒤 단위·스케일까지 읽는다('4 billion'·'30%'·'1만 2000')."""
    out = []
    for m in _RE_DIGITS.finditer(text):
        vals = _nums(text[m.start():_number_end(text, m.end())])
        q = (_RE_QUAL_BEFORE.search(text[max(0, m.start() - 16):m.start()])
             or _RE_QUAL_AFTER.search(text[m.end():m.end() + 10]))
        out.append((vals, " ".join(q.group().split()).strip("$ ") if q else ""))
    return out


def _number_end(text: str, end: int) -> int:
    """숫자 뒤 단위·스케일까지 읽되 **다음 숫자로 넘어가지 않는** 끝 위치(최대 12자).

    '1만 2000'·'16만 5천'처럼 숫자·만억조천백십·공백·쉼표로만 이어지면 한 수로 읽고, 다른 글자('개에서 최대')를 지난
    뒤 나오는 숫자에서 멈춘다 — 기준값 점검에서 '기존 3개에서 최대 20개'의 '3' 자리가 20 까지 읽은 오탐이 나왔다.
    """
    seen_other = False
    stop = end
    for i, ch in enumerate(text[end:end + 12]):
        if ch.isdigit() and seen_other:
            break
        if not (ch.isdigit() or ch in ",. 만억조천백십"):
            seen_other = True
        stop = end + i + 1
    return stop


def _qualifier_dropped(summary: str, source: str) -> list[str]:
    """원문에서 **한정어로만** 나온 숫자를 요약이 한정어 없이 쓴 경우 → ["5(up to)", …]. 원문에 같은 숫자가 맨숫자로도
    있으면 넘긴다. 연도(1900–2100 정수)는 'over 2025' 같은 전치사 오독이 많아 뺀다.
    원문 한정어를 함께 적는다 — 'up to'(상한)를 뺀 것이 'about'(근사)을 뺀 것보다 심각해, 나중에 가려 볼 수 있게."""
    src_occ = _occurrences(source)
    qual_of: dict[float, str] = {}
    for vals, q in src_occ:
        for v in vals:
            if q:
                qual_of.setdefault(v, q)
    bare = _union(v for v, q in src_occ if not q)
    hits = {}
    for vals, q in _occurrences(summary):
        for v in vals:
            if q or _is_year(v) or numeric.contains(v, bare):
                continue
            src_q = next((qq for sv, qq in qual_of.items() if numeric.contains(v, {sv})), "")
            if src_q:
                hits[v] = src_q
    return [f"{_fmt([v])}({hits[v]})" for v in sorted(hits)]


def _is_year(v: float) -> bool:
    return v == int(v) and 1900 <= v <= 2100


def _is_korean(text: str) -> bool:
    """원문 언어 — 한글이 라틴 문자보다 많으면 한국어 원문."""
    ko = sum(1 for ch in text if "가" <= ch <= "힣")
    en = sum(1 for ch in text if ch.isascii() and ch.isalpha())
    return ko > en


def _norm(text: str) -> str:
    return " ".join(text.split())


def _fmt(vals) -> str:
    return ", ".join(f"{v:g}" if v != int(v) else f"{int(v)}" for v in vals)
