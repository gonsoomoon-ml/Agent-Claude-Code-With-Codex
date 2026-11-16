"""relevance_claude — 보조 판정(LLM-as-Judge)을 `claude -p`(Claude 구독 로그인)로 호출. `relevance_bedrock` 의 구독 변형.

`JUDGE_PROVIDER=subscription` 일 때 런타임이 이 파일의 `make_claude_*` 를 쓴다(기본 = relevance_bedrock · Converse).
판정 함수(llm_relevance 등)·프롬프트·파싱·폴백은 같다 — 바뀌는 것은 `invoke(system, user) -> str` 의 배관뿐.
- 호출 = `author._run_author`(clean dir · `--system-prompt`) + 도구 0(`tools=False`) + 구독 경로(`provider`) + stdin 프롬프트.
- 모델 이름은 직접 호출용(RELEVANCE_MODEL_ID=claude-haiku-5-5 · LABEL_MODEL_ID=claude-sonnet-5-5 — Bedrock id 아님).
- effort 는 CLI 기본(`"default"`) — 요약 AI 의 AUTHOR_EFFORT 를 따라가지 않게.
★ Converse 변형과 다른 점: maxTokens·thinking 을 판정별로 줄 수 없다(CLI 에 없는 옵션) → 판정 품질은 측정으로 확인한다.
실패(rc≠0 · timeout)는 예외로 올라가 각 llm_* 의 기존 폴백(키워드 · 최신순 · B 유지 · 평평)이 받는다.
"""
from __future__ import annotations

from collections.abc import Callable

from .. import _debug
from ..authoring.author import _run_author
from ..config import Settings
from ..top_picks import LabelFn, llm_labels
from .headlines import HeadlineAreaFn, llm_headline_areas, llm_headline_select
from .relevance import RelevanceFn, llm_relevance
from .relevance_bedrock import _label_model
from .rereport import RereportFn, llm_rereport
from .selection import SelectFn, llm_select

JUDGE_TIMEOUT_S = 120   # 판정 1건 상한(초) — 실측 1.3~2.5초(2026-11-16). 넘으면 예외 → 판정별 폴백


def _invoker(settings: Settings, model_id: str) -> Callable[[str, str], str]:
    """(system, user) -> str. 도구 0 · 구독 경로 · CLI 기본 effort · 프롬프트는 stdin(argv 한 개 상한 128KB 회피)."""
    def _invoke(system: str, user: str) -> str:
        return _run_author(system, user, settings, model_id=model_id, effort="default", timeout_s=JUDGE_TIMEOUT_S,
                           tools=False, provider="subscription", prompt_via_stdin=True)
    return _invoke


def make_claude_relevance(settings: Settings) -> RelevanceFn:
    """(title, text)->bool 관련성 판정. 모델 = RELEVANCE_MODEL_ID. 실패는 llm_relevance 가 키워드로 폴백."""
    invoke = _invoker(settings, settings.relevance_model_id)
    return lambda title, text: llm_relevance(title, text, invoke=invoke)


def make_claude_select(settings: Settings) -> SelectFn:
    """(candidates, k)->선별. 실패는 llm_select 가 최신순으로 폴백."""
    invoke = _invoker(settings, settings.relevance_model_id)
    return lambda articles, k: llm_select(articles, k, invoke=invoke)


def make_claude_rereport(settings: Settings) -> RereportFn:
    """(a_text, b_text)->재보도 판정. 실패는 llm_rereport 가 same=None(fail-open)."""
    invoke = _invoker(settings, settings.relevance_model_id)
    return lambda a_text, b_text: llm_rereport(a_text, b_text, invoke=invoke)


def make_claude_headline_select(settings: Settings):
    """(candidates, k, covered)->헤드라인 선별. 실패는 llm_headline_select 가 keyword_latest 로 폴백."""
    invoke = _invoker(settings, settings.relevance_model_id)
    return lambda cands, k, covered: llm_headline_select(cands, k, covered, invoke=invoke)


def make_claude_headline_areas(settings: Settings) -> HeadlineAreaFn:
    """titles->분야 목록. 모델 = 라벨 모델(LABEL_MODEL_ID, 빈 값이면 RELEVANCE). 실패는 [](소제목 없는 한 목록)."""
    invoke = _invoker(settings, _label_model(settings))
    return lambda titles: llm_headline_areas(titles, invoke=invoke)


def make_claude_labels(settings: Settings) -> LabelFn:
    """(보이는 카드, 섹션)->라벨 목록(핵심 3 + 분야). 모델 = 라벨 모델. 불완전·예외는 llm_labels 가 1회 재시도 뒤 올린다."""
    model_id = _label_model(settings)
    invoke = _invoker(settings, model_id)

    def _invoke(system: str, user: str) -> str:
        _debug.warn("areas 호출", f"model={model_id} via=claude -p")   # Bedrock 변형과 같은 줄 — 라벨 모델이 컨테이너까지 갔는지 증명
        return invoke(system, user)

    return lambda cards, sections=(): llm_labels(cards, sections, invoke=_invoke)
