"""runtime._trial — build_trial_user / poll_verified / run_trial (DI, fake ses·run_briefing)."""
from __future__ import annotations

import dataclasses

from briefing.runtime._trial import build_trial_user, poll_verified, run_trial
from briefing.core.config import load_settings


def _settings():
    return dataclasses.replace(load_settings(), ses_sender="s@x.com")


def test_build_trial_user_has_all_9_fields():
    u = build_trial_user({"email": "U@X.com", "sources": ["aitimes"], "lens": "engineer"}, _settings())
    assert u.recipient == "U@X.com" and u.sources == ("aitimes",) and u.lens == "engineer"
    assert u.send_hour == 0 and u.timezone == "Asia/Seoul" and u.depth == "summary"
    assert u.skill_md == "" and u.type == "ai-news" and u.id.startswith("trial-")


class _Ses:
    def __init__(self, success_on): self.n, self.success_on = 0, success_on
    def get_identity_verification_attributes(self, Identities):
        self.n += 1
        st = "Success" if self.n >= self.success_on else "Pending"
        return {"VerificationAttributes": {Identities[0]: {"VerificationStatus": st}}}


def test_poll_verified_true_when_success_within_attempts():
    assert poll_verified(_Ses(success_on=3), "u@x.com", attempts=5, sleep_seconds=0, sleep_fn=lambda s: None)


def test_poll_verified_false_on_timeout():
    assert not poll_verified(_Ses(success_on=99), "u@x.com", attempts=3, sleep_seconds=0, sleep_fn=lambda s: None)


class _Brief:
    def __init__(self, published): self.published, self.recipient, self.email = published, "u@x.com", "<p>"


def test_run_trial_delivers_when_verified_and_published():
    delivered, fellback = [], []
    out = run_trial(_settings(), object(), None, {"email": "u@x.com", "sources": ["aitimes"]},
                    ses=_Ses(success_on=1), run_briefing_fn=lambda *a, **k: [_Brief(3)],
                    deliver_fn=lambda b: delivered.append(b), fallback_fn=lambda e: fellback.append(e),
                    sleep_fn=lambda s: None, run_date="2026-06-28")
    assert delivered and not fellback and "delivered" in out


def test_run_trial_fallback_when_published_zero():
    delivered, fellback = [], []
    run_trial(_settings(), object(), None, {"email": "u@x.com", "sources": ["aitimes"]},
              ses=_Ses(success_on=1), run_briefing_fn=lambda *a, **k: [_Brief(0)],
              deliver_fn=lambda b: delivered.append(b), fallback_fn=lambda e: fellback.append(e),
              sleep_fn=lambda s: None, run_date="2026-06-28")
    assert fellback == ["u@x.com"] and not delivered


def test_run_trial_no_send_on_verify_timeout():
    delivered, fellback, ran = [], [], []
    run_trial(_settings(), object(), None, {"email": "u@x.com", "sources": ["aitimes"]},
              ses=_Ses(success_on=99), run_briefing_fn=lambda *a, **k: ran.append(1) or [_Brief(3)],
              deliver_fn=lambda b: delivered.append(b), fallback_fn=lambda e: fellback.append(e),
              sleep_fn=lambda s: None, run_date="2026-06-28", attempts=2)
    assert not ran and not delivered and not fellback   # 미검증 → 생성/발송 0


def test_run_trial_status_fn_sequence_on_delivered():
    seen = []
    run_trial(_settings(), object(), None, {"email": "u@x.com", "sources": ["aitimes"]},
              ses=_Ses(success_on=1), run_briefing_fn=lambda *a, **k: [_Brief(3)],
              deliver_fn=lambda b: None, fallback_fn=lambda e: None,
              sleep_fn=lambda s: None, run_date="2026-06-28",
              status_fn=lambda s, p=None: seen.append((s, p)))
    assert ("generating", None) in seen and ("sent", 3) in seen


def test_run_trial_status_fallback_and_expired():
    seen = []
    run_trial(_settings(), object(), None, {"email": "u@x.com", "sources": ["aitimes"]},
              ses=_Ses(success_on=1), run_briefing_fn=lambda *a, **k: [_Brief(0)],
              deliver_fn=lambda b: None, fallback_fn=lambda e: None, sleep_fn=lambda s: None,
              run_date="2026-06-28", status_fn=lambda s, p=None: seen.append((s, p)))
    assert ("fallback", None) in seen
    seen.clear()
    run_trial(_settings(), object(), None, {"email": "u@x.com", "sources": ["aitimes"]},
              ses=_Ses(success_on=99), run_briefing_fn=lambda *a, **k: [_Brief(3)],
              deliver_fn=lambda b: None, fallback_fn=lambda e: None, sleep_fn=lambda s: None,
              run_date="2026-06-28", attempts=2, status_fn=lambda s, p=None: seen.append((s, p)))
    assert ("expired", None) in seen
