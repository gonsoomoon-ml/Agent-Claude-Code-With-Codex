"""dynamo — card cache·ledger 의 DynamoDB 백엔드 (v1.5). 로컬 backend 와 *같은 Protocol* 을 만족.

★ DynamoCardCache/DynamoLedger 가 CardCache/Ledger Protocol 을 구현 → wiring 한 줄 교체로 Local↔Dynamo swap.
- 테이블은 CloudFormation(infra/ddb.yaml)이 선언적으로 생성 — PAY_PER_REQUEST. cache=TTL 30일, ledger=durable(no TTL).
- 직렬화는 로컬 cache 의 _serialize/_deserialize 재사용 — 카드를 JSON 문자열 1속성으로 저장(중첩/빈문자열 marshalling 회피).
- endpoint_url 옵션: 빈값=실 AWS(기본), 값 주면 DynamoDB Local(무료 에뮬레이터) — 코드 동일, env 하나 차이.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict

import boto3
from boto3.dynamodb.conditions import Key

from .cache import _deserialize, _serialize
from .source_store import FrozenSource, content_id, media_from_url, normalize

_CACHE_TTL_DAYS = 30
_SOURCE_TTL_DAYS = 7  # 원문(저작권 민감)은 7일 ephemeral — corpus 아님(파생물 ledger/card 는 durable)
_SRC_FIELDS = ("source_id", "url", "title", "text", "fetched_at", "media")


def _to_frozen(item: dict) -> FrozenSource:
    return FrozenSource(**{k: item.get(k, "") for k in _SRC_FIELDS})


def _table(table_name: str, region: str = "", endpoint_url: str = ""):
    kw: dict = {}
    if region:
        kw["region_name"] = region
    if endpoint_url:
        kw["endpoint_url"] = endpoint_url  # DynamoDB Local(무료) 시만; 빈값이면 실 AWS
    return boto3.resource("dynamodb", **kw).Table(table_name)


class DynamoCardCache:
    """카드 캐시 DDB 백엔드 — PK=cache_key, 본문은 card_json(S), 만료는 ttl(N). LocalCardCache 와 동일 Protocol."""

    def __init__(self, table_name: str, region: str = "", endpoint_url: str = "") -> None:
        self._t = _table(table_name, region, endpoint_url)

    def get(self, key: str):
        item = self._t.get_item(Key={"cache_key": key}).get("Item")
        if not item:
            return None
        return _deserialize(json.loads(item["card_json"]))

    def put(self, key: str, card) -> None:
        self._t.put_item(Item={
            "cache_key": key,
            "card_json": json.dumps(_serialize(card), ensure_ascii=False),
            "ttl": int(time.time()) + _CACHE_TTL_DAYS * 86400,  # 운영 메타(만료) — gate 로직 아님(결정론 무관)
        })


class DynamoLedger:
    """장부 DDB 백엔드 — PK=user_id, SK=run_date#source_id. SK range 로 'user X 의 최근 N일' 질의.

    LocalLedger 와 동일 Protocol·동일 dict 형태 반환(백엔드 무관). put_item 은 같은 (user, sk) 덮어씀 = 재실행 idempotent.
    """

    def __init__(self, table_name: str, region: str = "", endpoint_url: str = "") -> None:
        self._t = _table(table_name, region, endpoint_url)

    def append(self, run_date: str, user_id: str, source_id: str, card_key: str,
               decision: str, headline: str) -> None:
        self._t.put_item(Item={
            "user_id": user_id,
            "sk": f"{run_date}#{source_id}",
            "run_date": run_date, "source_id": source_id,
            "card_key": card_key, "decision": decision, "headline": headline,
        })

    def query(self, user_id: str, since_date: str = "") -> list[dict]:
        cond = Key("user_id").eq(user_id)
        if since_date:
            cond = cond & Key("sk").gte(since_date)  # "2026-06-20" <= "2026-06-20#…" → 날짜 prefix range
        items = self._t.query(KeyConditionExpression=cond).get("Items", [])
        return [{
            "run_date": it.get("run_date", ""), "user_id": it.get("user_id", ""),
            "source_id": it.get("source_id", ""), "card_key": it.get("card_key", ""),
            "decision": it.get("decision", ""), "headline": it.get("headline", ""),
        } for it in items]


class DynamoSourceStore:
    """source-of-record DDB 백엔드 — PK=source_id(content hash). SourceStore 와 동일 인터페이스(freeze/get_source).

    동결본 불변(첫 동결 win) — local 과 같은 get-first 패턴. media = catalog Source.name(예 "AI Times"); 빈값이면 url 도메인.
    ★ 셋 중 *토대* — ledger/cache 의 source_id 포인터가 여기로 resolve. anti-cheat 불변식의 앵커.
    """

    def __init__(self, table_name: str, region: str = "", endpoint_url: str = "") -> None:
        self._t = _table(table_name, region, endpoint_url)

    def freeze(self, *, url: str, title: str, raw_text: str, fetched_at: str,
               media: str = "") -> FrozenSource:
        text = normalize(raw_text)
        source_id = content_id(text)
        existing = self._t.get_item(Key={"source_id": source_id}).get("Item")
        if existing:
            return _to_frozen(existing)            # 불변 — 충돌 시 최초 동결본 반환
        fs = FrozenSource(source_id=source_id, url=url, title=title, text=text,
                          fetched_at=fetched_at, media=media or media_from_url(url))
        item = asdict(fs)
        item["ttl"] = int(time.time()) + _SOURCE_TTL_DAYS * 86400  # 7일 후 DDB 자동 만료(ephemeral)
        self._t.put_item(Item=item)
        return fs

    def get_source(self, source_id: str) -> FrozenSource:
        return _to_frozen(self._t.get_item(Key={"source_id": source_id}).get("Item") or {})


# ── settings → backend 팩토리 (driver/smoke 가 호출; boto3 는 이 모듈 import 시점에만 필요) ──
def card_cache_from_settings(settings) -> DynamoCardCache:
    return DynamoCardCache(settings.cache_table, settings.region, getattr(settings, "ddb_endpoint_url", ""))


def ledger_from_settings(settings) -> DynamoLedger:
    return DynamoLedger(settings.ledger_table, settings.region, getattr(settings, "ddb_endpoint_url", ""))


def source_store_from_settings(settings) -> DynamoSourceStore:
    return DynamoSourceStore(settings.source_table, settings.region, getattr(settings, "ddb_endpoint_url", ""))
