"""webapi.trial — 검증기·가드·handle_trial(순수/DI, fake boto3)."""
from __future__ import annotations


from briefing.webapi.trial import handle_trial, validate_trial

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
