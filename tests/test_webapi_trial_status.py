"""GET /trial/status — briefing-trials 상태 조회(폴링용). fake table."""
from __future__ import annotations
from fastapi.testclient import TestClient
import briefing.webapi.app as appmod
from briefing.webapi.app import app
from briefing.webapi.trial import TrialStore

class _T:
    def __init__(self, item): self._i = item
    def get_item(self, Key): return {"Item": self._i} if self._i else {}

def test_get_status_returns_status(monkeypatch):
    monkeypatch.setattr(appmod, "_status_store", lambda: TrialStore(_T({"email": "u@x.com", "status": "generating"})))
    r = TestClient(app).get("/trial/status", params={"email": "u@x.com"})
    assert r.status_code == 200 and r.json()["status"] == "generating"

def test_get_status_unknown_when_no_row(monkeypatch):
    monkeypatch.setattr(appmod, "_status_store", lambda: TrialStore(_T(None)))
    r = TestClient(app).get("/trial/status", params={"email": "none@x.com"})
    assert r.json()["status"] == "unknown"

def test_get_status_bad_email_400():
    r = TestClient(app).get("/trial/status", params={"email": "bad"})
    assert r.status_code == 400


class _CapturingStore:
    """get_status 에 전달된 키를 기록하는 fake store — I1 소문자화 검증용."""
    def __init__(self):
        self.queried: list[str] = []

    def get_status(self, email: str) -> dict:
        self.queried.append(email)
        return {"status": "generating"}


def test_trial_status_lowercases_email_before_lookup(monkeypatch):
    """I1: 대소문자 혼합 이메일이 소문자로 변환된 뒤 store 에 전달돼야 한다."""
    store = _CapturingStore()
    monkeypatch.setattr(appmod, "_status_store", lambda: store)
    r = TestClient(app).get("/trial/status", params={"email": "Moongons@Amazon.com"})
    assert r.status_code == 200
    assert store.queried == ["moongons@amazon.com"]
