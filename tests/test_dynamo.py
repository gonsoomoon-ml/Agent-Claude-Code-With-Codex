"""dynamo — DDB 백엔드 통합테스트 (guarded). DynamoDB Local 이 떠 있고 DDB_ENDPOINT_URL 설정 시만 실행.

무료 로컬 경로: docker run -p 8000:8000 amazon/dynamodb-local
  → DDB_ENDPOINT_URL=http://localhost:8000 uv run pytest tests/test_dynamo.py
실 AWS(과금)는 scripts/ddb_smoke.py 로. 기본 `uv run pytest` 에선 skip(자격증명·과금 없음).
"""
import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.getenv("DDB_ENDPOINT_URL"),
    reason="DDB 통합테스트 — DynamoDB Local(DDB_ENDPOINT_URL) 설정 시만 실행",
)


def _ensure(ddb, name, keys):
    if name in [t.name for t in ddb.tables.all()]:
        return
    ddb.create_table(
        TableName=name, BillingMode="PAY_PER_REQUEST",
        AttributeDefinitions=[{"AttributeName": k, "AttributeType": "S"} for k, _ in keys],
        KeySchema=[{"AttributeName": k, "KeyType": t} for k, t in keys],
    ).wait_until_exists()


@pytest.fixture
def backends():
    import boto3

    from briefing.shared.stores.dynamo import DynamoCardCache, DynamoLedger, DynamoSourceStore
    ep = os.environ["DDB_ENDPOINT_URL"]
    ddb = boto3.resource("dynamodb", endpoint_url=ep, region_name="us-east-1",
                         aws_access_key_id="local", aws_secret_access_key="local")
    _ensure(ddb, "test-card-cache", [("cache_key", "HASH")])
    _ensure(ddb, "test-ledger", [("user_id", "HASH"), ("sk", "RANGE")])
    _ensure(ddb, "test-source-store", [("source_id", "HASH")])
    return (DynamoCardCache("test-card-cache", region="us-east-1", endpoint_url=ep),
            DynamoLedger("test-ledger", region="us-east-1", endpoint_url=ep),
            DynamoSourceStore("test-source-store", region="us-east-1", endpoint_url=ep))


def test_dynamo_cache_roundtrip(backends):
    cache, _, _ = backends
    from briefing.shared.harness.author import Claim, DraftCard
    from briefing.shared.stores.cache import card_key
    from briefing.shared.harness.certifier import CertVerdict
    from briefing.shared.gate import GatedCard
    g = GatedCard(DraftCard("S1", "헤드라인", "요약", "왜", (Claim("C1", "x", "arithmetic", "core"),)),
                  (CertVerdict("C1", "VERIFIED", "ev", "deterministic"),), "PUBLISH", 1)
    k = card_key("S1", "engineer", "", "m")
    assert cache.get(k) is None          # miss
    cache.put(k, g)
    assert cache.get(k) == g             # hit → 무손실(같은 _serialize/_deserialize)


def test_dynamo_ledger_query(backends):
    _, ledger, _ = backends
    ledger.append("2026-06-20", "u-int", "S1", "k1", "PUBLISH", "월")
    ledger.append("2026-06-27", "u-int", "S2", "k2", "QUARANTINE", "금")
    assert len(ledger.query("u-int")) == 2                  # SK 오름차순 = 시간순
    recent = ledger.query("u-int", since_date="2026-06-25")
    assert len(recent) == 1 and recent[0]["headline"] == "금"   # SK range 필터


def test_dynamo_source_roundtrip(backends):
    _, _, store = backends
    fs = store.freeze(url="https://www.aitimes.com/x", title="t", raw_text="같은 정본 텍스트",
                      fetched_at="2026-06-27T00:00:00Z", media="AI Times")
    assert fs.media == "AI Times"
    assert store.get_source(fs.source_id) == fs                # 왕복 무손실
    dup = store.freeze(url="https://other/y", title="다른", raw_text="같은 정본 텍스트",
                       fetched_at="t2", media="다른매체")
    assert dup == fs                                           # content-addressed 불변 → 최초 동결본(media "AI Times")
