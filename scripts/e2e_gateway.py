"""실 Gateway e2e — 승격한 retrieval 3 도구(fetch_article·get_source·discover_feed)를 *실제* AgentCore Gateway 로 호출해 본다.

각 도구가 Cognito JWT → Gateway(MCP) → Lambda dispatch → 도구 실행의 전 과정을 통과하고,
그 결과가 **직접 경로(fabric 내부 호출)와 같은지**를 확인한다 — ① Gateway 승격의 "동일 채널(identical channel)" 검증.

필요한 것: AWS 자격증명(us-east-1) + deploy_gateway.py 로 배포된 Gateway + `.env` 의 다음 값들 —
    GATEWAY_ENABLED=1 · GATEWAY_URL · GATEWAY_TARGET · COGNITO_SCOPE · COGNITO_CLIENT_ID
    · COGNITO_CLIENT_SECRET · COGNITO_TOKEN_URL   (deploy_gateway.py 출력 + describe-user-pool-client 로 얻은 secret)
  ※ COGNITO_CLIENT_SECRET 은 로컬 전용(.env, gitignore). Runtime 경로는 OAUTH_PROVIDER_NAME(볼트)으로 비밀 없이 토큰을 받는다.

실행(저장소 루트에서):
    uv run python scripts/e2e_gateway.py            # 기본: openai
    uv run python scripts/e2e_gateway.py aitimes    # 다른 출처

주의: get_source 검증은 *결정론적으로* 증명하려고 DDB(briefing-source-store)에 작은 동결본 1건을 쓴다(7일 TTL 이라 곧 사라짐 — 무해).
"""
from __future__ import annotations

import dataclasses
import json
import sys
from datetime import timedelta

from mcp.client.streamable_http import streamablehttp_client
from strands.tools.mcp.mcp_client import MCPClient

from briefing.core.config import load_settings
from briefing.core.retrieval import sources as src
from briefing.core.retrieval.curation import _default_fetch
from briefing.core.retrieval.gateway_client import _token
from briefing.core.stores.backends import make_stores


def _payload(res):
    """MCP 도구 결과(dict 또는 객체)에서 알맹이 dict 를 꺼낸다. 실제 형태: {'content': [{'text': '<JSON>'}], 'isError': False}.

    프로덕션 gateway_client._articles 와 같은 방어적 파싱 — structuredContent 를 먼저 보고, 없으면 content[0].text(JSON)를 파싱한다.
    """
    get = res.get if isinstance(res, dict) else (lambda k, d=None: getattr(res, k, d))
    sc = get("structuredContent")
    if isinstance(sc, dict):
        return sc
    content = get("content")
    if content:
        b = content[0]
        text = b.get("text") if isinstance(b, dict) else getattr(b, "text", None)
        if text:
            return json.loads(text)
    raise RuntimeError(f"예상 밖 MCP 형태: {res!r}")


def main() -> None:
    source_key = sys.argv[1] if len(sys.argv) > 1 else "openai"
    settings = load_settings()
    if not (settings.gateway_enabled and settings.gateway_url):
        sys.exit("GATEWAY_ENABLED=1 + GATEWAY_URL 필요 — deploy_gateway.py 출력값을 .env 에 넣으세요.")
    cat = {s.key: s for s in src.CATALOG}
    if source_key not in cat:
        sys.exit(f"알 수 없는 출처 '{source_key}' — 가능: {sorted(cat)}")
    source = cat[source_key]
    print(f"[설정] gateway={settings.gateway_url[:55]}… target={settings.gateway_target} "
          f"token={'Identity(provider)' if settings.oauth_provider_name else 'local(client_credentials)'}")

    token = _token(settings)

    def _transport():
        # Gateway MCP 엔드포인트로 가는 전송 — Authorization 헤더에 Bearer 토큰을 싣는다.
        return streamablehttp_client(url=settings.gateway_url,
                                     headers={"Authorization": f"Bearer {token}"},
                                     timeout=timedelta(seconds=120))

    results: dict[str, bool] = {}
    with MCPClient(_transport) as mcp:
        tools = sorted(getattr(t, "tool_name", getattr(t, "name", str(t))) for t in mcp.list_tools_sync())
        print(f"[0] tools/list → {tools}")

        # [1] fetch_article — Gateway 와 직접 경로의 본문이 byte 단위로 같은지. 라이브 RSS 라 두 호출의 *겹치는 기사*만 비교한다.
        gw = _payload(mcp.call_tool_sync("t1", f"{settings.gateway_target}___fetch_article",
                                         {"source_key": source_key, "window_hours": 336}))["articles"]
        direct = {a.url: a for a in _default_fetch(source, 336)}
        match = [a for a in gw if a["url"] in direct]
        results["fetch_article"] = bool(match) and all(a["raw_text"] == direct[a["url"]].raw_text for a in match)
        print(f"[1] fetch_article: gw={len(gw)} match={len(match)}/{len(gw)} byte-identical={results['fetch_article']}")

        # [2] get_source — DDB 에 동결한 뒤 Gateway 로 다시 읽는다. content-addressed(sha256)라 *결정론적* byte-identity 가 보장됨.
        s_ddb = dataclasses.replace(settings, backend="dynamo", source_table="briefing-source-store")
        store, _, _ = make_stores(s_ddb)
        fs = store.freeze(url="https://example.com/gw-e2e", title="GW E2E",
                          raw_text="GATEWAY E2E 동결 본문 — get_source 채널 검증용.",
                          fetched_at="2026-06-28", media="E2E")
        got = _payload(mcp.call_tool_sync("t2", f"{settings.gateway_target}___get_source",
                                          {"source_id": fs.source_id}))
        results["get_source"] = got.get("source_id") == fs.source_id and got.get("text") == fs.text
        print(f"[2] get_source: sid={fs.source_id[:16]}… match={results['get_source']}")

        # [3] discover_feed — Gateway 와 직접 경로의 결과가 같은지(둘 다 라이브 페치라 '등가'를 확인).
        gw_feed = _payload(mcp.call_tool_sync("t3", f"{settings.gateway_target}___discover_feed",
                                              {"url": source.url})).get("feed")
        d_feed = src.discover_feed(source.url)
        results["discover_feed"] = gw_feed == d_feed
        print(f"[3] discover_feed: gw={gw_feed!r} direct={d_feed!r} match={results['discover_feed']}")

    print("\n=== RESULT (3 도구 전체) ===")
    for k, v in results.items():
        print(f"  {'✅' if v else '❌'} {k}")
    if not all(results.values()):
        sys.exit(1)
    print("ALL PASS ✅")


if __name__ == "__main__":
    main()
