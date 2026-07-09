"""POST /trial 라우트 — handle_trial 위임 + CORS POST. boto3 는 monkeypatch fake."""
from __future__ import annotations

from fastapi.testclient import TestClient

import briefing.webapi.app as appmod
import briefing.webapi.authz as authzmod
from briefing.webapi.app import app

client = TestClient(app)


class _Ses:
    def __init__(self): self.verified = []
    def get_identity_verification_attributes(self, Identities):
        return {"VerificationAttributes": {Identities[0]: {"VerificationStatus": "Pending"}}}
    def verify_email_identity(self, EmailAddress): self.verified.append(EmailAddress)


class _Store:
    def within_cooldown(self, e): return False
    def over_global_cap(self, d, c): return False
    def record(self, e, s, *, ttl=0): pass


def _fake_deps():
    inv = []
    return {"store": _Store(), "ses": _Ses(),
            "runtime_invoke": lambda mode, p: inv.append((mode, p)), "sender": "s@x.com",
            "cap": 50, "cooldown_s": 3600, "test_emails": frozenset(), "_inv": inv}


def test_post_trial_pending(monkeypatch):
    deps = _fake_deps()
    monkeypatch.setattr(appmod, "_trial_deps", lambda: deps)
    r = client.post("/trial", json={"email": "u@x.com", "sources": ["aitimes"]})
    assert r.status_code == 202 and r.json()["status"] == "verification_pending"
    assert deps["_inv"] and deps["_inv"][0][0] == "trial"


def test_post_trial_validation_400(monkeypatch):
    monkeypatch.setattr(appmod, "_trial_deps", lambda: _fake_deps())
    r = client.post("/trial", json={"email": "bad", "sources": ["aitimes"]})
    assert r.status_code == 400


def test_cors_allows_post():
    r = client.options("/trial", headers={"Origin": "https://x.cloudfront.net",
                                          "Access-Control-Request-Method": "POST"})
    assert r.status_code in (200, 204)
    assert "POST" in r.headers.get("access-control-allow-methods", "")


class _CooldownStore:
    """within_cooldown 항상 True — 우회 분기 검증용."""
    def within_cooldown(self, e): return True
    def over_global_cap(self, d, c): return False
    def record(self, e, s, *, ttl=0): pass


def test_post_trial_allowlist_bypasses_cooldown(monkeypatch):
    deps = _fake_deps()
    deps["store"] = _CooldownStore()
    deps["test_emails"] = frozenset({"u@x.com"})
    monkeypatch.setattr(appmod, "_trial_deps", lambda: deps)
    r = client.post("/trial", json={"email": "u@x.com", "sources": ["aitimes"]})
    assert r.status_code == 202


def test_post_trial_non_allowlist_hits_cooldown(monkeypatch):
    deps = _fake_deps()
    deps["store"] = _CooldownStore()
    deps["test_emails"] = frozenset()       # 빈 allowlist → 공개 가드
    monkeypatch.setattr(appmod, "_trial_deps", lambda: deps)
    r = client.post("/trial", json={"email": "u@x.com", "sources": ["aitimes"]})
    assert r.status_code == 429


def test_post_trial_six_sources_rejected_even_with_admin_claims(monkeypatch):
    """회귀(스펙 §6 불변식5): trial 은 role 을 조회조차 안 하므로 admins 그룹 claim 이 실려도
    5 초과 소스는 무조건 400 — is_admin 배선이 trial 로 새지 않았음을 증명."""
    deps = _fake_deps()
    monkeypatch.setattr(appmod, "_trial_deps", lambda: deps)
    ev = {"requestContext": {"authorizer": {"jwt": {"claims": {"cognito:groups": ["admins"]}}}}}
    monkeypatch.setattr(authzmod, "_event_from_request", lambda req: ev)
    r = client.post("/trial", json={"email": "u@x.com",
                                     "sources": ["a", "b", "c", "d", "e", "f"]})
    assert r.status_code == 400
