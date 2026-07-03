"""gateway_client — fabric(데이터 직조 계층) 쪽에서 AgentCore Gateway 를 호출하는 MCP 클라이언트.

`GATEWAY_ENABLED` 가 켜져 있을 때만 쓰인다. 큰 흐름은 셋:
  ① Cognito 로 Bearer 토큰을 받고 → ② Gateway(MCP)로 `fetch_article` 도구를 호출 → ③ 결과를 `FetchArticleFn` 으로 돌려준다.
  fabric 은 이 함수를 curate 에 주입해서, *직접 fetch 하는 대신 Gateway 를 경유*해 기사를 가져온다.

토큰을 얻는 길은 두 가지:
  - Runtime(클라우드): AgentCore Identity 의 `get_resource_oauth2_token` — 비밀(secret)이 볼트에 있어 코드가 직접 만지지 않는다.
  - 로컬(개발·테스트): `.env` 의 Cognito client_id/secret 으로 직접 토큰을 발급(client_credentials).
새로 까는 의존성은 없다 — `mcp.streamablehttp_client` 와 `strands.MCPClient` 는 strands 에 이미 딸려온다.
동결(freeze)은 여기서 하지 않는다 — Gateway 는 fetch 만 하고, 받아온 기사는 fabric 이 *로컬에서* 동결한다(option A).
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
    """Gateway 호출에 쓸 Bearer 토큰을 발급한다.

    `oauth_provider_name` 이 있으면(= Runtime) AgentCore Identity 가 토큰을 내준다 — 비밀은 볼트에 있어 코드가 만지지 않는다.
    없으면(= 로컬) `.env` 의 Cognito client_id/secret 으로 직접 토큰을 받는다(테스트용).
    """
    if s.oauth_provider_name:
        import boto3  # 로컬 경로에는 boto3 가 필요 없으니, Runtime 경로일 때만 import 한다
        return boto3.client("bedrock-agentcore", region_name=s.region).get_resource_oauth2_token(
            resourceCredentialProviderName=s.oauth_provider_name, scopes=[s.cognito_scope],
            oauth2Flow="M2M")["accessToken"]
    # 로컬: client_id:secret 을 Basic 인증으로 보내, client_credentials 방식으로 토큰을 직접 발급한다
    creds = base64.b64encode(f"{s.cognito_client_id}:{s.cognito_client_secret}".encode()).decode()
    body = urllib.parse.urlencode({"grant_type": "client_credentials", "scope": s.cognito_scope}).encode()
    req = urllib.request.Request(s.cognito_token_url, data=body, headers={
        "Content-Type": "application/x-www-form-urlencoded", "Authorization": f"Basic {creds}"})
    with urllib.request.urlopen(req, timeout=15) as r:  # noqa: S310 — 신뢰된 Cognito 토큰 URL(검증됨)
        return json.loads(r.read())["access_token"]


def _articles(result) -> list[dict]:
    """MCP 도구 결과에서 기사 목록(`articles`)을 꺼낸다.

    결과 형태가 환경마다 달라서 두 경로를 모두 받는다 — `structuredContent`(dict)를 먼저 보고,
    없으면 `content[0].text`(JSON 문자열)를 파싱한다.
    (실제로는 content[0].text 형태임이 e2e 로 확인됐지만, 둘 다 처리해 두는 편이 안전하다.)
    """
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
    """settings 를 받아, 출처 하나를 Gateway 로 fetch 하는 함수(`FetchArticleFn`)를 만들어 돌려준다.

    `GATEWAY_ENABLED` 가 켜지면 fabric 이 이 함수를 `curate(fetch_article_fn=…)` 로 주입한다 →
    직접 fetch 대신 Gateway 를 경유해 기사를 받고, 동결은 fabric 이 로컬에서 한다(option A).
    """
    from mcp.client.streamable_http import streamablehttp_client   # 필요할 때만 import(strands 에 딸려옴 — Gateway off 면 안 불림)
    from strands.tools.mcp.mcp_client import MCPClient

    token = _token(s)   # 팩토리를 만들 때 토큰을 1회 발급한다(주의: 갱신하지 않음 — 장시간 실행 시 만료될 수 있음)

    def _transport():
        # Gateway 의 MCP 엔드포인트로 가는 HTTP 전송 — Authorization 헤더에 Bearer 토큰을 실어 보낸다.
        return streamablehttp_client(url=s.gateway_url, headers={"Authorization": f"Bearer {token}"},
                                     timeout=timedelta(seconds=120))

    def fetch(source: Source, window_hours: int) -> Sequence[FetchedArticle]:
        # 출처 1개를 Gateway 의 fetch_article 도구로 호출하고, 받은 결과를 FetchedArticle 로 복원한다.
        with MCPClient(_transport) as mcp:   # 호출할 때마다 MCP 세션을 새로 열고 닫는다
            res = mcp.call_tool_sync("gw-fetch", f"{s.gateway_target}___fetch_article",
                                     {"source_key": source.key, "window_hours": window_hours})
        return [FetchedArticle(**a) for a in _articles(res)]

    return fetch
