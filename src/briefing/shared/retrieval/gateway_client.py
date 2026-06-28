"""gateway_client — fabric 측 MCP 클라이언트. Cognito JWT(aiops 패턴) → Gateway → FetchArticleFn(opt-in).

★ 토큰(native): Runtime = AgentCore Identity(`get_resource_oauth2_token`, 비밀=볼트) / 로컬 = 직접 Cognito(.env, 테스트용).
  클라이언트 = mcp `streamablehttp_client` + strands `MCPClient` (새 dep 0 — mcp 는 strands transitive). freeze 는 curate 로컬(option A).
"""
from __future__ import annotations

import base64
import json
import urllib.parse
import urllib.request
from collections.abc import Sequence
from datetime import timedelta

from .sources import FetchedArticle, Source


def _token(s) -> str:
    """Gateway Bearer 토큰. oauth_provider_name 있으면 AgentCore Identity native(Runtime·비밀 볼트), 없으면 직접 Cognito(로컬)."""
    if s.oauth_provider_name:
        import boto3  # lazy
        return boto3.client("bedrock-agentcore", region_name=s.region).get_resource_oauth2_token(
            resourceCredentialProviderName=s.oauth_provider_name, scopes=[s.cognito_scope],
            oauth2Flow="M2M")["accessToken"]
    creds = base64.b64encode(f"{s.cognito_client_id}:{s.cognito_client_secret}".encode()).decode()  # 로컬 직접
    body = urllib.parse.urlencode({"grant_type": "client_credentials", "scope": s.cognito_scope}).encode()
    req = urllib.request.Request(s.cognito_token_url, data=body, headers={
        "Content-Type": "application/x-www-form-urlencoded", "Authorization": f"Basic {creds}"})
    with urllib.request.urlopen(req, timeout=15) as r:  # noqa: S310 (vetted Cognito token URL)
        return json.loads(r.read())["access_token"]


def _articles(result) -> list[dict]:
    """MCPToolResult → [{...}]. structuredContent 또는 content[0].text(JSON). (정확한 형태는 e2e 에서 확정.)"""
    sc = getattr(result, "structuredContent", None)
    if isinstance(sc, dict) and "articles" in sc:
        return sc["articles"]
    content = getattr(result, "content", None) or (result.get("content") if isinstance(result, dict) else None)
    if content:
        b = content[0]
        text = getattr(b, "text", None) or (b.get("text") if isinstance(b, dict) else None)
        if text:
            return json.loads(text)["articles"]
    raise RuntimeError(f"unexpected MCP result shape: {result!r}")


def gateway_fetch_factory(s):
    """settings → FetchArticleFn. GATEWAY_ENABLED 시 curate(fetch_article_fn=…) 로 주입 → fabric 이 로컬 freeze(A)."""
    from mcp.client.streamable_http import streamablehttp_client   # lazy(transitive — off 면 무관)
    from strands.tools.mcp.mcp_client import MCPClient

    token = _token(s)

    def _transport():
        return streamablehttp_client(url=s.gateway_url, headers={"Authorization": f"Bearer {token}"},
                                     timeout=timedelta(seconds=120))

    def fetch(source: Source, window_hours: int) -> Sequence[FetchedArticle]:
        with MCPClient(_transport) as mcp:
            res = mcp.call_tool_sync("gw-fetch", f"{s.gateway_target}___fetch_article",
                                     {"source_key": source.key, "window_hours": window_hours})
        return [FetchedArticle(**a) for a in _articles(res)]

    return fetch
