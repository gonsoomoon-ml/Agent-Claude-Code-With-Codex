"""GET /admin/emails — require_admin 게이트 + sent-log Scan → Decimal→float 환원."""
from decimal import Decimal

import briefing.webapi.admin as admin_mod
from fastapi import Request, HTTPException


def _event(groups):
    return {"requestContext": {"authorizer": {"jwt": {"claims": {
        "token_use": "id", "email_verified": "true", "sub": "s", "email": "a@x.com",
        "cognito:groups": groups}}}}}


def _scope(groups):
    return {"type": "http", "aws.event": _event(groups), "headers": []}


class _FakeTable:
    def scan(self, **kw):
        return {"Items": [{"user_id": "u1", "recipient": "a@x.com", "run_date": "2026-07-08",
                           "sent_at": "2026-07-08T07:00:12+00:00", "published": 5,
                           "quarantined": 0, "duration_ms": 662000,
                           "cost_usd": Decimal("1.08"), "status": "sent", "message_id": "MID-1"}]}


def test_admin_list_emails_returns_rows_and_totals(monkeypatch):
    monkeypatch.setattr(admin_mod, "_sent_log_table", lambda: _FakeTable())
    out = admin_mod.list_emails(Request(_scope("[admins]")))
    assert out["totals"]["count"] == 1
    assert out["emails"][0]["recipient"] == "a@x.com"
    assert out["emails"][0]["cost_usd"] == 1.08   # Decimal→float 환원


class _MixedTable:
    def scan(self, **kw):
        return {"Items": [
            {"user_id": "old", "run_date": "2026-06-27"},   # 계측 이전 dedup-only (sent_at 없음)
            {"user_id": "u1", "recipient": "a@x.com", "run_date": "2026-07-08",
             "sent_at": "2026-07-08T07:00:12+00:00", "published": 5, "quarantined": 0,
             "duration_ms": 662000, "cost_usd": Decimal("1.08"), "status": "sent", "message_id": "MID-1"}]}


def test_admin_list_emails_excludes_preinstrumentation_dedup_rows(monkeypatch):
    monkeypatch.setattr(admin_mod, "_sent_log_table", lambda: _MixedTable())
    out = admin_mod.list_emails(Request(_scope("[admins]")))
    assert out["totals"]["count"] == 1                 # audit 필드 없는 old 행 제외
    assert out["emails"][0]["user_id"] == "u1"
    assert all("sent_at" in e for e in out["emails"])


def test_non_admin_forbidden(monkeypatch):
    monkeypatch.setattr(admin_mod, "_sent_log_table", lambda: _FakeTable())
    try:
        admin_mod.list_emails(Request(_scope("[]")))
        assert False, "should have raised 403"
    except HTTPException as e:
        assert e.status_code == 403


def test_admin_route_registered_on_app():
    # 설치된 FastAPI(0.138.1)는 include_router 를 app.routes 에 평탄화하지 않고
    # _IncludedRouter 로 감싼다 — 그래서 내부 표현이 아니라 실제 라우팅 결과(404 아님)로 검증한다.
    from fastapi.testclient import TestClient
    from briefing.webapi.app import app
    r = TestClient(app).get("/admin/emails")
    assert r.status_code != 404
