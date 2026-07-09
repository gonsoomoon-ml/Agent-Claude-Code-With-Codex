from briefing.scheduler.sent_log import DynamoSentLog


class _FakeTable:
    def __init__(self): self.items = []
    def put_item(self, Item): self.items.append(Item)


def test_mark_sent_backward_compatible_without_record():
    t = _FakeTable()
    DynamoSentLog(t).mark_sent("u1", "2026-07-08")
    assert t.items == [{"user_id": "u1", "run_date": "2026-07-08"}]


def test_mark_sent_merges_audit_record():
    t = _FakeTable()
    DynamoSentLog(t).mark_sent("u1", "2026-07-08",
                               record={"published": 5, "status": "sent"})
    assert t.items[0] == {"user_id": "u1", "run_date": "2026-07-08",
                          "published": 5, "status": "sent"}
