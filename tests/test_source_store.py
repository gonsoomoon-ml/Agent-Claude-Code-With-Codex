"""source_store — content-addressed source-of-record (결정론 신뢰 핵심)."""
import unicodedata

import pytest

from briefing.core.stores.source_store import SourceStore, content_id, media_from_url, normalize


def test_normalize_crlf_and_trailing_ws():
    assert normalize("a\r\nb\r\n") == "a\nb"
    assert normalize("  x  \n  y  ") == "x\n  y"  # 줄말미공백 정리 + 전체 양끝 strip


def test_normalize_nfc_unifies():
    nfd = unicodedata.normalize("NFD", "가나")  # 자모 분리형
    assert normalize(nfd) == "가나"
    assert content_id(normalize(nfd)) == content_id(normalize("가나"))  # 같은 source_id


def test_content_id_is_sha256_hex():
    cid = content_id("hello")
    assert len(cid) == 64 and all(c in "0123456789abcdef" for c in cid)


def test_freeze_idempotent_collision_returns_first(tmp_path):
    s = SourceStore(str(tmp_path))
    a = s.freeze(url="https://A", title="A", raw_text="같은 내용", fetched_at="t1")
    b = s.freeze(url="https://B", title="B", raw_text="같은 내용", fetched_at="t2")  # 다른 url, 같은 텍스트
    g = s.get_source(a.source_id)
    assert a.source_id == b.source_id   # content-addressed
    assert a == b == g                  # 반환 == 저장 == get_source
    assert b.url == "https://A"          # 충돌 시 *최초* 메타데이터가 정본


def test_media_explicit_and_derived(tmp_path):
    s = SourceStore(str(tmp_path))
    explicit = s.freeze(url="https://www.aitimes.com/x", title="t", raw_text="명시", fetched_at="t", media="AI Times")
    assert explicit.media == "AI Times"                       # catalog 정본명 우선
    derived = s.freeze(url="https://www.aitimes.com/y", title="t", raw_text="유도", fetched_at="t")
    assert derived.media == "aitimes.com"                      # 미제공 → url 도메인(www 제거)
    assert media_from_url("https://www.aitimes.com/z?a=1") == "aitimes.com"


def test_get_source_missing_raises(tmp_path):
    # 미스 = dangling 포인터 → KeyError(빈 값을 조용히 주지 않음). DynamoSourceStore 도 동일(파리티).
    with pytest.raises(KeyError):
        SourceStore(str(tmp_path)).get_source("nonexistent")


def test_freeze_atomic_first_wins(tmp_path):
    # os.link 원자 동결 — 같은 내용 두 번 freeze 해도 최초 메타데이터 보존(idempotent·first-wins).
    s = SourceStore(str(tmp_path))
    a = s.freeze(url="https://A", title="A", raw_text="원자성 테스트 본문", fetched_at="t1")
    b = s.freeze(url="https://B", title="B", raw_text="원자성 테스트 본문", fetched_at="t2")
    assert a == b and b.url == "https://A" and s.get_source(a.source_id) == a


# ── DynamoSourceStore — 정본은 durable(TTL 없음) ────────────────────────
# 2026-08-01 결정: source-store 7일 TTL 폐지 → 영구 보존(나중 활용 목적).
# 파이프라인은 그 런에서 방금 freeze 한 객체를 직접 쓰므로 TTL 은 소급(retrospection)에만 영향을 준다.

class _FakeTable:
    """put_item/get_item 만 흉내내는 최소 fake — 네트워크 0, 조건부 put 의 first-wins 까지 재현."""

    def __init__(self) -> None:
        self.items: dict = {}

    def put_item(self, Item, ConditionExpression=None):
        from botocore.exceptions import ClientError
        if ConditionExpression is not None and Item["source_id"] in self.items:
            raise ClientError({"Error": {"Code": "ConditionalCheckFailedException"}}, "PutItem")
        self.items[Item["source_id"]] = dict(Item)

    def get_item(self, Key):
        item = self.items.get(Key["source_id"])
        return {"Item": item} if item is not None else {}


def _dynamo_store(monkeypatch):
    from briefing.core.stores import dynamo
    table = _FakeTable()
    monkeypatch.setattr(dynamo, "_table", lambda *a, **k: table)
    return dynamo.DynamoSourceStore("t"), table


def test_dynamo_freeze_writes_no_ttl(monkeypatch):
    """정본은 durable — freeze 가 ttl 속성을 쓰면 DDB 가 다시 자동 삭제하게 된다(회귀 방지)."""
    store, table = _dynamo_store(monkeypatch)
    fs = store.freeze(url="https://x/a", title="t", raw_text="본문 텍스트", fetched_at="t0")
    assert "ttl" not in table.items[fs.source_id]


def test_dynamo_reads_legacy_item_that_still_has_ttl(monkeypatch):
    """TTL 폐지 이전 항목엔 ttl 속성이 남아 있다 — 화이트리스트 역직렬화라 마이그레이션 없이 그대로 읽힌다."""
    store, table = _dynamo_store(monkeypatch)
    fs = store.freeze(url="https://x/b", title="t2", raw_text="구 항목 본문", fetched_at="t0")
    table.items[fs.source_id]["ttl"] = 1_700_000_000       # 과거 스키마 잔재를 주입
    assert store.get_source(fs.source_id) == fs           # ttl 은 무시되고 동일 동결본
