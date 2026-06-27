"""backends — make_stores(settings.backend) 가 local/dynamo 별로 일관된 세 store 를 반환."""
from types import SimpleNamespace

from briefing.shared.backends import make_stores
from briefing.shared.cache import LocalCardCache
from briefing.shared.ledger import LocalLedger
from briefing.shared.source_store import SourceStore


def _settings(backend, tmp):
    return SimpleNamespace(
        backend=backend,
        source_store_path=str(tmp / "s"), cache_path=str(tmp / "c"), ledger_path=str(tmp / "l"),
        region="us-east-1", cache_table="t", ledger_table="t", source_table="t", ddb_endpoint_url="",
    )


def test_make_stores_local(tmp_path):
    store, cache, ledger = make_stores(_settings("local", tmp_path))
    assert isinstance(store, SourceStore)
    assert isinstance(cache, LocalCardCache)
    assert isinstance(ledger, LocalLedger)


def test_make_stores_dynamo(tmp_path):
    # boto3 resource/Table 생성은 lazy(네트워크 0) — 타입 선택만 검증(region 제공돼 NoRegionError 없음).
    from briefing.shared.dynamo import DynamoCardCache, DynamoLedger, DynamoSourceStore
    store, cache, ledger = make_stores(_settings("dynamo", tmp_path))
    assert isinstance(store, DynamoSourceStore)
    assert isinstance(cache, DynamoCardCache)
    assert isinstance(ledger, DynamoLedger)
