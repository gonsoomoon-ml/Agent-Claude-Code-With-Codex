"""Test deliver returns SES response."""
from briefing.scheduler.deliver import make_ses_deliver


class _FakeSES:
    def send_email(self, **kw):
        return {"MessageId": "MID-1"}


def _briefing(pub):
    return type("B", (), {"recipient": "a@x.com", "email": "<p>", "published": pub})()


def test_deliver_returns_ses_response_when_published():
    d = make_ses_deliver(type("S", (), {"ses_sender": "s@x.com", "region": "r"})(),
                         client=_FakeSES())
    assert d(_briefing(3)) == {"MessageId": "MID-1"}


def test_deliver_returns_none_when_nothing_published():
    d = make_ses_deliver(type("S", (), {"ses_sender": "s@x.com", "region": "r"})(),
                         client=_FakeSES())
    assert d(_briefing(0)) is None
