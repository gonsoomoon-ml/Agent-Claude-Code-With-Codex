"""GET/PUT /profile — JWT claims(scope aws.event) 추출 + IDOR-safe write. monkeypatch deps."""
from __future__ import annotations

from fastapi.testclient import TestClient

import briefing.webapi.app as appmod
from briefing.webapi.app import app


def _client(claims):
    # HTTP API v2 JWT authorizer 이벤트 모양을 scope 에 주입
    ev = {"requestContext": {"authorizer": {"jwt": {"claims": claims}}}}
    c = TestClient(app)
    c.app_event = ev
    return c


class _Store:
    def __init__(self): self.updates = []; self._rec = None
    def get_user(self, uid): return self._rec
    def update_profile_from_jwt(self, *, sub, email, fields): self.updates.append((sub, email, fields))


def _deps():
    return {"store": _Store(), "ses": None, "sender": "s@x.com",
            "keys": ["aitimes", "openai"], "lenses": ["general"], "ensure_ses": lambda e: "active"}


def _put(monkeypatch, claims, body):
    deps = _deps()
    monkeypatch.setattr(appmod, "_profile_deps", lambda: deps)
    # scope 에 aws.event 주입: TestClient 의 transport 가 scope 를 만들므로 미들웨어/의존성에서 읽도록 헤더 우회
    ev = {"requestContext": {"authorizer": {"jwt": {"claims": claims}}}}
    monkeypatch.setattr(appmod, "_event_from_request", lambda req: ev)   # app.py 가 이 헬퍼로 event 취득
    r = TestClient(app).put("/profile", json=body)
    return r, deps


def test_put_keys_on_sub_email_ignores_body(monkeypatch):
    r, deps = _put(monkeypatch, {"sub": "SUB1", "email": "me@x.com", "token_use": "id"},
                   {"user_id": "EVIL", "recipient": "victim@x.com", "sources": ["aitimes"], "send_hour": 7})
    assert r.status_code == 200
    sub, email, fields = deps["store"].updates[0]
    assert sub == "SUB1" and email == "me@x.com"


def test_put_rejects_access_token(monkeypatch):
    r, _ = _put(monkeypatch, {"sub": "S", "email": "e@x.com", "token_use": "access"},
                {"sources": ["aitimes"]})
    assert r.status_code == 401


def test_put_validation_400(monkeypatch):
    r, _ = _put(monkeypatch, {"sub": "S", "email": "e@x.com", "token_use": "id"},
                {"sources": ["ghost"]})
    assert r.status_code == 400
