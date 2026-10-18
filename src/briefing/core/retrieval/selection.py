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

# 1순위 = AI 에이전트 + Applied AI(정의를 풀어 씀 — 단어만으론 Haiku 가 뜻을 추측). 2026-10-18 실측(같은 풀
# 3~5회): 에이전트·Applied AI 를 따로 두 단계로 나누면 큰 보안 사고 기사를 빼고 흔들렸다. "대형 발표는 예외"
# 문장은 넓게 쓰든 좁게 쓰든 큰 뉴스 쪽으로 기울어 불안정해져서 기각.
_SELECT_SYSTEM = (
    "You are a strict news curator for a daily AI briefing read by AI practitioners who build and run AI "
    "systems. From the numbered candidate articles, choose exactly {k} that such a reader would most regret "
    "missing. Priority: (1) AI agents — agent products and frameworks, agentic coding, agent protocols such as "
    "MCP, and agent evaluation or safety, and applied AI — building and running AI in production: deployment "
    "case studies, serving and inference engines, RAG and retrieval, local or on-device inference, cost and "
    "latency trade-offs, security findings, and engineering how-tos; (2) major model or platform releases; "
    "(3) research with broad practical impact. Rank lower: opinion pieces and essays, funding or valuation "
    "news, executive quotes, and narrow academic results with no practical consequence. Never pick two "
    "articles about the same event; prefer topic diversity. Answer with ONLY a JSON array of the chosen "
    "numbers, e.g. [1,4,7]."
)
_LEAD_CHARS = 300   # 후보당 제목+리드 300자 — 12건 × 300 ≈ 4K, 판별 충분·비용 유계
_IDX_RE = re.compile(r"\[[\d,\s]*\]")


def latest_k(articles: Sequence[FetchedArticle], k: int) -> list[FetchedArticle]:
    """피드 순서(최신순) 첫 K — 기존 캡 잘림과 동일(폴백·기본값의 결정론)."""
    return list(articles)[:k]


def pick_indices(items: Sequence[tuple[str, str]], k: int,
                 *, invoke: Callable[[str, str], str]) -> list[int]:
    """(제목, 본문) 번호 목록에서 P2b 기준으로 K개 — 0-기반 인덱스(응답 순서). 판정 공통부.

    응답 = 1-기반 번호 JSON 배열. 범위 밖/중복 번호는 걸러내고, 유효 선택이 k 미만이면 ValueError.
    invoke 예외도 그대로 올린다 — 폴백은 호출자 몫(소스 선별 = 최신순, 오늘의 핵심 3 = 칸 생략).
    """
    user = "\n\n".join(f"{i}. {title}\n{(text or '')[:_LEAD_CHARS]}"
                       for i, (title, text) in enumerate(items, start=1))
    ans = invoke(_SELECT_SYSTEM.format(k=k), user) or ""
    m = _IDX_RE.search(ans)
    picked: list[int] = []
    for i in (json.loads(m.group(0)) if m else []):
        if isinstance(i, int) and 1 <= i <= len(items) and i - 1 not in picked:
            picked.append(i - 1)
    if len(picked) < k:
        raise ValueError(f"판정 유효 선택 {len(picked)}<{k} (응답 {ans!r:.80})")
    return picked[:k]


def llm_select(articles: Sequence[FetchedArticle], k: int,
               *, invoke: Callable[[str, str], str]) -> list[FetchedArticle]:
    """LLM 판정자로 K건 선별. invoke=(system,user)->str. 실패·모호 시 latest_k 폴백(non-silent warn).

    한 판정 실패가 그 소스의 수집 자체를 막으면 안 됨(relevance 와 같은 degrade 사다리).
    """
    arts = list(articles)
    if len(arts) <= k:
        return arts   # 후보가 캡 이하 — 판정 불필요(비용 0)
    try:
        return [arts[i] for i in pick_indices([(a.title, a.raw_text) for a in arts], k, invoke=invoke)]
    except Exception as err:  # throttle/timeout/파싱/유효 선택 부족 — 소스 수집을 막지 않는다
        _debug.warn("curate select", f"{type(err).__name__}: {err} → 최신순 폴백")
    return latest_k(arts, k)
