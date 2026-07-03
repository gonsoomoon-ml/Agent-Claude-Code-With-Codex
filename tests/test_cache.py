"""cache — 공유 결과 캐시: 직렬화 라운드트립 + 같은 (source, lens) 둘째 실행은 파이프라인 재실행 0회."""
from types import SimpleNamespace

from briefing.core.authoring.author import Claim, DraftCard
from briefing.core.stores.cache import LocalCardCache, _deserialize, _serialize, card_key
from briefing.core.verification.certifier import CertVerdict
from briefing.core.gate import GatedCard
from briefing.core.pipeline import run_briefing
from briefing.core.stores.source_store import SourceStore
from briefing.core.retrieval.sources import FetchedArticle


def _gated():
    return GatedCard(
        DraftCard("S", "헤드라인", "요약", "왜", (Claim("C1", "직원이 100명이다.", "arithmetic", "core"),)),
        (CertVerdict("C1", "VERIFIED", "ev", "deterministic"),), "PUBLISH", 1)


def test_cache_serialize_roundtrip():
    g = _gated()
    assert _deserialize(_serialize(g)) == g   # frozen dataclass eq → 무손실 왕복


def test_card_cache_idempotent(tmp_path):
    cache = LocalCardCache(str(tmp_path))
    g, k = _gated(), card_key("S", "engineer", "", "model")
    assert cache.get(k) is None               # miss
    cache.put(k, g)
    assert cache.get(k) == g                   # hit → 동일 카드


def test_card_cache_corrupt_entry_returns_none(tmp_path):
    # 손상/구스키마 캐시 항목 → get 은 raise 가 아니라 miss(None). 캐시는 disposable 라 fail-open.
    cache = LocalCardCache(str(tmp_path))
    k = card_key("S", "engineer", "", "model")
    cache._path(k).write_text("{ not valid json", encoding="utf-8")              # 손상 JSON
    assert cache.get(k) is None
    cache._path(k).write_text('{"card": {"source_id": "x"}}', encoding="utf-8")  # 구스키마(필드 누락)
    assert cache.get(k) is None


def _user(uid, lens="engineer"):
    return SimpleNamespace(id=uid, recipient=f"{uid}@x", sources=("aws-ml",), depth="full", lens=lens, skill_md="")


def _fetch(source, _w):
    return [FetchedArticle(source.key, "u", "t", "직원 약 100명.", "2026-06-27T00:00:00Z")]


def test_card_cache_skips_pipeline_on_second_same_lens(tmp_path):
    store = SourceStore(str(tmp_path / "store"))
    cache = LocalCardCache(str(tmp_path / "cache"))
    settings = SimpleNamespace(author_model_id="m")
    calls = {"draft": 0}

    def draft(*_a):
        calls["draft"] += 1
        return DraftCard("sid", "H", "S", "W", (Claim("C1", "직원이 100명이다.", "arithmetic", "core"),))

    common = dict(window_hours=0, fetch_article_fn=_fetch, draft_fn=draft,
                  verify_fn=lambda c: (CertVerdict("C1", "VERIFIED", "ev"),), card_cache=cache)

    run_briefing(settings, store, [_user("alice")], **common)
    assert calls["draft"] == 1                 # 첫 실행: alice → draft 1회
    out = run_briefing(settings, store, [_user("bob")], **common)
    assert calls["draft"] == 1                 # ★ 같은 (source, lens) → 캐시 hit → draft 0회 추가(재실행 방지)
    assert out[0].published == 1               # 캐시본으로도 정상 발행
