"""webapi.trial — 검증기·가드·handle_trial(순수/DI, fake boto3)."""
from __future__ import annotations

import time

from briefing.webapi.trial import TrialStore, handle_trial, validate_trial, _parse_emails

CATALOG = ("aitimes", "openai", "anthropic")


def test_validate_rejects_bad_email():
    assert validate_trial("nope", ["aitimes"], CATALOG)


def test_validate_rejects_unknown_or_too_many_sources():
    assert validate_trial("a@b.com", ["ghost"], CATALOG)            # 미존재
    assert validate_trial("a@b.com", [], CATALOG)                   # 빈
    assert validate_trial("a@b.com", ["aitimes"] * 6, CATALOG)      # >5(중복이라도 길이)


def test_validate_ok():
    assert validate_trial("a@b.com", ["aitimes", "openai"], CATALOG) is None


class _FakeStore:
    def __init__(self, cooldown=False, over=False):
        self._cooldown, self._over, self.recorded = cooldown, over, []
    def within_cooldown(self, email): return self._cooldown
    def over_global_cap(self, date, cap): return self._over
    def record(self, email, status, *, ttl=0): self.recorded.append((email, status))


class _FakeSes:
    def __init__(self, verified=False):
        self._verified, self.verified_calls = verified, []
    def get_identity_verification_attributes(self, Identities):
        st = "Success" if self._verified else "Pending"
        return {"VerificationAttributes": {Identities[0]: {"VerificationStatus": st}}}
    def verify_email_identity(self, EmailAddress):
        self.verified_calls.append(EmailAddress)


def _invoke_spy():
    calls = []
    def invoke(mode, payload): calls.append((mode, payload))
    invoke.calls = calls
    return invoke


def _ok_payload(**o):
    return {"email": "u@x.com", "sources": ["aitimes"], **o}


def test_handle_rejects_invalid():
    code, body = handle_trial(_ok_payload(email="bad"), store=_FakeStore(), ses=_FakeSes(),
                              runtime_invoke=_invoke_spy(), cap=50,
                              cooldown_s=3600, today="2026-06-28",
                              catalog_keys=CATALOG)
    assert code == 400


def test_handle_cooldown_and_cap_429():
    inv = _invoke_spy()
    code, _ = handle_trial(_ok_payload(), store=_FakeStore(cooldown=True), ses=_FakeSes(),
                           runtime_invoke=inv, cap=50, cooldown_s=3600,
                           today="d", catalog_keys=CATALOG)
    assert code == 429 and not inv.calls           # 쿨다운 → invoke 안 함
    code, _ = handle_trial(_ok_payload(), store=_FakeStore(over=True), ses=_FakeSes(),
                           runtime_invoke=inv, cap=50, cooldown_s=3600,
                           today="d", catalog_keys=CATALOG)
    assert code == 429 and not inv.calls           # cap 초과 → invoke 안 함


def test_handle_unverified_triggers_verify_and_pending():
    ses, inv, store = _FakeSes(verified=False), _invoke_spy(), _FakeStore()
    code, body = handle_trial(_ok_payload(), store=store, ses=ses, runtime_invoke=inv,
                              cap=50, cooldown_s=3600,
                              today="d", catalog_keys=CATALOG)
    assert code == 202 and body["status"] == "verification_pending"
    assert ses.verified_calls == ["u@x.com"]       # 검증 메일 트리거
    assert inv.calls and inv.calls[0][0] == "trial"  # runtime mode=trial invoke
    assert ("u@x.com", "verification_pending") in store.recorded


def test_handle_already_verified_skips_verify_sending():
    ses, inv = _FakeSes(verified=True), _invoke_spy()
    code, body = handle_trial(_ok_payload(), store=_FakeStore(), ses=ses, runtime_invoke=inv,
                              cap=50, cooldown_s=3600,
                              today="d", catalog_keys=CATALOG)
    assert code == 202 and body["status"] == "sending"
    assert ses.verified_calls == []                # 이미 검증 → verify skip
    assert inv.calls


# ── TrialStore.within_cooldown — I2 ttl 기반 쿨다운 ──────────────────────

class _FakeTable:
    """get_item 만 지원하는 최소 DDB 테이블 fake."""
    def __init__(self, item: dict | None):
        self._item = item

    def get_item(self, Key):
        return {"Item": self._item} if self._item else {}


def test_within_cooldown_true_when_ttl_in_future():
    """I2: ttl 이 미래이면 쿨다운 중(True)."""
    future_ttl = int(time.time()) + 3600
    store = TrialStore(_FakeTable({"email": "u@x.com", "status": "generating", "ttl": future_ttl}))
    assert store.within_cooldown("u@x.com") is True


def test_within_cooldown_false_when_ttl_in_past():
    """I2: ttl 이 과거이면 쿨다운 해제(False)."""
    past_ttl = int(time.time()) - 1
    store = TrialStore(_FakeTable({"email": "u@x.com", "status": "generating", "ttl": past_ttl}))
    assert store.within_cooldown("u@x.com") is False


def test_within_cooldown_false_when_no_item():
    """I2: 레코드 없으면 쿨다운 아님(False)."""
    store = TrialStore(_FakeTable(None))
    assert store.within_cooldown("new@x.com") is False


def test_within_cooldown_true_regardless_of_status():
    """I2: status 가 'generating' 이어도 ttl 이 미래이면 쿨다운 중 — status 기반 구현의 버그를 방지."""
    future_ttl = int(time.time()) + 100
    store = TrialStore(_FakeTable({"email": "u@x.com", "status": "generating", "ttl": future_ttl}))
    assert store.within_cooldown("u@x.com") is True


# ── v1.1e: TRIAL_TEST_EMAILS allowlist 쿨다운 우회 ──────────────────────

def test_allowlist_email_skips_cooldown():
    """allowlist 주소는 within_cooldown=True 여도 202(쿨다운 게이트 skip)."""
    inv = _invoke_spy()
    code, body = handle_trial(_ok_payload(), store=_FakeStore(cooldown=True),
                              ses=_FakeSes(verified=True), runtime_invoke=inv,
                              cap=50, cooldown_s=3600, today="d", catalog_keys=CATALOG,
                              test_emails=frozenset({"u@x.com"}))
    assert code == 202 and body["status"] == "sending"
    assert inv.calls and inv.calls[0][0] == "trial"   # 우회 후 정상 invoke


def test_non_allowlist_email_still_cooldown_429():
    """allowlist 가 비어있지 않아도 그 안에 없는 주소는 429(공개 가드 유지)."""
    inv = _invoke_spy()
    code, _ = handle_trial(_ok_payload(), store=_FakeStore(cooldown=True),
                           ses=_FakeSes(), runtime_invoke=inv,
                           cap=50, cooldown_s=3600, today="d", catalog_keys=CATALOG,
                           test_emails=frozenset({"other@x.com"}))
    assert code == 429 and not inv.calls


def test_allowlist_email_still_blocked_by_cap():
    """allowlist 우회는 쿨다운 한정 — 전역 cap 은 테스트 주소도 차단(절대 천장 유지)."""
    inv = _invoke_spy()
    code, _ = handle_trial(_ok_payload(), store=_FakeStore(over=True),
                           ses=_FakeSes(verified=True), runtime_invoke=inv,
                           cap=50, cooldown_s=3600, today="d", catalog_keys=CATALOG,
                           test_emails=frozenset({"u@x.com"}))
    assert code == 429 and not inv.calls


def test_parse_emails_normalizes():
    """쉼표 구분 → 소문자·trim·빈값 제거 frozenset; '' → frozenset()."""
    assert _parse_emails("A@x.com, b@y.com ,") == frozenset({"a@x.com", "b@y.com"})
    assert _parse_emails("") == frozenset()
    assert _parse_emails("  ") == frozenset()
