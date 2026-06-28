"""gateway_handler — AgentCore Gateway 의 Lambda MCP 타깃. retrieval 3도구를 *기존 함수 호출*로 노출.

★ guardrail(decorrelation): **dispatch 화이트리스트 = retrieval 3도구뿐** — MCP 호출에서 certify/produce_card/author 로
  가는 *코드 경로가 없음*. (store 계층이 직렬화용으로 그 타입을 transitively import 하지만, 어떤 도구도 호출 안 함 → MCP 도달 불가.)
도구명 = `context.client_context.custom['bedrockAgentCoreToolName']` = "TARGET___tool" (AgentCore 규약).
승격 3도구(권력 구배): fetch_article=originate(fabric) · get_source=read(fabric+author) · discover_feed=discovery(fabric).
"""
from __future__ import annotations

from dataclasses import asdict

from ..shared.config import load_settings
from ..shared.retrieval import sources as src
from ..shared.retrieval.curation import _default_fetch       # fetch 만(freeze 아님 — option A: 동결은 fabric 로컬)
from ..shared.stores.backends import make_stores

_CATALOG = {s.key: s for s in src.CATALOG}   # import 시 1회(부작용 없음 — CATALOG 는 이미 로드됨)
_STORE = None                                # lazy(콜드스타트 1회; get_source 전용)


def _store():
    """warm store(backend 선택) — get_source 용. lazy 라 import 부작용 0(단위테스트 친화)."""
    global _STORE
    if _STORE is None:
        _STORE, _, _ = make_stores(load_settings())
    return _STORE


def lambda_handler(event, context):
    """MCP tools/call → 도구명 디스패치 → 기존 함수. 화이트리스트 3개 외 fail-closed."""
    tool = context.client_context.custom["bedrockAgentCoreToolName"].split("___", 1)[-1]
    if tool == "fetch_article":              # originate(fabric only) — 최근 기사 raw 페치(freeze 는 fabric 로컬)
        arts = _default_fetch(_CATALOG[event["source_key"]], int(event.get("window_hours", 24)))
        return {"articles": [asdict(a) for a in arts]}
    if tool == "get_source":                 # read(fabric + author) — 동결본 재열람
        return asdict(_store().get_source(event["source_id"]))
    if tool == "discover_feed":              # discovery(fabric) — 피드 찾기(비권위)
        return {"feed": src.discover_feed(event["url"])}
    raise ValueError(f"unknown tool: {tool}")  # fail-closed
