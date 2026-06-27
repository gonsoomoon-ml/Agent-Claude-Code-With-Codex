"""supervisor — Strands Agent 오케스트레이터 (supervisor-delegates-to-tools 패턴; 설계 근거 = four-component-analysis.md §5.7).

★ 신뢰 경계 보존(비협상): supervisor(LLM)는 *순서만* 통제 — 도구를 올바른 순서로 호출할 뿐 **발행 결정은 안 함.**
verify-before-publish 게이트(author→certifier→**결정론 decide**)는 `verify_and_produce_card` 도구 *안*에 있어
supervisor 가 reach/override 불가 — 결정·실행은 도구가, supervisor 는 순서만 통제.
- **decorrelation:** supervisor 는 author↔certifier 사이에 *앉지 않는다* — 그 핸드오프는 produce_card 도구 내부(envelope).
- 도구 3개는 전부 결정론 Python(shared/runtime)을 얇게 감싼 것. **LLM 은 supervisor 하나뿐.**
- 1회 실행 컨텍스트는 모듈 전역 `_CTX`(global node-state 패턴) — 도구들이 공유.
"""
from __future__ import annotations

import time

from strands import Agent, tool
from strands.hooks import HookProvider
from strands.hooks.events import AfterModelCallEvent, BeforeModelCallEvent, BeforeToolCallEvent
from strands.models import BedrockModel

from ..shared import _debug, render
from ..shared import sources as src
from ..shared.config import Settings, UserConfig, load_settings, load_user
from ..shared.gate import GatedCard, produce_card
from ..shared.prompts import apply_prompt_template
from ..shared.curation import curate
from ..shared.source_store import SourceStore

# supervisor 1회 실행 컨텍스트 — run_supervisor 가 세팅, 세 도구가 공유.
_CTX: dict = {}


@tool
def curate_sources(window_hours: int = 24) -> str:
    """Fetch and freeze the user's selected news sources. Call this FIRST, exactly once.

    Returns the list of frozen source_ids; you must then call verify_and_produce_card for EACH id.
    """
    user: UserConfig = _CTX["user"]
    store: SourceStore = _CTX["store"]
    max_items = _CTX.get("max_items", 5)
    keys = _CTX.get("source_keys") or list(user.sources)

    def _fetch_fn(source, win):
        if source.fragile:
            return src.fetch_fragile(source)
        return src.fetch_clean_rss(source, window_hours=win, max_items=max_items)

    targets = src.fetch_set([keys])
    by_key = curate(store, targets, window_hours=window_hours, fetch_article_fn=_fetch_fn)
    frozen = [fs for v in by_key.values() for fs in v]
    _CTX["frozen"] = {fs.source_id: fs for fs in frozen}
    if not frozen:
        return "Curated 0 sources (empty feeds). Call render_briefing to finish with no items."
    listing = "\n".join(f"- {fs.source_id}  ::  {fs.title[:60]}" for fs in frozen)
    return f"Curated {len(frozen)} source(s). Call verify_and_produce_card for each id:\n{listing}"


@tool
def verify_and_produce_card(source_id: str) -> str:
    """Run the verify-before-publish gate on ONE frozen source (by source_id from curate_sources).

    The author drafts atomic claims, an INDEPENDENT certifier verifies each, and a DETERMINISTIC rule
    decides PUBLISH or QUARANTINE. You do NOT decide publish — this tool owns that decision and you
    cannot change its verdict. Returns the decision and per-verdict counts.
    """
    fs = _CTX.get("frozen", {}).get(source_id)
    if fs is None:
        return f"Unknown source_id {source_id!r}; use an id returned by curate_sources."
    settings: Settings = _CTX["settings"]
    user: UserConfig = _CTX["user"]
    store: SourceStore = _CTX["store"]
    gated: GatedCard = produce_card(fs, user, settings, store)
    _CTX.setdefault("cards", []).append(gated)
    counts = {k: sum(1 for v in gated.verdicts if v.verdict == k) for k in ("VERIFIED", "DEMOTED", "BLOCKED")}
    return f"source {source_id[:12]}: decision={gated.decision} attempts={gated.attempts} verdicts={counts}"


@tool
def render_briefing() -> str:
    """Render the final email from PUBLISH cards only (QUARANTINE excluded). Call LAST, exactly once."""
    cards: list[GatedCard] = _CTX.get("cards", [])
    user: UserConfig = _CTX["user"]
    settings: Settings = _CTX["settings"]
    email = render.render_email(cards, user, settings, _CTX["store"])
    _CTX["email"] = email
    published = sum(1 for c in cards if c.decision == "PUBLISH")
    return f"Rendered briefing: {published} published / {len(cards) - published} quarantined, {len(email)} bytes."


def _tool_label(event: object) -> str:
    """이벤트에서 도구 이름+입력을 best-effort 추출 (Strands 버전별 속성 차이에 방어적)."""
    tu = getattr(event, "tool_use", None) or getattr(event, "tool", None)
    if isinstance(tu, dict):
        return f"{tu.get('name', '?')}({_debug.truncate(tu.get('input', {}), 80)})"
    return getattr(event, "tool_name", None) or _debug.truncate(repr(tu), 80)


class _DebugFlowHook(HookProvider):
    """DEBUG=1 시 supervisor 의 LLM 호출·도구 호출을 추적 (Strands HookProvider = FlowHook 패턴).

    LLM call # + 지속시간(Before/AfterModelCall) + 도구 라우팅(BeforeToolCall). DEBUG off 면 애초에 미등록(get_supervisor).
    """

    def __init__(self) -> None:
        self._calls = 0
        self._t0 = 0.0

    def register_hooks(self, registry: object, **_kwargs: object) -> None:
        registry.add_callback(BeforeModelCallEvent, self._before_model)
        registry.add_callback(AfterModelCallEvent, self._after_model)
        registry.add_callback(BeforeToolCallEvent, self._before_tool)

    def _before_model(self, _event: object) -> None:
        self._calls += 1
        self._t0 = time.monotonic()
        _debug.dprint("supervisor → LLM", f"call #{self._calls}", "cyan")

    def _after_model(self, _event: object) -> None:
        _debug.dprint("supervisor ⊣ LLM",
                      f"call #{self._calls} · {int((time.monotonic() - self._t0) * 1000)}ms", "dim")

    def _before_tool(self, event: object) -> None:
        _debug.dprint("supervisor → tool", _tool_label(event), "magenta")


def get_supervisor(settings: Settings) -> Agent:
    """Strands supervisor Agent — 도구 3개 + supervisor.md 프롬프트. LLM 은 *순서만* 통제(발행 결정 X)."""
    model = BedrockModel(
        model_id=settings.supervisor_model_id,  # per-role 라우팅 (기본=author_model_id)
        region_name=settings.region,
        streaming=False,
        temperature=0,
        additional_request_fields={"thinking": {"type": "disabled"}},
    )
    return Agent(
        model=model,
        system_prompt=apply_prompt_template("supervisor"),
        tools=[curate_sources, verify_and_produce_card, render_briefing],
        hooks=[_DebugFlowHook()] if _debug.is_debug() else [],  # 조건부 등록(DEBUG off → hook 0)
        callback_handler=None,
    )


def run_supervisor(
    user_id: str = "gonsoo",
    *,
    window_hours: int = 24,
    source_keys: list[str] | None = None,
    max_items: int = 5,
) -> dict:
    """Strands supervisor 가 파이프라인을 오케스트레이션(curate→produce per source→render). 결과 dict 반환.

    신뢰 경계: supervisor 는 순서만 — 모든 verify/decide 는 도구(결정론) 소유. (source_keys/max_items = 스모크 제한용.)
    """
    settings = load_settings()
    store = SourceStore(settings.source_store_path)
    user = load_user(user_id, settings)
    _CTX.clear()
    _CTX.update(settings=settings, store=store, user=user, source_keys=source_keys, max_items=max_items)

    agent = get_supervisor(settings)
    task = (
        f"Produce today's verified briefing for user '{user_id}' (window {window_hours}h). "
        "Follow the mandatory sequence: curate_sources, then verify_and_produce_card for EVERY returned "
        "source_id, then render_briefing. Do not decide publish yourself."
    )
    transcript = str(agent(task))
    return {"email": _CTX.get("email", ""), "cards": _CTX.get("cards", []), "transcript": transcript}
