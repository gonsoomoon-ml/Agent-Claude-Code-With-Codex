"""scheduler(⑤)의 *순수·테스트가능* 단위 — AWS·네트워크 0.

검증 대상(결정론):
  - due.users_due_now : 타임존 due-check (시간당 tick → 지금 due 인 사용자만; per-user 규칙 X)
  - deliver.*         : SES DeliverFn (QUARANTINE/빈 발행은 미발송) — fake 로 검증
  - dispatch.dispatch : due → run_briefing → deliver (중복발송 dedup seam)
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace


def _u(uid: str, send_hour: int, tz: str) -> SimpleNamespace:
    return SimpleNamespace(id=uid, send_hour=send_hour, timezone=tz)


# ───────────────────────── C6 users_due_now (타임존 due-check) ─────────────────────────

def test_users_due_now_matches_local_send_hour():
    from briefing.scheduler.due import users_due_now

    # 07:00 KST = 22:00 UTC (전날) — KST=UTC+9. send_hour 는 *사용자 로컬* 기준.
    now = datetime(2026, 6, 27, 22, 0, tzinfo=timezone.utc)
    users = [_u("seoul7", 7, "Asia/Seoul"), _u("seoul8", 8, "Asia/Seoul")]
    assert [u.id for u in users_due_now(users, now)] == ["seoul7"]   # 07:00 KST 만 due


def test_users_due_now_not_due_on_off_hour():
    from briefing.scheduler.due import users_due_now

    now = datetime(2026, 6, 27, 21, 0, tzinfo=timezone.utc)          # KST 06:00 — 1시간 이르다
    assert users_due_now([_u("seoul7", 7, "Asia/Seoul")], now) == []


def test_users_due_now_handles_multiple_timezones_in_one_tick():
    from briefing.scheduler.due import users_due_now

    # 12:00 UTC (2026-06-27, 여름): NY(EDT,UTC-4)=08, London(BST,UTC+1)=13, Seoul(UTC+9)=21
    now = datetime(2026, 6, 27, 12, 0, tzinfo=timezone.utc)
    users = [
        _u("ny8", 8, "America/New_York"),
        _u("ldn13", 13, "Europe/London"),
        _u("seoul21", 21, "Asia/Seoul"),
        _u("ldn9", 9, "Europe/London"),     # 13시인데 9 원함 → not due
    ]
    assert {u.id for u in users_due_now(users, now)} == {"ny8", "ldn13", "seoul21"}


def test_users_due_now_treats_naive_now_as_utc():
    from briefing.scheduler.due import users_due_now

    naive = datetime(2026, 6, 27, 22, 0)                            # tzinfo 없음 → UTC 로 간주
    assert [u.id for u in users_due_now([_u("seoul7", 7, "Asia/Seoul")], naive)] == ["seoul7"]


# ───────────────────────── C5 deliver (SES — 발송 게이트) ─────────────────────────

def _briefing(recipient, email, published, quarantined=0):
    return SimpleNamespace(user_id="u", recipient=recipient, email=email,
                           published=published, quarantined=quarantined)


def test_should_deliver_only_when_published():
    from briefing.scheduler.deliver import should_deliver

    assert should_deliver(_briefing("a@x.com", "<h1>hi</h1>", published=1))
    assert not should_deliver(_briefing("a@x.com", "", published=0, quarantined=1))  # QUARANTINE-only
    assert not should_deliver(_briefing("a@x.com", "", published=0))                 # 빈 발행


class _FakeSES:
    def __init__(self):
        self.sent: list[dict] = []

    def send_email(self, **kw):
        self.sent.append(kw)
        return {"MessageId": "fake"}


def test_ses_deliver_sends_publishable_with_correct_envelope():
    from briefing.scheduler.deliver import make_ses_deliver

    ses = _FakeSES()
    settings = SimpleNamespace(ses_sender="briefing@example.com", region="us-east-1")
    deliver = make_ses_deliver(settings, client=ses)

    deliver(_briefing("alice@example.com", "<h1>아침 브리핑</h1>", published=2))
    assert len(ses.sent) == 1
    msg = ses.sent[0]
    assert msg["Source"] == "briefing@example.com"
    assert msg["Destination"]["ToAddresses"] == ["alice@example.com"]
    assert "아침 브리핑" in msg["Message"]["Body"]["Html"]["Data"]


def test_ses_deliver_skips_quarantine_and_empty():
    from briefing.scheduler.deliver import make_ses_deliver

    ses = _FakeSES()
    deliver = make_ses_deliver(SimpleNamespace(ses_sender="b@x.com", region="us-east-1"), client=ses)
    deliver(_briefing("a@x.com", "", published=0, quarantined=1))   # 미발송
    deliver(_briefing("a@x.com", "", published=0))                  # 미발송
    assert ses.sent == []


# ───────────────────────── dispatch (due → run_briefing → deliver) ─────────────────────────

def _full_user(uid, send_hour, tz, sources=("aws-ml",)):
    return SimpleNamespace(id=uid, recipient=f"{uid}@example.com", type="ai-news",
                           sources=tuple(sources), depth="full", lens="general",
                           skill_md="", send_hour=send_hour, timezone=tz)


def _fetch(source, _w):
    from briefing.shared.sources import FetchedArticle
    return [FetchedArticle(source.key, "https://x", "제목", "직원 약 100명.", "2026-06-27T00:00:00Z")]


def _draft(*_a):
    from briefing.shared.author import Claim, DraftCard
    return DraftCard("sid", "헤드라인", "요약", "왜중요",
                     (Claim("C1", "직원이 100명이다.", "arithmetic", "core"),))


def _verify(_card):
    from briefing.shared.certifier import CertVerdict
    return (CertVerdict("C1", "VERIFIED", "ev"),)


_NOW_KST7 = datetime(2026, 6, 27, 22, 0, tzinfo=timezone.utc)   # = 07:00 KST


def test_dispatch_delivers_only_due_publishable_users(tmp_path):
    from briefing.scheduler.dispatch import dispatch
    from briefing.shared.source_store import SourceStore

    store = SourceStore(str(tmp_path / "store"))
    users = [_full_user("seoul7", 7, "Asia/Seoul"), _full_user("seoul8", 8, "Asia/Seoul")]
    delivered: list[str] = []
    out = dispatch(SimpleNamespace(), store, users, _NOW_KST7,
                   deliver_fn=lambda b: delivered.append(b.user_id),
                   fetch_article_fn=_fetch, draft_fn=_draft, verify_fn=_verify)
    assert out == ["seoul7"]          # 07:00 KST 인 seoul7 만 due
    assert delivered == ["seoul7"]    # 정확히 1회 발송


def test_dispatch_noop_when_nobody_due(tmp_path):
    from briefing.scheduler.dispatch import dispatch
    from briefing.shared.source_store import SourceStore

    store = SourceStore(str(tmp_path / "store"))
    delivered: list[str] = []
    out = dispatch(SimpleNamespace(), store, [_full_user("seoul8", 8, "Asia/Seoul")], _NOW_KST7,
                   deliver_fn=lambda b: delivered.append(b.user_id),
                   fetch_article_fn=_fetch, draft_fn=_draft, verify_fn=_verify)
    assert out == [] and delivered == []   # due 0 → run_briefing/deliver 호출 안 함


def test_dispatch_dedups_already_sent(tmp_path):
    from briefing.scheduler.dispatch import dispatch
    from briefing.shared.source_store import SourceStore

    class SentLog:
        def __init__(self):
            self.marks: set[tuple[str, str]] = set()

        def already_sent(self, uid, rd):
            return (uid, rd) in self.marks

        def mark_sent(self, uid, rd):
            self.marks.add((uid, rd))

    store = SourceStore(str(tmp_path / "store"))
    log = SentLog()
    log.mark_sent("seoul7", "2026-06-27")          # 이미 발송됨(같은 run_date)
    delivered: list[str] = []
    out = dispatch(SimpleNamespace(), store, [_full_user("seoul7", 7, "Asia/Seoul")], _NOW_KST7,
                   deliver_fn=lambda b: delivered.append(b.user_id), run_date="2026-06-27",
                   sent_log=log, fetch_article_fn=_fetch, draft_fn=_draft, verify_fn=_verify)
    assert out == [] and delivered == []           # 중복 발송 방지


# ───────────────────────── sent_log (DDB dedup — fake table DI) ─────────────────────────

class _FakeTable:
    """boto3 dynamodb Table 의 최소 모킹 (get_item/put_item) — sent_log 단위 테스트용."""
    def __init__(self):
        self.items: dict[tuple, dict] = {}

    def get_item(self, Key):  # noqa: N803 (boto3 시그니처)
        k = (Key["user_id"], Key["run_date"])
        return {"Item": self.items[k]} if k in self.items else {}

    def put_item(self, Item):  # noqa: N803
        self.items[(Item["user_id"], Item["run_date"])] = Item


def test_dynamo_sent_log_marks_and_detects():
    from briefing.scheduler.sent_log import DynamoSentLog

    log = DynamoSentLog(_FakeTable())
    assert not log.already_sent("gonsoo", "2026-06-27")
    log.mark_sent("gonsoo", "2026-06-27")
    assert log.already_sent("gonsoo", "2026-06-27")
    assert not log.already_sent("gonsoo", "2026-06-28")   # 다른 날 = 미발송
    log.mark_sent("gonsoo", "2026-06-27")                 # 재마크 멱등
    assert log.already_sent("gonsoo", "2026-06-27")


def test_dynamo_sent_log_dedups_through_dispatch(tmp_path):
    from briefing.scheduler.dispatch import dispatch
    from briefing.scheduler.sent_log import DynamoSentLog
    from briefing.shared.source_store import SourceStore

    store = SourceStore(str(tmp_path / "store"))
    log = DynamoSentLog(_FakeTable())
    user = [_full_user("seoul7", 7, "Asia/Seoul")]
    common = dict(deliver_fn=lambda b: None, run_date="2026-06-27", sent_log=log,
                  fetch_article_fn=_fetch, draft_fn=_draft, verify_fn=_verify)
    assert dispatch(SimpleNamespace(), store, user, _NOW_KST7, **common) == ["seoul7"]   # 첫 발송
    assert dispatch(SimpleNamespace(), store, user, _NOW_KST7, **common) == []           # 재실행 dedup


# ───────────────────────── lambda_handler (얇은 fire-and-return poker) ─────────────────────────

class _FakeAgentCore:
    """boto3 bedrock-agentcore 클라이언트 모킹 — invoke_agent_runtime + SSE 스트림."""
    def __init__(self, lines: list[bytes]):
        self._lines = lines
        self.calls: list[dict] = []

    def invoke_agent_runtime(self, **kw):
        self.calls.append(kw)
        return {"contentType": "text/event-stream",
                "response": SimpleNamespace(iter_lines=lambda chunk_size=1: iter(self._lines))}


def test_lambda_handler_invokes_scheduled_and_reports_accepted(monkeypatch):
    monkeypatch.setenv("BRIEFING_RUNTIME_ARN", "arn:aws:bedrock-agentcore:us-east-1:1:runtime/briefing_agent-x")
    monkeypatch.setenv("BRIEFING_DRY_RUN", "1")
    from briefing.scheduler import lambda_handler as lh

    import json as _json
    fake = _FakeAgentCore([b'data: {"type": "accepted", "mode": "scheduled", "users": 1}'])
    out = lh.handler({}, None, client=fake)

    assert out["ok"] is True and out["accepted"] is True and out["dry_run"] is True
    kw = fake.calls[0]
    assert kw["agentRuntimeArn"].endswith("briefing_agent-x") and kw["qualifier"] == "DEFAULT"
    assert len(kw["runtimeSessionId"]) >= 33                       # AgentCore 제약
    assert _json.loads(kw["payload"]) == {"mode": "scheduled", "dry_run": True}


def test_lambda_handler_accepted_false_when_no_accept_event(monkeypatch):
    monkeypatch.setenv("BRIEFING_RUNTIME_ARN", "arn:aws:bedrock-agentcore:us-east-1:1:runtime/x")
    monkeypatch.delenv("BRIEFING_DRY_RUN", raising=False)          # 기본 dry-run
    from briefing.scheduler import lambda_handler as lh

    out = lh.handler({}, None, client=_FakeAgentCore([b'data: {"type": "stage"}', b""]))
    assert out["accepted"] is False and out["dry_run"] is True     # 미설정 시 dry-run 기본
