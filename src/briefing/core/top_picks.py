"""top_picks — 라벨 1회로 **오늘의 핵심 3 + 분야 밴드**: 보이는 카드(PUBLISH+⚠)마다 LLM 이 라벨을 붙이고, 선택·분야는 코드.

검증을 통과한 카드의 **순서·묶음만** 바꾼다(내용 불변) → author/certifier 분리와 무관(relevance·selection 과 같은 논거).
판정 재료 = 사실층(제목·요약 300자) + 메일 섹션 이름(카탈로그 category). 해석층(why)은 lens 별이라 넣으면 같은 카드
묶음도 사용자마다 결과가 달라져 run 내 공유(memo)가 깨진다.

핵심 3 기준(2026-10-20 사용자 결정): ① 5대 기업(Anthropic·OpenAI·Amazon·Google·Meta)의 큰 발표 → ② 응용 AI·AI 에이전트.
★ LLM 은 기사마다 **라벨만** 붙인다(발표 주체·종류·중요도·사건 키·**분야**). 5대 기업인지, 칸 배분(큰 발표 ≤2 · 응용 ≥1),
  같은 사건 제거는 **코드**가 한다(`assign_top`). 오프라인 실측(7일 × 2회): 한 번에 3장을 고르게 하면 표절 논란·
  과학자 성명을 "큰 발표"로 골랐고, 등급만 매기게 해도 MS·Deepseek·Z.ai 를 큰 발표로 넣었다 — 회사 목록 같은
  결정론적 조건은 LLM 에 맡기면 새고, 라벨 + 코드 판정은 7일 중 6일이 두 번 모두 같은 결과였다.
★ 2026-10-30 `launch` 정의 좁힘(새 모델·새 제품/서비스·플랫폼 GA 만; 점진 기능·통합·SDK/스킬 추가·튜토리얼·엔지니어링 글은
  applied). 왜: 10-20~29 실발송에서 1티어(큰 발표 칸)의 약 1/4 이 how-to·기능 글(TorchTPU 통합·IAM Helper·AWS Batch 할당량)
  — "major feature" 문구가 기능 소개를 launch 로 끌어들였다. 실측(10일 × Sonnet 5.5 재생, `docs/work_note/Oct-2026/
  261030-improve-today-briefing/`): 1티어 후보 58→33장(−43%), 플래그십(Duet·Genie 4·GPT-6.1 Terra·Gemini 4 Carbon·S-1·GSA)
  전부 유지, 분야 골든 89.3→87.8%(같은 날 기준선 대비 −1.5pt, 불일치 12건 공유 = 잡음). **기각(재제안 금지):** ① 1티어
  importance 하한 — 점수가 3~4 에 뭉쳐 하한 4 는 정당한 소형 발표(Polly·AI for Science)를 떨구고 오분류 4점(연구 보도)은
  통과시키며 주말엔 핵심 3 자체가 생략됨 ② "연구 결과→other" 문구 — 응용 칸의 연구 픽(전문가 판단·신약)을 밀어내고 10-24
  OpenAI 연구 보도(policy 오분류)는 못 고침 ③ importance 앵커 — 점수가 여전히 들쭉날쭉(Terra 5→4). 잔존 1건/10일(연구 보도가
  policy)은 수용.
★ 2026-10-30 사용자 우선순위 **① 5대 기업 큰 발표 → ② AI Agents → ③ Applied AI**(엄격, importance 는 등급 안에서만) + **Arel**
  (큰 발표는 그날 최고 AI Agents 후보 importance 이상일 때만 1순위, 미달이면 Agents 다음) — `tier`·`ranks`·`assign_top` 참조.
  10일 시뮬: 엄격 순서로 5일 변화(Applied AI 는 큰 발표 2장 미만인 날만 핵심 3 진입 — 사용자 수용), Arel 은 1일(10-25 순서).
  중간 단계였던 #2b(2티어 = Agents·Applied AI 를 importance 순으로 섞음, `422df5b`)는 이 규칙으로 대체.

분야 밴드(2026-10-24 사용자 결정, `docs/superpowers/specs/2026-10-24-topic-grouping-design.md`):
- 같은 라벨 호출에 `area`(공용 `areas.AREAS` 중 하나, **정확 일치**)를 더한다 — 추가 호출 0. 입력은 ⚠(QUARANTINE)
  카드까지 보이는 카드 전부(메일에 실리므로 분야가 필요); 핵심 3 선택은 PUBLISH 라벨만 본다(N5).
- 라벨이 **완전할 때만** 쓴다(카드마다 1개·area 유효). 불완전·예외면 같은 입력으로 1회 재시도, 그래도 안 되면
  `LabelIncomplete` → 호출자는 핵심 3·분야 밴드를 함께 생략(메일은 평평). 부분 라벨을 채워 넣지 않는다.
- 분야는 **캐시하지 않는다**(run 당 라벨, 같은 카드 묶음을 받는 사용자끼리 memo 공유) — 2026-07-27 해석층 캐시가 새 규칙을
  우회한 사고의 재발 방지.
"""
from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping, Sequence
from typing import TYPE_CHECKING

from . import _debug
from .areas import AREA_DEFINITIONS, AREAS

if TYPE_CHECKING:
    from .gate import GatedCard

TOP_K = 3
TOP_MIN_CARDS = 6   # 발행 카드가 이보다 적으면 라벨 호출 생략 — 짧은 메일(주말)에선 순서만 바뀌는 셈(9/20~ 34회 최소 10장)
MAX_BIG = 2         # 큰 발표 칸 상한 — 나머지는 응용 AI·에이전트(있으면 최소 1장)
AGENTS_AREA, APPLIED_AREA = "AI Agents", "Applied AI"   # 2026-10-30 사용자 우선순위: 큰 발표 → AI Agents → Applied AI(tier 참조)
assert {AGENTS_AREA, APPLIED_AREA} <= set(AREAS)
DEMOTED_BIG = 2.5   # Arel: 큰 발표인데 그날 최고 AI Agents 후보보다 importance 가 낮음 → Agents 다음·Applied AI 앞(ranks 참조)

# (보이는 카드, 카드별 메일 섹션 이름) -> 완전한 라벨 목록(카드마다 {n(0-기반), org, type, importance, event, area}).
# 불완전·실패는 예외(LabelIncomplete 등). production = relevance_bedrock.make_bedrock_labels(LABEL_MODEL_ID).
LabelFn = Callable[[Sequence["GatedCard"], Sequence[str]], list[dict]]


class LabelIncomplete(ValueError):
    """라벨 호출이 재시도 뒤에도 완전하지 않다(사유 문자열 포함) — 호출자는 핵심 3·분야 밴드를 생략한다."""


# 5대 기업 — 라벨 org 를 소문자 포함 검사로 정규화(AWS→Amazon, DeepMind→Google). 여기 없는 회사는 큰 발표가 아니다.
BIG_ORGS = {"anthropic": "Anthropic", "openai": "OpenAI", "amazon": "Amazon", "aws": "Amazon",
            "google": "Google", "deepmind": "Google", "meta": "Meta"}

_LABEL_SYSTEM = (
    "You label candidate articles for the front page of a daily AI briefing read by AI practitioners. Each "
    "numbered candidate is tagged with its publisher section in brackets. For EVERY candidate output one object:\n"
    '{"n": <number>, "org": <the single organization whose OWN announcement this article is, or "" if it is '
    'not anyone\'s announcement>, "type": <one of "launch", "policy", "applied", "other">, '
    '"importance": <1-5 for an AI practitioner>, "event": <2-4 word key; articles about the same event or the '
    'same technical topic get the same key>, "area": <exactly one of: ' + ", ".join(AREAS) + ">}\n"
    'type "launch" = the org announces its own NEW model, NEW product or service, or general availability of a '
    'platform - something an AI practitioner would call headline news. Incremental features, integrations, '
    'SDK/skill/tool additions, regional expansions, tutorials, how-tos and engineering write-ups are NOT launch - '
    'use "applied" (or "other"). '
    'type "policy" = the org announces its own major policy, investment, partnership or organizational '
    "decision. A third-party model or product made available on a platform is the THIRD PARTY's launch (org = "
    "the third party). Criticism, lawsuits, court rulings, controversies, leaks, rumors, opinion and analyst "
    'rankings or awards are never launch or policy - use "other" (or "applied" if it fits). '
    'type "applied" = AI agents and applied AI: agent products and frameworks, agentic coding, agent protocols '
    "such as MCP, agent evaluation or safety, and building and running AI in production - deployment case "
    "studies, serving and inference engines, RAG and retrieval, on-device inference, cost and latency, security "
    "findings, engineering how-tos and tutorials.\n"
    + AREA_DEFINITIONS + "\n"
    "Answer with ONLY a JSON array of these objects, one per candidate, using the area names verbatim."
)
_LEAD_CHARS = 300   # 후보당 요약 앞 300자 — 소스 선별(selection)과 같은 분량
_ARRAY_RE = re.compile(r"\[.*\]", re.S)


def big_org(org: str) -> str:
    """라벨의 org → 5대 기업 표준 이름, 아니면 ""."""
    o = (org or "").lower()
    return next((name for key, name in BIG_ORGS.items() if key in o), "")


def tier(label: dict) -> int:
    """등급: 1 = 5대 기업의 큰 발표(launch·policy) · 2 = AI Agents(type applied ∧ area AI Agents) · 3 = Applied AI
    (type applied ∧ area Applied AI) · 4 = 그 밖(비5대기업 launch, other, 다른 분야의 applied — 인프라 how-to 등).

    ★ 2026-10-30 사용자 우선순위 "① 5대 기업 큰 발표 → ② AI Agents → ③ Applied AI" 를 등급으로 — importance 는 같은 등급
    안에서만 쓴다(10-20~29 시뮬: Applied AI 는 큰 발표가 2장 미만인 날에만 핵심 3 에 들어옴 — 사용자가 수용). 그 전(#2b)엔
    2티어가 Agents·Applied AI 를 importance 순으로 섞었고, 그 전엔 type applied 면 분야 무관이라 Inference & Hardware how-to 가
    응용 칸을 차지했다(10-29 "Nemotron on EKS"). 선호 분야 applied 가 없으면 4티어에서 채운다(`assign_top` ④).
    """
    if label.get("type") in ("launch", "policy") and big_org(label.get("org", "")):
        return 1
    if label.get("type") == "applied":
        if label.get("area") == AGENTS_AREA:
            return 2
        if label.get("area") == APPLIED_AREA:
            return 3
    return 4


def ranks(labels: Sequence[dict]) -> dict[int, float]:
    """라벨 → n → 선정 등급(1 · 2 · DEMOTED_BIG=2.5 · 3 · 4). 순수 함수.

    ★ Arel(2026-10-30, 사용자 "큰 발표는 importance 를 고려"): 큰 발표는 **그날 최고 AI Agents 후보의 importance 이상**일 때만
    1순위(동점은 큰 발표). 미달이면 2.5 — Agents 다음·Applied AI 앞. 절대 문턱(≥4) 대신 상대 비교인 이유: importance 는 LLM 이
    같은 호출에서 매긴 1~5 라 3↔4 로 흔들리고 3 에 뭉친다(10일 196장 중 92장). 절대 문턱은 10-29 AI for Science(3)·10-26 IAM
    Helper(3)를 빼고 imp 2 Agents how-to 를 넣었다(실측). 같은 호출 안의 점수끼리 비교하면 그 영향이 작고, 10일 중 1일(10-25:
    Open Responses 3 < "one agent beats many subagents" 4)만 바뀐다.
    """
    best_agents = max((_importance(lb) for lb in labels if tier(lb) == 2), default=0)
    return {lb["n"]: (DEMOTED_BIG if tier(lb) == 1 and _importance(lb) < best_agents else float(tier(lb)))
            for lb in labels}


def _importance(label: dict) -> int:
    try:
        return int(label.get("importance", 0))
    except (TypeError, ValueError):
        return 0


def assign_top(labels: Sequence[dict], sections: Sequence[str], k: int = TOP_K,
               max_big: int = MAX_BIG) -> list[int]:
    """라벨 → 고른 후보 번호(0-기반, 표시 순서 = 등급순·중요도순). 순수 함수(결정론).

    ① 1순위 큰 발표(`ranks`) ≤max_big ② AI Agents ②.5 강등된 큰 발표(큰 발표 합계 ≤max_big) ③ Applied AI
    ④ 모자라면 잔여(큰 발표 잔여 → 그 밖, 상한 없음 — 10-20 이래 폴백). 2026-10-30 사용자 우선순위 + Arel.
    같은 event 키는 1장 — 단 event 키는 LLM 이 같은 사건에도 매번 같게 주지 않는다(실측) → 결정론 보강 둘:
    - 큰 발표는 **회사당 1장** — 같은 날 한 회사의 글 둘은 대개 같은 발표(10-13: Gemini 4 Argon 로봇용·안전성 글이
      함께 뽑혀 GPT-6.1 이 밀림). 5대 기업 사이의 다양성도 된다.
    - 큰 발표가 아닌 칸(응용·그 밖)은 **메일 섹션당 1장** — 같은 연재물 1부·2부 같은 쏠림(10-18). 큰 발표는 섹션이
      같아도 된다(뉴스 칸이 두 회사의 발표를 함께 보도하는 날이 흔하다 — 10-14).
    `sections` 는 라벨 `n` 이 가리키는 **전체 카드 목록** 기준(⚠ 카드가 섞여 있어도 인덱스를 다시 매기지 않는다).
    """
    rank = ranks(labels)
    key = lambda lb: (rank[lb["n"]], -_importance(lb), lb["n"])  # noqa: E731
    order = sorted(labels, key=key)
    picked: list[dict] = []
    events: set[str] = set()
    big_orgs: set[str] = set()
    small_sections: set[str] = set()
    n_big = 0

    def take(pool: list[dict], limit: int, *, big_cap: int | None = None) -> None:
        nonlocal n_big
        for lb in pool:
            if len(picked) >= limit:
                return
            is_big = tier(lb) == 1
            ev = str(lb.get("event") or "").strip().lower()
            sec = sections[lb["n"]] if lb["n"] < len(sections) else ""
            org = big_org(lb.get("org", "")) if is_big else ""
            if lb in picked or (ev and ev in events) or (org and org in big_orgs):
                continue
            if not is_big and sec and sec in small_sections:
                continue
            if is_big and big_cap is not None and n_big >= big_cap:
                continue
            picked.append(lb)
            if ev:
                events.add(ev)
            if org:
                big_orgs.add(org)
            if is_big:
                n_big += 1
            elif sec:
                small_sections.add(sec)

    take([lb for lb in order if rank[lb["n"]] == 1], k, big_cap=max_big)            # ① 1순위 큰 발표 ≤max_big
    take([lb for lb in order if rank[lb["n"]] == 2], k)                             # ② AI Agents
    take([lb for lb in order if rank[lb["n"]] == DEMOTED_BIG], k, big_cap=max_big)  # ②.5 강등 큰 발표(합계 ≤max_big)
    take([lb for lb in order if rank[lb["n"]] == 3], k)                             # ③ Applied AI
    take(order, k)                                                                  # ④ 잔여(큰 발표 잔여 → 그 밖)
    return [lb["n"] for lb in sorted(picked, key=key)]


def _parse_labels(answer: str, n_cards: int) -> list[dict]:
    """LLM 응답 → 유효 라벨(n 은 0-기반으로 바꾼다). 번호 밖·중복은 버린다. area 는 그대로 통과(검사는 labels_complete)."""
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


def labels_complete(labels: Sequence[dict], n_cards: int) -> str:
    """완전하면 "", 아니면 사유. 완전 = 카드마다 라벨 1개(n 중복·누락 없음) + area 가 AREAS 와 **정확 일치**.

    정규화(대소문자·공백)는 하지 않는다 — 근사 일치를 받으면 모델이 목록 밖 이름을 발명해도 통과한다(결정론 우선).
    """
    ns = [lb.get("n") for lb in labels]
    if len(set(ns)) != len(ns):
        return f"n 중복 {len(ns) - len(set(ns))}건"
    missing = sorted(set(range(n_cards)) - set(ns))
    if missing:
        return f"라벨 {len(labels)}/{n_cards} (누락 {missing[:5]})"
    bad = [lb["n"] for lb in labels if lb.get("area") not in AREAS]
    if bad:
        return f"area 미배정 {len(bad)}/{n_cards} (카드 {bad[:5]})"
    return ""


def _prompt_user(cards: Sequence[GatedCard], secs: Sequence[str]) -> str:
    return "\n\n".join(f"{i}. {f'[{s}] ' if s else ''}{g.card.headline}\n{(g.card.summary or '')[:_LEAD_CHARS]}"
                       for i, (g, s) in enumerate(zip(cards, secs), start=1))


def llm_labels(cards: Sequence[GatedCard], sections: Sequence[str] = (),
               *, invoke: Callable[[str, str], str]) -> list[dict]:
    """LLM 라벨(완전한 목록, n 오름차순). invoke=(system,user)->str. 불완전·예외면 **같은 입력으로 1회 재시도**.

    재시도 사실은 dprint(디버그)만 — 2차에 성공하면 조용히 끝난다. 2차도 불완전하면 LabelIncomplete(사유).
    """
    cards = list(cards)
    secs = list(sections) + [""] * (len(cards) - len(sections))
    user = _prompt_user(cards, secs)
    why = ""
    for attempt in (1, 2):
        try:
            labels = _parse_labels(invoke(_LABEL_SYSTEM, user), len(cards))
            why = labels_complete(labels, len(cards))
            if not why:
                return sorted(labels, key=lambda lb: lb["n"])
        except Exception as err:  # noqa: BLE001 — throttle/timeout/파싱: 재시도 1회 뒤 호출자에게
            why = f"{type(err).__name__}: {err}"
        if attempt == 1:
            _debug.dprint("areas 라벨", f"1차 불완전({why}) → 같은 입력으로 재시도", "yellow")
    raise LabelIncomplete(why)


def _distribution(cards: Sequence[GatedCard], labels: Sequence[dict]) -> str:
    """CloudWatch 한 줄 — 분야마다 장수와 제목 앞 40자(사후 점검 원자료, 스펙 §6)."""
    by_area: dict[str, list[str]] = {a: [] for a in AREAS}
    for lb in labels:
        by_area.setdefault(lb["area"], []).append(cards[lb["n"]].card.headline[:40])
    return " | ".join(f"{a} {len(ts)}: " + " · ".join(ts) for a, ts in by_area.items() if ts)


def label_cards(cards: Sequence[GatedCard], label_fn: LabelFn | None,
                memo: dict[tuple[str, ...], list[dict] | None],
                source_categories: Mapping[str, str] | None = None) -> list[dict] | None:
    """pipeline 용 — 보이는 카드 전부에 라벨(run 내 같은 묶음 사용자끼리 memo 1회). 실패·게이트 미만 = None.

    게이트 = PUBLISH 카드 ≥ TOP_MIN_CARDS(현행 핵심 3 규칙; 9/20~ 34회 발송 중 6장 미만 0회라 분리하지 않는다).
    memo 키 = 보이는 카드(PUBLISH+⚠) source_id 튜플. 프로필이 달라 묶음이 다르면 호출이 따로 돌고 같은 기사가
    사용자마다 다른 칸에 갈 수 있다 — 수용(2026-10-24 결정). 예외는 warn 후 None(fail-open — 메일은 평평하게 나간다).
    """
    cards = list(cards)
    if label_fn is None or sum(1 for g in cards if g.decision == "PUBLISH") < TOP_MIN_CARDS:
        return None
    key = tuple(g.card.source_id for g in cards)
    if key not in memo:
        secs = [(source_categories or {}).get(g.card.source_id, "") for g in cards]
        try:
            labels = list(label_fn(cards, secs))
            if why := labels_complete(labels, len(cards)):   # 주입 함수가 불완전한 목록을 돌려줘도 밴드를 그리지 않는다
                raise LabelIncomplete(why)
            memo[key] = labels
            _debug.warn("areas 라벨", _distribution(cards, labels), limit=4000)   # 24장 × 40자가 400자 절단에 잘리지 않게(표본 점검 원자료)
        except Exception as err:  # noqa: BLE001 — 라벨은 보조 장치: 실패해도 브리핑은 나간다(핵심 3·밴드만 생략)
            _debug.warn("areas 라벨", f"{type(err).__name__}: {err} → 핵심 3·분야 밴드 생략(평평)")
            memo[key] = None
    return memo[key]


def pick_top(cards: Sequence[GatedCard], labels: Sequence[dict], sections: Sequence[str],
             k: int = TOP_K) -> tuple[str, ...]:
    """라벨 → 오늘의 핵심 K장의 source_id(표시 순서). PUBLISH 카드의 라벨만 후보(⚠ 는 핵심에 안 올림 — N5).

    `sections` 는 전체 카드 기준(라벨 n 과 같은 인덱스). 유효 선택 < k 면 warn 후 ()(앞 K장 대체 금지).
    """
    cards = list(cards)
    secs = list(sections) + [""] * (len(cards) - len(sections))
    pub = [lb for lb in labels if 0 <= lb["n"] < len(cards) and cards[lb["n"]].decision == "PUBLISH"]
    idx = assign_top(pub, secs, k)
    if len(idx) < k:
        _debug.warn("top picks", f"유효 선택 {len(idx)}<{k} (라벨 {len(labels)}/{len(cards)}) → 핵심 칸 생략")
        return ()
    by_n = {lb["n"]: lb for lb in labels}
    rank = ranks(pub)
    # 고른 결과 한 줄(CloudWatch) — 기준이 의도대로 도는지 사후 검토용(예전엔 선정이 어디에도 남지 않았다).
    # p1 큰 발표 · p1↓ 강등된 큰 발표(Arel) · p2 AI Agents · p3 Applied AI · p4 그 밖
    _debug.warn("top picks 선정", " | ".join(
        f"{'p1↓' if rank[i] == DEMOTED_BIG else f'p{int(rank[i])}'} "
        f"{big_org(by_n[i].get('org', '')) or by_n[i].get('type', '')}: {cards[i].card.headline[:50]}"
        for i in idx))
    return tuple(cards[i].card.source_id for i in idx)


def areas_of(cards: Sequence[GatedCard], labels: Sequence[dict]) -> dict[str, str]:
    """라벨 → source_id → 분야(render 의 `card_areas`). 보이는 카드 전부(⚠ 포함)."""
    cards = list(cards)
    return {cards[lb["n"]].card.source_id: lb["area"] for lb in labels if 0 <= lb["n"] < len(cards)}
