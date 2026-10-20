"""top_picks — 오늘의 핵심 3: 사용자가 받는 발행 카드 전체에서 K장을 골라 메일 맨 앞에 올린다.

검증을 통과한 카드의 **순서만** 바꾼다(내용 불변) → author/certifier 분리와 무관(relevance·selection 과 같은 논거).
판정 재료 = 사실층(제목·요약) + 메일 섹션 이름. 해석층(why)은 lens 별이라 넣으면 같은 카드 묶음도 사용자마다
결과가 달라져 run 내 공유(memo)가 깨진다. 실패하면 빈 목록 = 핵심 칸 없이 발송 — 최신순 대체는 하지 않는다
(앞 K장 = 늘 첫 섹션 카드가 "핵심"이 된다).

기준(2026-10-20 사용자 결정): ① 5대 기업(Anthropic·OpenAI·Amazon·Google·Meta)의 큰 발표 → ② 응용 AI·AI 에이전트.
★ LLM 은 기사마다 **라벨만** 붙인다(발표 주체·종류·중요도·사건 키). 5대 기업인지, 칸 배분(큰 발표 ≤2 · 응용 ≥1),
  같은 사건 제거는 **코드**가 한다(`assign_top`). 오프라인 실측(7일 × 2회): 한 번에 3장을 고르게 하면 표절 논란·
  과학자 성명을 "큰 발표"로 골랐고, 등급만 매기게 해도 MS·Deepseek·Z.ai 를 큰 발표로 넣었다 — 회사 목록 같은
  결정론적 조건은 LLM 에 맡기면 새고, 라벨 + 코드 판정은 7일 중 6일이 두 번 모두 같은 결과였다.
"""
from __future__ import annotations

import json
import re
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING

from . import _debug

if TYPE_CHECKING:
    from .gate import GatedCard

TOP_K = 3
TOP_MIN_CARDS = 6   # 발행 카드가 이보다 적으면 생략 — 짧은 메일(주말)에선 순서만 바뀌는 셈
MAX_BIG = 2         # 큰 발표 칸 상한 — 나머지는 응용 AI·에이전트(있으면 최소 1장)

# (발행 카드, k, 카드별 메일 섹션 이름) -> 고른 카드(k 이하, 표시 순서). production = Haiku(relevance_bedrock).
TopPickFn = Callable[[Sequence["GatedCard"], int, Sequence[str]], list["GatedCard"]]

# 5대 기업 — 라벨 org 를 소문자 포함 검사로 정규화(AWS→Amazon, DeepMind→Google). 여기 없는 회사는 큰 발표가 아니다.
BIG_ORGS = {"anthropic": "Anthropic", "openai": "OpenAI", "amazon": "Amazon", "aws": "Amazon",
            "google": "Google", "deepmind": "Google", "meta": "Meta"}

_LABEL_SYSTEM = (
    "You label candidate articles for the front page of a daily AI briefing read by AI practitioners. Each "
    "numbered candidate is tagged with its publisher section in brackets. For EVERY candidate output one object:\n"
    '{"n": <number>, "org": <the single organization whose OWN announcement this article is, or "" if it is '
    'not anyone\'s announcement>, "type": <one of "launch", "policy", "applied", "other">, '
    '"importance": <1-5 for an AI practitioner>, "event": <2-4 word key; articles about the same event or the '
    "same technical topic get the same key>}\n"
    'type "launch" = the org announces its own new model, product, platform, general availability or major '
    'feature. type "policy" = the org announces its own major policy, investment, partnership or organizational '
    "decision. A third-party model or product made available on a platform is the THIRD PARTY's launch (org = "
    "the third party). Criticism, lawsuits, court rulings, controversies, leaks, rumors, opinion and analyst "
    'rankings or awards are never launch or policy - use "other" (or "applied" if it fits). '
    'type "applied" = AI agents and applied AI: agent products and frameworks, agentic coding, agent protocols '
    "such as MCP, agent evaluation or safety, and building and running AI in production - deployment case "
    "studies, serving and inference engines, RAG and retrieval, on-device inference, cost and latency, security "
    "findings, engineering how-tos and tutorials.\n"
    "Answer with ONLY a JSON array of these objects."
)
_LEAD_CHARS = 300   # 후보당 요약 앞 300자 — 소스 선별(selection)과 같은 분량
_ARRAY_RE = re.compile(r"\[.*\]", re.S)


def big_org(org: str) -> str:
    """라벨의 org → 5대 기업 표준 이름, 아니면 ""."""
    o = (org or "").lower()
    return next((name for key, name in BIG_ORGS.items() if key in o), "")


def tier(label: dict) -> int:
    """1 = 5대 기업의 큰 발표(launch·policy) · 2 = 응용 AI·에이전트 · 3 = 그 밖."""
    if label.get("type") in ("launch", "policy") and big_org(label.get("org", "")):
        return 1
    return 2 if label.get("type") == "applied" else 3


def _importance(label: dict) -> int:
    try:
        return int(label.get("importance", 0))
    except (TypeError, ValueError):
        return 0


def assign_top(labels: Sequence[dict], sections: Sequence[str], k: int = TOP_K,
               max_big: int = MAX_BIG) -> list[int]:
    """라벨 → 고른 후보 번호(0-기반, 표시 순서 = 큰 발표 먼저·중요도순). 순수 함수(결정론).

    ① 큰 발표 ≤max_big ② 응용 AI·에이전트로 채움(있으면 최소 1장) ③ 모자라면 큰 발표 → 그 밖 순.
    같은 event 키는 1장 — 단 event 키는 LLM 이 같은 사건에도 매번 같게 주지 않는다(실측) → 결정론 보강 둘:
    - 큰 발표는 **회사당 1장** — 같은 날 한 회사의 글 둘은 대개 같은 발표(10-13: Gemini 4 Argon 로봇용·안전성 글이
      함께 뽑혀 GPT-6.1 이 밀림). 5대 기업 사이의 다양성도 된다.
    - 큰 발표가 아닌 칸(응용·그 밖)은 **메일 섹션당 1장** — 같은 연재물 1부·2부 같은 쏠림(10-18). 큰 발표는 섹션이
      같아도 된다(뉴스 칸이 두 회사의 발표를 함께 보도하는 날이 흔하다 — 10-14).
    """
    order = sorted(labels, key=lambda lb: (tier(lb), -_importance(lb), lb["n"]))
    picked: list[dict] = []
    events: set[str] = set()
    big_orgs: set[str] = set()
    small_sections: set[str] = set()

    def take(pool: list[dict], limit: int) -> None:
        for lb in pool:
            if len(picked) >= limit:
                return
            ev = str(lb.get("event") or "").strip().lower()
            sec = sections[lb["n"]] if lb["n"] < len(sections) else ""
            org = big_org(lb.get("org", "")) if tier(lb) == 1 else ""
            if lb in picked or (ev and ev in events) or (org and org in big_orgs):
                continue
            if tier(lb) != 1 and sec and sec in small_sections:
                continue
            picked.append(lb)
            if ev:
                events.add(ev)
            if org:
                big_orgs.add(org)
            if tier(lb) != 1 and sec:
                small_sections.add(sec)

    take([lb for lb in order if tier(lb) == 1], max_big)
    take([lb for lb in order if tier(lb) == 2], k)
    take(order, k)
    return [lb["n"] for lb in sorted(picked, key=lambda lb: (tier(lb), -_importance(lb), lb["n"]))]


def _parse_labels(answer: str, n_cards: int) -> list[dict]:
    """LLM 응답 → 유효 라벨(n 은 0-기반으로 바꾼다). 번호 밖·중복은 버린다."""
    m = _ARRAY_RE.search(answer or "")
    out: dict[int, dict] = {}
    for lb in (json.loads(m.group(0)) if m else []):
        if not isinstance(lb, dict):
            continue
        try:
            n = int(lb.get("n")) - 1
        except (TypeError, ValueError):
            continue
        if 0 <= n < n_cards and n not in out:
            out[n] = {**lb, "n": n}
    return list(out.values())


def llm_top_picks(cards: Sequence[GatedCard], k: int, sections: Sequence[str] = (),
                  *, invoke: Callable[[str, str], str]) -> list[GatedCard]:
    """LLM 라벨 + 코드 배분으로 K장. invoke=(system,user)->str. 실패·K장 미달이면 [](non-silent warn)."""
    cards = list(cards)
    secs = list(sections) + [""] * (len(cards) - len(sections))
    user = "\n\n".join(f"{i}. {f'[{s}] ' if s else ''}{g.card.headline}\n{(g.card.summary or '')[:_LEAD_CHARS]}"
                       for i, (g, s) in enumerate(zip(cards, secs), start=1))
    try:
        labels = _parse_labels(invoke(_LABEL_SYSTEM, user), len(cards))
        idx = assign_top(labels, secs, k)
        if len(idx) < k:
            raise ValueError(f"유효 선택 {len(idx)}<{k} (라벨 {len(labels)}/{len(cards)})")
    except Exception as err:  # throttle/timeout/파싱 — 핵심 칸만 빠지고 메일은 나간다
        _debug.warn("top picks", f"{type(err).__name__}: {err} → 핵심 칸 생략")
        return []
    by_n = {lb["n"]: lb for lb in labels}
    # 고른 결과 한 줄(CloudWatch) — 기준이 의도대로 도는지 사후 검토용(예전엔 선정이 어디에도 남지 않았다)
    _debug.warn("top picks 선정", " | ".join(
        f"p{tier(by_n[i])} {big_org(by_n[i].get('org', '')) or by_n[i].get('type', '')}: {cards[i].card.headline[:50]}"
        for i in idx))
    return [cards[i] for i in idx]


def top_source_ids(cards: Sequence[GatedCard], top_pick_fn: TopPickFn | None,
                   memo: dict[tuple[str, ...], tuple[str, ...]],
                   sections: dict[str, str] | None = None) -> tuple[str, ...]:
    """pipeline 용 — 발행 카드가 TOP_MIN_CARDS 이상일 때만 판정해 고른 카드의 source_id(판정 순서)를 돌려준다.

    sections = source_id → 메일 섹션 이름(catalog category). 판정 재료로 넘긴다(공식 채널인지 보도인지 구분).
    같은 카드 묶음을 받는 사용자들은 memo 로 판정 1회를 공유한다(재료가 사실층·섹션이라 lens 무관).
    주입된 함수가 예외를 던져도 () — 브리핑을 막지 않는다(fail-open, 카드 격리와 같은 원칙).
    """
    pub = [g for g in cards if g.decision == "PUBLISH"]
    if top_pick_fn is None or len(pub) < TOP_MIN_CARDS:
        return ()
    key = tuple(g.card.source_id for g in pub)
    if key not in memo:
        secs = [(sections or {}).get(g.card.source_id, "") for g in pub]
        try:
            memo[key] = tuple(g.card.source_id for g in top_pick_fn(pub, TOP_K, secs))[:TOP_K]
        except Exception as err:  # noqa: BLE001 — 핵심 칸은 보조 장치
            _debug.warn("top picks", f"{type(err).__name__}: {err} → 핵심 칸 생략")
            memo[key] = ()
    return memo[key]
