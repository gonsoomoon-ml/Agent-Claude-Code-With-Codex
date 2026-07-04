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
    def __init__(self):
        self.updates = []
        self._rec = None
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
    r, deps = _put(monkeypatch, {"sub": "SUB1", "email": "me@x.com", "token_use": "id", "email_verified": "true"},
                   {"user_id": "EVIL", "recipient": "victim@x.com", "sources": ["aitimes"], "send_hour": 7})
    assert r.status_code == 200
    sub, email, fields = deps["store"].updates[0]
    assert sub == "SUB1" and email == "me@x.com"


def test_put_rejects_access_token(monkeypatch):
    r, _ = _put(monkeypatch, {"sub": "S", "email": "e@x.com", "token_use": "access", "email_verified": "true"},
                {"sources": ["aitimes"]})
    assert r.status_code == 401


def test_put_rejects_unverified_email(monkeypatch):
    r, _ = _put(monkeypatch, {"sub": "S", "email": "e@x.com", "token_use": "id", "email_verified": "false"},
                {"sources": ["aitimes"]})
    assert r.status_code == 401


def test_put_validation_400(monkeypatch):
    r, _ = _put(monkeypatch, {"sub": "S", "email": "e@x.com", "token_use": "id", "email_verified": "true"},
                {"sources": ["ghost"]})
    assert r.status_code == 400


# --- cognito:groups → is_admin → policy 상한 배선 (Task 3) ---

def _deps6():
    d = _deps()
    d["keys"] = ["a", "b", "c", "d", "e", "f"]
    return d


def _claims_base():
    return {"sub": "S", "email": "e@x.com", "token_use": "id", "email_verified": "true"}


def _event_with_groups(groups):
    # 파일 기존 헬퍼는 bare `_event()` 가 아니라 claims dict 를 인자로 받는 인라인 이벤트 구성
    # (`_put` 참고)이므로, 여기서는 그 shape 을 그대로 재사용해 groups 를 얹는다.
    claims = _claims_base()
    if groups is not None:
        claims["cognito:groups"] = groups
    return {"requestContext": {"authorizer": {"jwt": {"claims": claims}}}}


def test_parse_groups_accepts_list_and_flattened_string():
    from briefing.webapi.app import _parse_groups
    assert _parse_groups(["admins"]) == {"admins"}
    assert _parse_groups("[admins]") == {"admins"}
    assert _parse_groups("[admins ops]") == {"admins", "ops"}
    assert _parse_groups(None) == set()


def test_get_profile_max_sources_default_5(monkeypatch):
    monkeypatch.setattr(appmod, "_profile_deps", _deps)
    monkeypatch.setattr(appmod, "_event_from_request", lambda req: _event_with_groups(None))
    r = TestClient(app).get("/profile")
    assert r.status_code == 200 and r.json()["max_sources"] == 5


def test_get_profile_admin_gets_catalog_size(monkeypatch):
    from briefing.core.retrieval.sources import CATALOG
    monkeypatch.setattr(appmod, "_profile_deps", _deps)
    monkeypatch.setattr(appmod, "_event_from_request", lambda req: _event_with_groups("[admins]"))
    r = TestClient(app).get("/profile")
    assert r.json()["max_sources"] == len(CATALOG)


def test_put_profile_six_sources_rejected_for_general(monkeypatch):
    monkeypatch.setattr(appmod, "_profile_deps", _deps6)
    monkeypatch.setattr(appmod, "_event_from_request", lambda req: _event_with_groups(None))
    r = TestClient(app).put("/profile", json={"sources": ["a", "b", "c", "d", "e", "f"], "send_hour": 7,
                                              "lens": "general", "depth": "summary"})
    assert r.status_code == 400


def test_put_profile_six_sources_accepted_for_admin(monkeypatch):
    monkeypatch.setattr(appmod, "_profile_deps", _deps6)
    monkeypatch.setattr(appmod, "_event_from_request", lambda req: _event_with_groups(["admins"]))
    r = TestClient(app).put("/profile", json={"sources": ["a", "b", "c", "d", "e", "f"], "send_hour": 7,
                                              "lens": "general", "depth": "summary"})
    assert r.status_code == 200
