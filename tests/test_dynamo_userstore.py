"""DynamoUserStore.update_profile_from_jwt — IDOR-safe(PK=sub·recipient=email 인자에서만)."""
from __future__ import annotations

from briefing.core.stores.dynamo import DynamoUserStore


class _FakeTable:
    def __init__(self): self.updates = []
    def update_item(self, **kw): self.updates.append(kw)


def _store():
    s = DynamoUserStore.__new__(DynamoUserStore)
    s._t = _FakeTable()
    return s


def test_keys_on_sub_recipient_on_email_ignores_body_identity():
    s = _store()
    s.update_profile_from_jwt(sub="SUB-1", email="me@x.com",
                              fields={"user_id": "EVIL", "recipient": "victim@x.com",
                                      "sources": ["aitimes"], "send_hour": 8, "type": "ai-news"})
    up = s._t.updates[0]
    assert up["Key"] == {"user_id": "SUB-1"}                      # body user_id 무시
    vals = up["ExpressionAttributeValues"]
    assert ":r" in up["ExpressionAttributeValues"] or any(v == "me@x.com" for v in vals.values())
    assert "victim@x.com" not in vals.values()                   # body recipient 무시
    assert "EVIL" not in str(up["Key"])
    # type 은 DDB 예약어 → ExpressionAttributeNames 로 우회(직접 'type' 토큰 없음)
    assert "type" not in up.get("UpdateExpression", "").replace("#", "")
    assert ["aitimes"] in vals.values() and 8 in vals.values()   # sources list, send_hour int
