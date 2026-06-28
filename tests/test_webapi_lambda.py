"""lambda_main.handler — Mangum 어댑터가 HTTP API v2 이벤트를 FastAPI 로 라우팅(무클라우드)."""
from __future__ import annotations

from briefing.webapi.lambda_main import handler


def _http_v2_event(path: str) -> dict:
    return {
        "version": "2.0", "routeKey": f"GET {path}", "rawPath": path, "rawQueryString": "",
        "headers": {"host": "test"},
        "requestContext": {"http": {"method": "GET", "path": path, "sourceIp": "127.0.0.1"}, "stage": "$default"},
        "isBase64Encoded": False,
    }


def test_handler_routes_health():
    resp = handler(_http_v2_event("/health"), None)
    assert resp["statusCode"] == 200
    assert '"ok"' in resp["body"]
