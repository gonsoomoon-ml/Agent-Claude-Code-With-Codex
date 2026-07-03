"""gateway_handler — AgentCore Gateway 가 호출하는 Lambda(= MCP 타깃). retrieval 3도구를 *기존 함수 그대로* 노출한다.

★ 가드레일(decorrelation): **노출하는 건 retrieval 3도구뿐이고, dispatch 도 그 3개로 하드코딩**돼 있다 —
  MCP 호출에서 certify/produce_card/author 로 가는 *코드 경로가 아예 없다*.
  (store 계층이 직렬화 때문에 그 타입들을 따라-import 하긴 하지만, 어떤 도구도 그것들을 *호출*하지 않으므로 MCP 로는 닿을 수 없다.)
도구 이름은 `context.client_context.custom['bedrockAgentCoreToolName']` = "TARGET___tool" 형식(AgentCore 규약).
3도구의 권한 구배: fetch_article = 페치(fabric 만) · get_source = 읽기(fabric + author) · discover_feed = 피드 발견(fabric).
"""
from __future__ import annotations

from dataclasses import asdict

from ..core.config import load_settings
from ..core.retrieval import sources as src
from ..core.retrieval.curation import _default_fetch       # fetch 만 쓴다(freeze 아님 — option A: 동결은 fabric 이 로컬에서)
from ..core.stores.backends import make_stores

_CATALOG = {s.key: s for s in src.CATALOG}   # import 될 때 1회 만든다(부작용 없음 — CATALOG 는 이미 로드돼 있음)
_STORE = None                                # 지연 초기화(콜드스타트 때 1회; get_source 에서만 필요)


def _store():
    """get_source 가 쓸 store(backend 선택)를 준비한다. 지연 초기화라 import 부작용이 없다(단위테스트 친화)."""
    global _STORE
    if _STORE is None:
        _STORE, _, _ = make_stores(load_settings())
    return _STORE


def lambda_handler(event, context):
    """MCP tools/call → 도구 이름으로 디스패치 → 기존 함수 호출. 화이트리스트 3개 밖이면 fail-closed(예외)."""
    tool = context.client_context.custom["bedrockAgentCoreToolName"].split("___", 1)[-1]
    if tool == "fetch_article":              # 페치(fabric 전용) — 최근 기사 raw 를 가져온다(동결은 fabric 이 로컬에서)
        arts = _default_fetch(_CATALOG[event["source_key"]], int(event.get("window_hours", 24)))
        return {"articles": [asdict(a) for a in arts]}
    if tool == "get_source":                 # 읽기(fabric + author) — 동결해 둔 정본을 다시 읽는다
        return asdict(_store().get_source(event["source_id"]))
    if tool == "discover_feed":              # 피드 발견(fabric·비권위). ※ 임의 URL 을 서버가 페치(SSRF 성격) — authn(allowedClients)으로만 바운드
        return {"feed": src.discover_feed(event["url"])}
    raise ValueError(f"unknown tool: {tool}")  # fail-closed(화이트리스트 밖 도구는 거부)
