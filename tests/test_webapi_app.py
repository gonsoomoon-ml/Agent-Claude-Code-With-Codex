"""webapi.app — FastAPI 라우트(GET /catalog·/sample·/health) + CORS. TestClient(무클라우드)."""
from __future__ import annotations

from fastapi.testclient import TestClient

from briefing.webapi.app import app

client = TestClient(app)


def test_get_catalog_returns_form_shape():
    r = client.get("/catalog")
    assert r.status_code == 200
    body = r.json()
    assert body["max_sources"] == 5
    assert body["send_hours"] == [6, 7, 8]
    names = [g["name"] for g in body["categories"]]
    assert "전체" not in names and len(names) >= 2   # H2(LANE-A): category 별 그룹(폴백 아님)


def test_get_sample_returns_html():
    r = client.get("/sample")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert "오늘의 AI 브리핑" in r.text


def test_health_ok():
    assert client.get("/health").json() == {"ok": True}


def test_cors_header_present_for_browser_origin():
    # CORSMiddleware 가 Origin 요청에 allow-origin 헤더를 단다(브라우저 SPA 호출 가능).
    r = client.get("/catalog", headers={"Origin": "https://example.cloudfront.net"})
    assert r.headers.get("access-control-allow-origin") in ("*", "https://example.cloudfront.net")
