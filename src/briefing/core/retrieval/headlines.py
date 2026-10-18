"""headlines — 제목·링크 전용 소스: 본문을 가져오지 않고, AI 판정자에는 **제목만** 넘긴다.

왜(2026-10-17 적법성 점검): AI타임스 기사마다 "무단전재 및 재배포, AI학습 및 활용 금지" 고지가 붙어 있다.
본문 수집 + LLM 요약(카드)은 이 고지와 정면 충돌 → 카드 경로(curate)에서 뺀다. 대신 기계가 읽으라고 공개한
RSS 의 제목·링크·발행시각만 쓴다. 피드 요약문은 본문 앞 300자를 그대로 옮긴 것이라 싣지 않는다(전재).
Haiku 관련성 판정·선별은 제목만 받고 출력은 선택 여부뿐 — 메일엔 원제목을 그대로 싣는다(재작성·번역·요약 없음).
판단 근거: docs/work_note/Oct-2026/261017-find-new-articles/source-candidates.md

검증 카드가 아니므로 gate/certifier 를 거치지 않는다 → render 가 "요약·검증 없음" 칸으로 카드와 분리한다.
칸 안은 분야(HEADLINE_AREAS)로 묶는다 — 선별이 끝난 제목만 Haiku 가 닫힌 분야 목록에 배정(별도 콜, 제목만).
"""
from __future__ import annotations

import calendar
import json
import re
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timezone

from .. import _debug
from . import robots
from . import sources as src
from .relevance import RelevanceFn, is_ai_relevant
from .selection import latest_k

_DEFAULT_MAX_HEADLINES = 8   # 소스당 헤드라인 상한(카탈로그 max_items 가 덮어씀)
_POOL = 50                   # 후보 상한 = 피드 전체(AI타임스 50건) — 선별은 집합당 1콜이라 넓혀도 비용 동일

# (source, window_hours) -> 후보. 기본 = 피드 전용 수집(fetch_headline_feed). 테스트는 fake 주입.
HeadlineFetchFn = Callable[[src.Source, int], Sequence[src.FetchedArticle]]
# (candidates, k, covered_titles) -> 상한 k **이하**의 (기사, 그룹). covered = 이번 run 카드 소스의 기사 제목(같은 소식
# 제외용). 그룹 = "해외" | "국내" | ""(모름 — 폴백·구형 응답).
HeadlineSelectFn = Callable[[Sequence[src.FetchedArticle], int, Sequence[str]], list[tuple[src.FetchedArticle, str]]]
# titles -> 제목마다 분야(같은 길이, HEADLINE_AREAS 중 하나). 실패 = [] → 분야 없음(render 가 소제목 없는 한 목록).
HeadlineAreaFn = Callable[[Sequence[str]], list[str]]

# 헤드라인 칸 분야(2026-10-18 사용자 결정) — 닫힌 목록·영문 정본(섹션 이름과 같은 원칙). 순서 = 메일 소제목 순서
# (독자 우선순위: 에이전트 먼저). 지역(국내/해외)은 화면에 내지 않는다(소제목·표시 없음 — 2026-10-18 사용자 결정).
HEADLINE_AREAS = ("AI Agents", "Models & Releases", "Research", "Policy & Security", "Industry & Business")

_HEADLINE_SELECT_SYSTEM = (
    "You curate the headline list at the top of a Korean daily AI briefing email. The candidates are Korean "
    "news headlines (titles only). Choose UP TO {k} of them, in this priority order:\n"
    "1) The most important AI news for AI practitioners — major model/platform/product releases, widely used "
    "tools, significant AI policy, security incidents, and AI industry moves.\n"
    "2) Korean domestic AI news — Korean companies, Korean government AI policy, Korean research.\n"
    "Exclude anything that is not about AI (energy, local administration, general consumer gadgets, stock "
    "market roundups, opinion columns, cartoons) even if that leaves fewer than {k}. Prefer topic diversity; "
    "never pick two headlines about the same event. Split your picks into overseas news and Korean domestic news "
    "(domestic = the main actor is a Korean company, the Korean government or a Korean research group; a foreign "
    "company adding Korean-language support or launching in Korea is overseas). Think briefly, then end "
    "your answer with ONE JSON object on the last line, at most {k} numbers in total, each list in priority order: "
    '{{"global": [3,7], "domestic": [1]}}.'
)
# ★ "JSON 만" 지시는 47건 중 15건 선별에서 지켜지지 않는다(2026-10-17 실측): thinking 을 꺼도 텍스트로 추론하다
#   토큰 상한에서 잘려 3회 중 2회 파싱 불가 → 폴백. 짧은 추론 + 마지막 줄 배열로 바꾸자 3/3 성공·비AI 0·국내 3~4건.
# ★ 카드 중복 제거는 **별도 콜**이다(2026-10-17 실측): 선별 프롬프트에 "카드와 같은 소식 제외"를 넣으면 1순위
#   (실무 핵심)에 밀려 무시되고(ChatGPT 크롬 기사가 1위로 선택), 한 콜에 "covered 먼저 표시"를 시키면 비AI·무관
#   기사까지 covered 로 몰아 넣는다. 교차 언어 사건 대조만 시키고 짧게 추론하게 하면 3회 연속 정확히 3건.
_DEDUP_SYSTEM = (
    "You match news headlines across languages. Below are numbered Korean candidate headlines and a list of "
    "reference titles (often English). Find candidates that report the SAME specific event as some reference "
    "title: the same company or organization AND the same announcement, release, incident or report. "
    "Different events about the same company do NOT match. If unsure, do not include it. Think briefly, then "
    "end your answer with a JSON array of the matching candidate numbers on the last line, e.g. [2,9] or []."
)
# ★ 선별 프롬프트를 고치지 않고 **별도 콜**로 둔 이유: 선별(위)의 10-17 실측(파싱 3/3·비AI 0·국내 3~4건)을 그대로 유지.
#   2026-10-18 실측(Haiku 5.5, 오늘 선별 11건 × 3회): 전부 배정, 7건 매회 같은 분야, 4건은 경계에서 흔들림
#   (물리 문제 풀이=Research/Models, 에이전트 무단 침입=Agents/Security 등 — 어느 쪽도 틀리지 않은 경계).
_AREA_SYSTEM = (
    "You group Korean AI news headlines (titles only) by area for a daily AI briefing read by AI practitioners. "
    "Assign EVERY numbered headline to exactly one area from this closed list: " + ", ".join(HEADLINE_AREAS) + ". "
    "AI Agents = agent products and frameworks, agentic coding, agents acting on browsers or computers, agent "
    "protocols, agent incidents. Models & Releases = new or updated models and AI products. Research = studies, "
    "benchmarks, scientific results. Policy & Security = laws, regulation, government action, security incidents "
    "and espionage. Industry & Business = funding, credit, deals, datacenters, chips, markets. Think briefly, then "
    'end with ONE JSON object on the last line mapping area to numbers, e.g. {"AI Agents": [2], "Research": [1]}.'
)
_IDX_RE = re.compile(r"\[[\d,\s]*\]")


@dataclass(frozen=True)
class Headline:
    source_key: str
    media: str          # 카탈로그 정본명(예 "AI Times")
    title: str          # 피드 원제목 그대로
    url: str
    published_at: str   # ISO8601 (없으면 "")
    group: str = ""     # "해외" | "국내" | ""(선별자가 안 나눔) — 선별 안에서만 씀(상한 초과 시 국내 보존), 화면 표시 없음
    area: str = ""      # HEADLINE_AREAS 중 하나 | ""(분류 안 됨) — 메일 칸의 분야 소제목


def fetch_headline_feed(source: src.Source, window_hours: int) -> list[src.FetchedArticle]:
    """RSS → (제목, 링크, 발행시각). 기사 페이지 요청 0 · 피드 요약문 미사용(raw_text="").

    `_fetch_feed` 를 쓰지 않는 이유: 그쪽은 링크를 따라가 전문을 받고(금지된 본문 수집), 짧은 항목을
    스텁으로 버린다(제목만 있는 항목은 전부 탈락). 여기선 둘 다 하면 안 된다.
    """
    import feedparser  # lazy — sources._fetch_feed 와 같은 이유

    if not robots.allowed(source.url, robots.FEED_TOKEN):   # 막힌 피드는 요청하지 않는다(non-silent)
        _debug.warn("robots", f"{source.key}: robots.txt 가 막은 피드 — 요청 안 함: {source.url}")
        return []
    feed = src._with_deadline(lambda: feedparser.parse(source.url), src._FETCH_TIMEOUT_S,
                              f"headline feed {source.url}")
    if feed is None:   # 시간초과(warn 은 _with_deadline 이 이미 냄)
        return []
    now = time.time()
    out: list[src.FetchedArticle] = []
    for entry in feed.entries:
        if len(out) >= _POOL:
            break
        title = (entry.get("title") or "").strip()
        link = (entry.get("link") or "").strip()
        if not (title and link):
            continue
        published = ""
        parsed = entry.get("published_parsed") or entry.get("updated_parsed")
        if parsed:
            ts = calendar.timegm(parsed)
            if window_hours and (now - ts) / 3600.0 > window_hours:
                continue
            published = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
        out.append(src.FetchedArticle(source.key, link, title, "", published))
    return out


def keyword_latest(cands: Sequence[src.FetchedArticle], k: int) -> list[src.FetchedArticle]:
    """결정론 폴백 — 제목 키워드로 비AI 를 빼고 최신순 k건(선별자 미주입·장애 시)."""
    return [a for a in cands if is_ai_relevant(a.title, "")][:k]


def _indices(text: str, n: int, *, last: bool = False) -> list[int] | None:
    """응답의 JSON 번호 배열(첫/마지막) → 1..n 범위·중복 제거한 번호. 배열이 없으면 None."""
    found = _IDX_RE.findall(text or "")
    if not found:
        return None
    out: list[int] = []
    for i in json.loads(found[-1] if last else found[0]):
        if isinstance(i, int) and 1 <= i <= n and i not in out:
            out.append(i)
    return out


def _drop_covered(arts: list[src.FetchedArticle], covered: Sequence[str],
                  invoke: Callable[[str, str], str]) -> list[src.FetchedArticle]:
    """카드와 같은 사건인 후보 제거(교차 언어). 실패하면 이 단계만 건너뛴다(non-silent) — 중복 1건이 빈 칸보다 낫다."""
    if not covered:
        return arts
    user = ("Candidates:\n" + "\n".join(f"{i}. {a.title}" for i, a in enumerate(arts, start=1))
            + "\n\nReference titles:\n" + "\n".join(f"- {t}" for t in covered))
    try:
        same = _indices(invoke(_DEDUP_SYSTEM, user), len(arts), last=True)
        if same is None:
            _debug.warn("headlines dedup", "번호 배열 없음 → 중복 제거 건너뜀")
            return arts
        return [a for i, a in enumerate(arts, start=1) if i not in same]
    except Exception as err:  # noqa: BLE001
        _debug.warn("headlines dedup", f"{type(err).__name__}: {err} → 중복 제거 건너뜀")
        return arts


def _grouped(text: str, n: int) -> list[tuple[int, str]] | None:
    """응답 마지막 줄의 {"global": [...], "domestic": [...]} → [(번호, "해외"|"국내")] (해외 먼저, 범위·중복 제거).

    객체가 없고 번호 배열만 있으면 그룹 없음("")으로 받는다(구형 응답 호환). 둘 다 없으면 None.
    """
    objs = re.findall(r"\{[^{}]*\}", text or "")
    if objs:
        try:
            d = json.loads(objs[-1])
        except ValueError:
            d = None
        if isinstance(d, dict):
            out: list[tuple[int, str]] = []
            for key, label in (("global", "해외"), ("domestic", "국내")):
                for i in d.get(key) or []:
                    if isinstance(i, int) and 1 <= i <= n and i not in {j for j, _ in out}:
                        out.append((i, label))
            return out
    idx = _indices(text, n, last=True)
    return None if idx is None else [(i, "") for i in idx]


def llm_headline_select(cands: Sequence[src.FetchedArticle], k: int, covered: Sequence[str],
                        *, invoke: Callable[[str, str], str],
                        invoke_dedup: Callable[[str, str], str] | None = None) -> list[tuple[src.FetchedArticle, str]]:
    """LLM 선별 2단계 — ① 카드와 같은 사건 제거(covered 가 있을 때만) ② 남은 제목에서 상한 이하, 해외/국내로 나눠 선택.

    판정자에 넘기는 것은 AI타임스 **제목**과 우리 카드 소스의 제목뿐이다(본문·요약문 없음 — 고지 준수).
    상한 초과 시 해외 끝에서 자른다(국내는 드물고 카드가 못 다루는 몫). 선별 실패 시 keyword_latest(non-silent, 그룹 없음).
    invoke_dedup 미지정이면 invoke 를 같이 쓴다.
    """
    arts = _drop_covered(list(cands), covered, invoke_dedup or invoke)
    if not arts:
        return []
    user = "\n".join(f"{i}. {a.title}" for i, a in enumerate(arts, start=1))
    try:
        picks = _grouped(invoke(_HEADLINE_SELECT_SYSTEM.format(k=k), user), len(arts))
        if picks is not None:
            dom = [p for p in picks if p[1] == "국내"]
            rest = [p for p in picks if p[1] != "국내"][:max(k - len(dom), 0)]
            return [(arts[i - 1], g) for i, g in (rest + dom)[:k]]   # 상한 미만 허용 — 비AI 를 억지로 채우지 않는다
        _debug.warn("headlines select", "번호 응답 없음 → 키워드·최신순 폴백")
    except Exception as err:  # noqa: BLE001 — throttle/timeout/파싱: 헤드라인 칸만 degrade
        _debug.warn("headlines select", f"{type(err).__name__}: {err} → 키워드·최신순 폴백")
    return [(a, "") for a in keyword_latest(arts, k)]


def llm_headline_areas(titles: Sequence[str], *, invoke: Callable[[str, str], str]) -> list[str]:
    """선별된 제목 → 제목마다 분야(HEADLINE_AREAS). 응답 = 마지막 줄 {"분야": [번호…]} 객체.

    전부 배정됐을 때만 돌려준다 — 일부만 분야가 있으면 소제목 없는 줄이 마지막 묶음에 섞여 보인다.
    목록 밖 이름·범위 밖 번호는 버리고(→ 미배정), 실패하면 [](non-silent): 칸은 소제목 없이 한 목록.
    """
    if not titles:
        return []
    user = "\n".join(f"{i}. {t}" for i, t in enumerate(titles, start=1))
    try:
        ans = invoke(_AREA_SYSTEM, user) or ""
        objs = re.findall(r"\{[^{}]*\}", ans)
        d = json.loads(objs[-1]) if objs else None
        if not isinstance(d, dict):
            raise ValueError(f"분야 객체 없음 (응답 {ans[-80:]!r})")
        areas = [""] * len(titles)
        for area, nums in d.items():
            if area not in HEADLINE_AREAS:
                continue
            for i in nums if isinstance(nums, list) else []:
                if isinstance(i, int) and 1 <= i <= len(titles) and not areas[i - 1]:
                    areas[i - 1] = area
        if all(areas):
            return areas
        _debug.warn("headlines area", f"분야 미배정 {areas.count('')}/{len(titles)}건 → 소제목 없이 한 목록")
    except Exception as err:  # noqa: BLE001 — throttle/timeout/파싱: 분야 소제목만 빠진다
        _debug.warn("headlines area", f"{type(err).__name__}: {err} → 소제목 없이 한 목록")
    return []


def collect_headlines(
    sources: Sequence[src.Source],
    *,
    window_hours: int = 24,
    fetch_fn: HeadlineFetchFn | None = None,
    relevance_fn: RelevanceFn | None = None,
    headline_select_fn: HeadlineSelectFn | None = None,
    headline_area_fn: HeadlineAreaFn | None = None,
    covered_titles: Sequence[str] = (),
) -> dict[str, list[Headline]]:
    """headlines_only 소스만 → {source_key: [Headline]}. 다른 소스는 무시(카드 경로 = curate).

    require_ai 면 제목으로 관련성 판정(주=Haiku, 미주입=키워드). select=llm 이면 선별자가 상한 이하로 고른다
    (주=Haiku: 실무 핵심 → 국내 AI, 카드와 같은 소식·비AI 제외 / 미주입=keyword_latest). 아니면 최신순 상한.
    headline_area_fn 이 있으면 고른 제목에 분야를 붙인다(실패·길이 불일치 = 분야 없음).
    한 소스 실패가 브리핑을 막지 않는다(curate 와 같은 source-level degradation).
    """
    fetch = fetch_fn or fetch_headline_feed
    is_relevant = relevance_fn or is_ai_relevant
    out: dict[str, list[Headline]] = {}
    for source in sources:
        if not source.headlines_only:
            continue
        try:
            arts = fetch(source, source.window_hours or window_hours)
        except Exception as err:  # noqa: BLE001 — 피드 1개 실패가 전체 브리핑을 죽이면 안 됨
            _debug.warn("headlines skip", f"{source.key}: {type(err).__name__}: {err}")
            continue
        # ★ 고지 준수 불변식: 주입 fetch 가 본문을 돌려줘도 판정자에게 닿기 전에 지운다 — AI 에는 제목만.
        cands = [replace(a, raw_text="") for a in list(arts)[:_POOL]]
        if source.require_ai:
            cands = [a for a in cands if is_relevant(a.title, "")]
        cap = source.max_items or _DEFAULT_MAX_HEADLINES
        if source.select == "llm":   # 상한 이하여도 호출 — 비AI·카드 중복 제외가 선별자의 일이다
            chooser = headline_select_fn or (lambda c, k, _cov: [(a, "") for a in keyword_latest(c, k)])
            picked = list(chooser(cands, cap, covered_titles))[:cap]
        else:
            picked = [(a, "") for a in latest_k(cands, cap)]
        areas = _areas([a.title for a, _ in picked], headline_area_fn) if picked else []
        if picked:
            out[source.key] = [Headline(source.key, source.name, a.title, a.url, a.published_at, g, ar)
                               for (a, g), ar in zip(picked, areas or [""] * len(picked))]
    return out


def _areas(titles: list[str], fn: HeadlineAreaFn | None) -> list[str]:
    """분야 판정 1회 — 주입 함수가 예외를 던지거나 길이가 안 맞으면 [](분야 없음). 헤드라인 칸 자체는 막지 않는다."""
    if fn is None:
        return []
    try:
        areas = list(fn(titles))
    except Exception as err:  # noqa: BLE001
        _debug.warn("headlines area", f"{type(err).__name__}: {err} → 소제목 없이 한 목록")
        return []
    if len(areas) != len(titles):
        _debug.warn("headlines area", f"분야 {len(areas)}개 ≠ 제목 {len(titles)}개 → 소제목 없이 한 목록")
        return []
    return areas
