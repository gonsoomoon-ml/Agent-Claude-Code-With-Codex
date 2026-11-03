"""weekly.issues — 상태 전이 · 중복 발송 거부 · force · DDB 조건식(로컬 파일 + fake 테이블, 네트워크 0)."""
import pytest

from briefing.weekly.issues import DynamoIssueStore, LocalIssueStore, TransitionError

D = "2026-11-07"


def test_local_happy_path_and_fields_merge(tmp_path):
    s = LocalIssueStore(str(tmp_path))
    assert s.get(D) is None
    s.transition(D, "building")
    s.transition(D, "ready", issue_md="# t", gate_json="{}")
    s.transition(D, "sending")
    item = s.transition(D, "sent", message_id="m-1")
    assert item["status"] == "sent" and item["issue_md"] == "# t" and item["message_id"] == "m-1"
    assert s.get(D)["status"] == "sent"


def test_second_send_is_refused(tmp_path):
    s = LocalIssueStore(str(tmp_path))
    s.transition(D, "building")
    s.transition(D, "quarantined", issue_md="# t")     # 1단계: 격리 호도 보낼 수 있다
    s.transition(D, "sending")
    with pytest.raises(TransitionError):
        s.transition(D, "sending")                      # 07:00 send 가 두 번 돌아도 한 번만
    s.transition(D, "sent")
    with pytest.raises(TransitionError):
        s.transition(D, "building")                     # 보낸 호는 다시 만들지 않는다
    with pytest.raises(TransitionError):
        s.transition(D, "building", force=True)         # force 도 sent 는 못 바꾼다


def test_failed_build_can_rebuild_and_cannot_send(tmp_path):
    s = LocalIssueStore(str(tmp_path))
    s.transition(D, "building")
    s.transition(D, "failed", error="author timeout")
    with pytest.raises(TransitionError):
        s.transition(D, "sending")
    s.transition(D, "building")
    with pytest.raises(TransitionError):
        s.transition(D, "building")                     # 동시 build 거부(멈춘 building 은 force 로)
    assert s.transition(D, "building", force=True)["status"] == "building"


class _CondFail(Exception):
    response = {"Error": {"Code": "ConditionalCheckFailedException"}}


class _FakeTable:
    def __init__(self, fail: bool = False):
        self.calls, self.fail = [], fail

    def update_item(self, **kw):
        self.calls.append(kw)
        if self.fail:
            raise _CondFail()
        return {"Attributes": {"issue_date": kw["Key"]["issue_date"], "status": kw["ExpressionAttributeValues"][":to"]}}


def test_dynamo_condition_expression():
    t = _FakeTable()
    DynamoIssueStore(t).transition(D, "sending", subject="[현장 실험] x")
    kw = t.calls[0]
    assert kw["ConditionExpression"] == "#s IN (:a0, :a1)"
    assert {kw["ExpressionAttributeValues"][":a0"], kw["ExpressionAttributeValues"][":a1"]} == {"ready", "quarantined"}
    assert "#s = :to" in kw["UpdateExpression"] and "subject" in kw["ExpressionAttributeNames"].values()
    DynamoIssueStore(t).transition(D, "building")
    assert t.calls[1]["ConditionExpression"].startswith("attribute_not_exists(issue_date) OR #s IN (")


def test_dynamo_condition_failure_becomes_transition_error():
    with pytest.raises(TransitionError):
        DynamoIssueStore(_FakeTable(fail=True)).transition(D, "sending")
