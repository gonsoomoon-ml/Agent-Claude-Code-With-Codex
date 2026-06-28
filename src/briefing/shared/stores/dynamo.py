"""dynamo — 영속 계층의 DynamoDB 백엔드(v1.5). 로컬 backend 와 *완전히 같은 Protocol* 을 만족한다.

★ 각 Dynamo* 클래스가 Local* 과 같은 인터페이스를 구현 → wiring 한 줄만 바꾸면 Local ↔ Dynamo 를 갈아끼울 수 있다.
- 테이블은 CloudFormation(infra/ddb.yaml)이 선언적으로 만든다 — PAY_PER_REQUEST. cache=TTL 30일, source=7일, ledger=durable(TTL 없음).
- 직렬화는 로컬 cache 의 _serialize/_deserialize 를 그대로 쓴다 — 카드를 JSON 문자열 한 속성으로 저장(DDB 의 중첩 map·빈 문자열 marshalling 함정을 피한다).
- endpoint_url 옵션: 빈값이면 실제 AWS(기본), 값을 주면 DynamoDB Local(무료 에뮬레이터) — 코드는 같고 env 하나만 다르다.
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
_SOURCE_TTL_DAYS = 7  # 원문은 저작권에 민감해서 7일만 두는 ephemeral — 말뭉치(corpus)가 아니다. 파생물인 ledger/card 는 durable
_SRC_FIELDS = ("source_id", "url", "title", "text", "fetched_at", "media")
_USER_FIELDS = ("recipient", "type", "sources", "depth", "lens", "send_hour", "timezone")  # skill_md 는 뺀다 — 파일 오버레이(신뢰 경계)


def _to_frozen(item: dict) -> FrozenSource:
    return FrozenSource(**{k: item.get(k, "") for k in _SRC_FIELDS})


def _table(table_name: str, region: str = "", endpoint_url: str = ""):
    kw: dict = {}
    if region:
        kw["region_name"] = region
    if endpoint_url:
        kw["endpoint_url"] = endpoint_url  # DynamoDB Local(무료 에뮬레이터)을 쓸 때만; 빈값이면 실제 AWS
    return boto3.resource("dynamodb", **kw).Table(table_name)


class DynamoCardCache:
    """카드 캐시 DDB 백엔드 — PK=cache_key, 본문은 card_json(문자열), 만료는 ttl(숫자). LocalCardCache 와 같은 Protocol."""

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
            "ttl": int(time.time()) + _CACHE_TTL_DAYS * 86400,  # 만료용 운영 메타데이터일 뿐 — gate 로직이 아니라 결정론에 무관
        })


class DynamoLedger:
    """장부 DDB 백엔드 — PK=user_id, SK=run_date#source_id. SK range 로 'user X 의 최근 N일'을 질의한다.

    LocalLedger 와 같은 Protocol·같은 dict 형태를 돌려준다(backend 무관). put_item 은 같은 (user, sk)를 덮어쓰므로 재실행해도 idempotent.
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
            cond = cond & Key("sk").gte(since_date)  # "2026-06-20" <= "2026-06-20#…" 이라 날짜 prefix 로 그날 이후를 range 질의
        items = self._t.query(KeyConditionExpression=cond).get("Items", [])
        return [{
            "run_date": it.get("run_date", ""), "user_id": it.get("user_id", ""),
            "source_id": it.get("source_id", ""), "card_key": it.get("card_key", ""),
            "decision": it.get("decision", ""), "headline": it.get("headline", ""),
        } for it in items]


class DynamoSourceStore:
    """정본(source-of-record) DDB 백엔드 — PK=source_id(내용 해시). SourceStore 와 같은 인터페이스(freeze/get_source).

    동결본은 불변(첫 동결이 이긴다) — local 과 같은 get-first 패턴. media = catalog 의 Source.name(예 "AI Times"), 빈값이면 url 도메인에서 유도.
    ★ 셋 중 *토대* — ledger/cache 의 source_id 포인터가 여기로 resolve 된다. anti-cheat 불변식의 앵커.
    """

    def __init__(self, table_name: str, region: str = "", endpoint_url: str = "") -> None:
        self._t = _table(table_name, region, endpoint_url)

    def freeze(self, *, url: str, title: str, raw_text: str, fetched_at: str,
               media: str = "") -> FrozenSource:
        text = normalize(raw_text)
        source_id = content_id(text)
        existing = self._t.get_item(Key={"source_id": source_id}).get("Item")
        if existing:
            # 이미 있으면 그 동결본을 반환(첫 동결이 이긴다). ※ get→put 이 원자적이지 않아 동시 freeze 시
            #   메타데이터(url/title/fetched_at)는 last-write-wins — 다만 텍스트는 content-hash 라 항상 동일.
            return _to_frozen(existing)
        fs = FrozenSource(source_id=source_id, url=url, title=title, text=text,
                          fetched_at=fetched_at, media=media or media_from_url(url))
        item = asdict(fs)
        item["ttl"] = int(time.time()) + _SOURCE_TTL_DAYS * 86400  # 7일 뒤 DDB 가 자동 삭제(ephemeral)
        self._t.put_item(Item=item)
        return fs

    def get_source(self, source_id: str) -> FrozenSource:
        """source_id 로 동결본을 읽는다. 없으면 전 필드가 빈 FrozenSource(미스 = 빈 레코드)."""
        return _to_frozen(self._t.get_item(Key={"source_id": source_id}).get("Item") or {})


class DynamoUserStore:
    """사용자 프로필 DDB 백엔드 — PK=user_id, **운영 7필드만**(skill_md 는 제외 — 파일 오버레이, 신뢰 경계).

    get_user → 7필드 dict(config.load_user 가 skill_md 파일을 합쳐 UserConfig 를 만든다). 쓰기는 ④ 의 `PUT /profile`.
    list_users → Scan(user_id 만 projection, 페이지네이션). put_user 는 시드/관리용(skill_md 안 씀).
    """

    def __init__(self, table_name: str, region: str = "", endpoint_url: str = "") -> None:
        self._t = _table(table_name, region, endpoint_url)

    def get_user(self, user_id: str) -> dict | None:
        item = self._t.get_item(Key={"user_id": user_id}).get("Item")
        if not item:
            return None
        d = {k: item[k] for k in _USER_FIELDS if k in item}
        if "sources" in d:
            d["sources"] = list(d["sources"])      # DDB 의 List 를 파이썬 list 로
        if "send_hour" in d:
            d["send_hour"] = int(d["send_hour"])    # DDB 의 Number(Decimal)를 int 로
        return d

    def list_users(self) -> list[str]:
        ids: list[str] = []
        kw: dict = {"ProjectionExpression": "user_id"}
        while True:                                  # 페이지네이션 — 일일 배치는 어차피 전 사용자를 순회하므로 Scan 이 불가피
            resp = self._t.scan(**kw)
            ids += [it["user_id"] for it in resp.get("Items", [])]
            lek = resp.get("LastEvaluatedKey")
            if not lek:
                break
            kw["ExclusiveStartKey"] = lek
        return sorted(ids)

    def put_user(self, user_id: str, fields: dict) -> None:
        """시드·관리용 — 운영 7필드를 쓴다(★ skill_md 는 쓰지 않는다 — 신뢰 경계). ④ 는 PutItem 대신 UpdateItem(7필드)으로 갱신하는 게 좋다."""
        item: dict = {"user_id": user_id}
        for k in _USER_FIELDS:
            v = fields.get(k)
            if v is None:
                continue
            item[k] = list(v) if k == "sources" else (int(v) if k == "send_hour" else v)
        self._t.put_item(Item=item)


# ── settings → backend 팩토리 (driver/smoke 가 호출한다; boto3 는 이 모듈을 import 할 때만 필요) ──
def card_cache_from_settings(settings) -> DynamoCardCache:
    return DynamoCardCache(settings.cache_table, settings.region, getattr(settings, "ddb_endpoint_url", ""))


def ledger_from_settings(settings) -> DynamoLedger:
    return DynamoLedger(settings.ledger_table, settings.region, getattr(settings, "ddb_endpoint_url", ""))


def source_store_from_settings(settings) -> DynamoSourceStore:
    return DynamoSourceStore(settings.source_table, settings.region, getattr(settings, "ddb_endpoint_url", ""))


def user_store_from_settings(settings) -> DynamoUserStore:
    return DynamoUserStore(settings.users_table, settings.region, getattr(settings, "ddb_endpoint_url", ""))
