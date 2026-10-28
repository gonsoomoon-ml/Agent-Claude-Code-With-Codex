"""rereport — 재보도 판정자: "B(오늘 후보)는 주로 A(원문)와 같은 발표에 대한 글인가?"(2026-10-28).

B 의 본문이 A 를 링크한 쌍만 판정한다(쌍 찾기 = core/rereport_dedup.py). True 면 B 를 메일에서 뺀다.
★ "새 정보를 더했나" 로 물으면 실패한다 — 재보도는 늘 세부를 조금 더해 12쌍 중 0건만 걸렀다(2026-10-28 실험).
  "주로 같은 발표인가" 판정은 10건 제외·2건 유지(gitai=다른 도구, AAIF=여러 항목 중 하나)로 기대와 일치.
fail-open: 호출 예외·JSON 없음·`same` 이 bool 아님 → same=None(판정 실패) → 호출자가 B 를 남긴다.
설계: docs/superpowers/specs/2026-10-28-cited-rereport-dedup-design.md
"""
from __future__ import annotations

import json
from collections.abc import Callable
from typing import NamedTuple

MAX_JUDGE_CHARS = 8000  # A·B 본문 각 앞부분 상한 — 재생 게이트가 검증한 값. 동결본 상한(MAX_SOURCE_CHARS 20K, 37c6f22)보다
#                         작다: 재보도 여부는 글 앞부분(주제·출처 소개)에서 갈리고, 입력 토큰을 쌍당 ~5K 로 묶는다

REREPORT_SYSTEM = """\
Article A was already sent to our reader. Article B was published later and links to A.
Question: is B mainly a report about the SAME announcement or content as A?

SAME (answer true): B covers A's announcement/finding/release as its main news — even if B translates it
(e.g. a Korean write-up), summarizes it, adds some extra details, quotes, reactions or comparisons.
DIFFERENT (answer false): B's main subject is something else — a different product, project, release or event —
and A is only cited as background, inspiration, or one item among several equal items.

Answer only JSON: {"same": true|false, "reason": "<one short sentence>"}"""


class RereportVerdict(NamedTuple):
    same: bool | None  # True = 같은 발표(B 제외) · False = 다른 주제 · None = 판정 실패(B 유지)
    reason: str


# (a_text, b_text) -> 판정. production = Haiku(relevance_bedrock.make_bedrock_rereport), 테스트 = fake.
RereportFn = Callable[[str, str], RereportVerdict]


def _first_json_object(ans: str) -> dict | None:
    """응답 안 첫 JSON 객체(앞뒤 잡담 허용). reason 에 `}` 가 들어가도 깨지지 않게 정규식 대신 raw_decode."""
    dec = json.JSONDecoder()
    start = ans.find("{")
    while start != -1:
        try:
            obj, _end = dec.raw_decode(ans, start)
            if isinstance(obj, dict):
                return obj
        except ValueError:
            pass
        start = ans.find("{", start + 1)
    return None


def llm_rereport(a_text: str, b_text: str, *, invoke: Callable[[str, str], str]) -> RereportVerdict:
    """A·B 본문(각 MAX_JUDGE_CHARS 자) → 판정. invoke=(system, user)->str. 어떤 예외도 밖으로 내지 않는다."""
    user = f"<A>\n{(a_text or '')[:MAX_JUDGE_CHARS]}\n</A>\n\n<B>\n{(b_text or '')[:MAX_JUDGE_CHARS]}\n</B>"
    try:
        ans = invoke(REREPORT_SYSTEM, user) or ""
        obj = _first_json_object(ans)
    except Exception as err:  # throttle·timeout·파싱 — 브리핑을 막지 않는다(fail-open)
        return RereportVerdict(None, f"{type(err).__name__}: {err}")
    if obj is None or not isinstance(obj.get("same"), bool):
        return RereportVerdict(None, f"판정 JSON 없음: {ans[:80]!r}")
    return RereportVerdict(obj["same"], str(obj.get("reason", "")))
