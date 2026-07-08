"""dispatch — 발송 시 audit 레코드(비용·시간·기사수·MessageId) sent_log 기록 (admin-monitoring Task 7).

검증 대상: `dispatch()` 가 실 발송(deliver_fn 응답 있음) 시 sent_log.mark_sent 에 record= 로
{sent_at, recipient, published, quarantined, duration_ms, cost_usd(Decimal), status, message_id} 를 넘기는지.
"""
from __future__ import annotations

from datetime import datetime, timezone

from briefing.scheduler.dispatch import dispatch


class _SentLog:
    def __init__(self):
        self.records = {}

    def already_sent(self, uid, rd):
        return False

    def mark_sent(self, uid, rd, *, record=None):
        self.records[uid] = record


def _briefing(uid, pub):
    return type("B", (), {"user_id": uid, "recipient": f"{uid}@x.com", "email": "<p>",
                          "published": pub, "quarantined": 0, "cost_usd": 1.08,
                          "duration_ms": 662000})()


def test_dispatch_writes_audit_record_on_send(monkeypatch):
    import briefing.scheduler.dispatch as d
    monkeypatch.setattr(d, "users_due_now", lambda users, now, **k: users)
    monkeypatch.setattr(d, "run_briefing", lambda *a, **k: [_briefing("u1", 5)])
    sent = _SentLog()
    now = datetime(2026, 7, 8, 7, 0, 12, tzinfo=timezone.utc)
    dispatch(None, None, ["u1"], now, deliver_fn=lambda b: {"MessageId": "MID-9"},
             run_date="2026-07-08", sent_log=sent)
    r = sent.records["u1"]
    assert r["status"] == "sent" and r["message_id"] == "MID-9"
    assert r["published"] == 5 and r["duration_ms"] == 662000
    assert r["recipient"] == "u1@x.com" and r["sent_at"] == "2026-07-08T07:00:12+00:00"
    assert float(r["cost_usd"]) == 1.08     # Decimal 로 저장됨
