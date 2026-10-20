"""get_meta(dedup 용 메타 일괄 조회) + DynamoLedger.query pagination — 오프라인(가짜 테이블, AWS 없음)."""
from types import SimpleNamespace

from briefing.core.stores.source_store import SourceMeta, SourceStore


def test_local_get_meta_returns_meta_and_skips_missing(tmp_path):
    store = SourceStore(str(tmp_path))
    fs = store.freeze(url="https://x.com/a", title="T", raw_text="본문", fetched_at="2026-10-01", media="X")
    got = store.get_meta([fs.source_id, "missing-id", fs.source_id])
    assert got == {fs.source_id: SourceMeta(url="https://x.com/a", title="T", media="X")}


class _FakeClient:
    """batch_get_item 응답을 순서대로 내주는 가짜 resource client — 요청·응답 모두 파이썬 값(boto3 가 변환한 뒤의 모양).

    저수준 타입({"S": ...})을 쓰면 안 된다 — 운영 `Table.meta.client` 와 다른 가정이라 2026-10 버그를 숨겼다.
    """

    def __init__(self, pages):
        self.pages, self.requests = list(pages), []

    def batch_get_item(self, RequestItems):  # noqa: N803 — boto3 인자명 그대로
        self.requests.append(RequestItems)
        return self.pages.pop(0)


def _dynamo_store(client):
    from briefing.core.stores.dynamo import DynamoSourceStore
    s = object.__new__(DynamoSourceStore)          # boto3 연결 없이 — _t 만 가짜로
    s._t = SimpleNamespace(name="tbl", meta=SimpleNamespace(client=client))
    return s


def _item(sid, url="https://x.com/a", title="T", media="X"):
    return {"source_id": sid, "url": url, "title": title, "media": media}


def test_dynamo_get_meta_batches_by_100_and_follows_unprocessed(monkeypatch):
    from briefing.core.stores import dynamo
    monkeypatch.setattr(dynamo.time, "sleep", lambda _s: None)
    ids = [f"s{i}" for i in range(150)]
    client = _FakeClient([
        {"Responses": {"tbl": [_item(f"s{i}") for i in range(99)]},
         "UnprocessedKeys": {"tbl": {"Keys": [{"source_id": "s99"}]}}},
        {"Responses": {"tbl": [_item("s99")]}},
        {"Responses": {"tbl": [_item(f"s{i}") for i in range(100, 150)]}},
    ])
    got = _dynamo_store(client).get_meta(ids)
    assert len(got) == 150 and got["s99"] == SourceMeta(url="https://x.com/a", title="T", media="X")
    assert [len(r["tbl"]["Keys"]) for r in client.requests] == [100, 1, 50]
    assert client.requests[0]["tbl"]["ExpressionAttributeNames"]["#u"] == "url"   # url 은 예약어 → placeholder


def test_dynamo_get_meta_gives_up_after_rounds_and_warns(monkeypatch, capsys):
    from briefing.core.stores import dynamo
    monkeypatch.setattr(dynamo.time, "sleep", lambda _s: None)
    stuck = {"Responses": {"tbl": []}, "UnprocessedKeys": {"tbl": {"Keys": [{"source_id": "s0"}]}}}
    client = _FakeClient([stuck] * dynamo._BATCH_GET_ROUNDS)
    assert _dynamo_store(client).get_meta(["s0"]) == {}          # 죽지 않고 미해결로 진행(fail-open)
    assert "미처리" in capsys.readouterr().err


def test_dynamo_get_meta_through_real_resource_client():
    """★ 2026-10-20 회귀 — 진짜 boto3 resource 의 client 로 왕복한다(Stubber, 네트워크 없음).

    `Table.meta.client` 는 저수준 client 가 아니다: boto3 가 파이썬 값 ↔ DynamoDB 타입을 자동 변환한다.
    예전 코드는 {"S": sid} 를 넘겨 한 번 더 감싸졌고(→ Map) 운영 DDB 가 ValidationException
    ("key element does not match the schema") → published_keys 예외 → dedup 전체가 매 run 꺼졌다.
    가짜 client 테스트는 그 잘못된 가정을 그대로 품고 있어 통과했다 — 그래서 실물 client 로 검사한다.
    """
    import boto3
    from botocore.stub import Stubber

    from briefing.core.stores.dynamo import DynamoSourceStore
    table = boto3.resource("dynamodb", region_name="us-east-1",
                           aws_access_key_id="x", aws_secret_access_key="x").Table("tbl")
    store = object.__new__(DynamoSourceStore)
    store._t = table
    wire = {"source_id": {"S": "s1"}, "url": {"S": "https://x.com/a"}, "title": {"S": "T"}, "media": {"S": "X"}}
    with Stubber(table.meta.client) as stub:
        stub.add_response(
            "batch_get_item", {"Responses": {"tbl": [wire]}},
            {"RequestItems": {"tbl": {
                "Keys": [{"source_id": "s1"}],                       # 파이썬 값 그대로 — 변환은 boto3 몫
                "ProjectionExpression": "#s, #u, #t, #m",
                "ExpressionAttributeNames": {"#s": "source_id", "#u": "url", "#t": "title", "#m": "media"},
            }}},
        )
        assert store.get_meta(["s1"]) == {"s1": SourceMeta(url="https://x.com/a", title="T", media="X")}


def test_dynamo_ledger_query_follows_pages():
    from briefing.core.stores.dynamo import DynamoLedger
    calls = []

    def fake_query(**kw):
        calls.append(kw)
        if "ExclusiveStartKey" not in kw:
            return {"Items": [{"run_date": "2026-10-01", "user_id": "u", "source_id": "a", "decision": "PUBLISH"}],
                    "LastEvaluatedKey": {"user_id": "u", "sk": "2026-10-01#a"}}
        return {"Items": [{"run_date": "2026-10-02", "user_id": "u", "source_id": "b", "decision": "PUBLISH"}]}

    led = object.__new__(DynamoLedger)
    led._t = SimpleNamespace(query=fake_query)
    rows = led.query("u", since_date="2026-07-18")
    assert [r["source_id"] for r in rows] == ["a", "b"]           # 두 번째 페이지까지 읽음
    assert calls[1]["ExclusiveStartKey"] == {"user_id": "u", "sk": "2026-10-01#a"}
