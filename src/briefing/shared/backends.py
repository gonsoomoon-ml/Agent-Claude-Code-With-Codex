"""backends — settings.backend(local|dynamo) → (source_store, card_cache, ledger) *일관* 선택.

★ 셋은 한 durability tier 를 공유해야 한다 — ledger 의 source_id 포인터가 source_store 로, card_key 가 card_cache 로
  resolve 하기 때문. 그래서 store 별로 따로 고르지 않고 **단일 BACKEND 토글**로 셋을 함께 고른다
  ("ledger 만 DDB, source 는 local" → 클라우드 ephemeral 에서 dangling 포인터 = 그 footgun 방지).
- local(기본): 파일 backend(dev/PoC). dynamo: CFN 테이블(클라우드).
- dynamo 는 *lazy import* — local 경로는 boto3 를 전혀 건드리지 않는다(AWS-free baseline 유지).
"""
from __future__ import annotations

from .cache import CardCache, LocalCardCache
from .config import Settings
from .ledger import Ledger, LocalLedger
from .source_store import SourceStore


def make_stores(settings: Settings) -> tuple[SourceStore, CardCache, Ledger]:
    """(source_store, card_cache, ledger) — backend 일관. driver/entrypoint 가 호출해 run_briefing 에 전달."""
    if settings.backend == "dynamo":
        from . import dynamo  # lazy: local 경로는 boto3 무접촉
        return (
            dynamo.source_store_from_settings(settings),
            dynamo.card_cache_from_settings(settings),
            dynamo.ledger_from_settings(settings),
        )
    return (
        SourceStore(settings.source_store_path),
        LocalCardCache(settings.cache_path),
        LocalLedger(settings.ledger_path),
    )
