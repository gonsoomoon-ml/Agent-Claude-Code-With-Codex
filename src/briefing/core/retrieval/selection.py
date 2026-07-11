"""selection — 캡 초과 시 top-K 선별: 주=Haiku pick-K(invoke seam), 폴백=최신순 잘림(=기존 캡 동작).

relevance(관련성 YES/NO)에 이은 curate-stage **사전 필터 2호** — author/certifier *이전*에 포함 여부만
결정하므로 decorrelation 무관(relevance 와 같은 §3 논거). 왜 집합당 1콜인가: "8건 중 대표 3건"은
비교 판단이라 기사당 이진 판정으로는 K 를 보장할 수 없다(0건 또는 전부 통과 가능).
동기(실측): pytorch-kr 처럼 균질 품질 6~9건/일 소스에 최신순 캡을 쓰면 fetch 시각 기준
**고정 시간대 사각지대**가 생긴다 — 선별로 바꾸면 "그날의 대표 K건"이 된다.
"""
from __future__ import annotations

import json
import re
from collections.abc import Callable, Sequence

from .. import _debug
from .sources import FetchedArticle

# (candidates, k) -> 선택된 k건. 기본 구현 = latest_k(결정론); production = Haiku pick-K.
SelectFn = Callable[[Sequence[FetchedArticle], int], list[FetchedArticle]]

_SELECT_SYSTEM = (
    "You are a strict news curator for a daily AI briefing. From the numbered candidate "
    "articles, choose exactly {k} that are most valuable for a broad AI-practitioner "
    "audience. Priority: (1) major model/platform/release announcements, (2) widely "
    "applicable tools, frameworks, or security findings, (3) research with broad impact. "
    "Prefer topic diversity over near-duplicates. Answer with ONLY a JSON array of the "
    "chosen numbers, e.g. [1,4,7]."
)
_LEAD_CHARS = 300   # 후보당 제목+리드 300자 — 12건 × 300 ≈ 4K, 판별 충분·비용 유계
_IDX_RE = re.compile(r"\[[\d,\s]*\]")


def latest_k(articles: Sequence[FetchedArticle], k: int) -> list[FetchedArticle]:
    """피드 순서(최신순) 첫 K — 기존 캡 잘림과 동일(폴백·기본값의 결정론)."""
    return list(articles)[:k]


def llm_select(articles: Sequence[FetchedArticle], k: int,
               *, invoke: Callable[[str, str], str]) -> list[FetchedArticle]:
    """LLM 판정자로 K건 선별. invoke=(system,user)->str. 실패·모호 시 latest_k 폴백(non-silent warn).

    응답 = 1-기반 번호 JSON 배열. 범위 밖/중복 번호는 걸러내고, 유효 선택이 k 미만이면 폴백 —
    한 판정 실패가 그 소스의 수집 자체를 막으면 안 됨(relevance 와 같은 degrade 사다리).
    """
    arts = list(articles)
    if len(arts) <= k:
        return arts   # 후보가 캡 이하 — 판정 불필요(비용 0)
    user = "\n\n".join(f"{i}. {a.title}\n{(a.raw_text or '')[:_LEAD_CHARS]}"
                       for i, a in enumerate(arts, start=1))
    try:
        ans = invoke(_SELECT_SYSTEM.format(k=k), user) or ""
        m = _IDX_RE.search(ans)
        picked: list[FetchedArticle] = []
        for i in (json.loads(m.group(0)) if m else []):
            if isinstance(i, int) and 1 <= i <= len(arts) and arts[i - 1] not in picked:
                picked.append(arts[i - 1])
        if len(picked) >= k:
            return picked[:k]
        _debug.warn("curate select", f"판정 유효 선택 {len(picked)}<{k} (응답 {ans!r:.80}) → 최신순 폴백")
    except Exception as err:  # throttle/timeout/파싱 — 소스 수집을 막지 않는다
        _debug.warn("curate select", f"{type(err).__name__}: {err} → 최신순 폴백")
    return latest_k(arts, k)
