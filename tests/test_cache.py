"""cache — 공유 결과 캐시: 직렬화 라운드트립 + 2층 키(fact/interp) + 사용자 간 공유(둘째 실행 재실행 0회)."""
from types import SimpleNamespace

from briefing.core.authoring.author import Claim, DraftCard, Interpretation
from briefing.core.stores.cache import (
    LocalCardCache, _deserialize, _serialize, card_key, fact_card_key, interp_card_key,
)
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


# ── 2층 키 (card-layering §5) ─────────────────────────────


def test_fact_card_key_shared_across_lens_and_skill():
    # 사실층 키에는 lens·skill 이 없다 → 전 사용자 공유(진짜 캐시 공유의 성립 조건)
    k = fact_card_key("S", "model", "v1")
    assert k == fact_card_key("S", "model", "v1")     # 결정론
    assert k != fact_card_key("S2", "model", "v1")    # 기사 바뀌면 무효화(content-addressed)
    assert k != fact_card_key("S", "model", "v2")     # 프롬프트 계약 개정도 무효화


def test_interp_card_key_per_lens_and_chained_to_fact():
    fk1, fk2 = fact_card_key("S", "m", "v1"), fact_card_key("S", "m", "v2")
    assert interp_card_key("S", "engineer", fk1) != interp_card_key("S", "business", fk1)  # lens 별 분리
    assert interp_card_key("S", "engineer", fk1) != interp_card_key("S", "engineer", fk2)  # 사실층 갱신 → 해석층 자동 무효화


# ── 사용자 간 공유(드라이버 통합) ─────────────────────────────


def _user(uid, lens="engineer"):
    return SimpleNamespace(id=uid, recipient=f"{uid}@x", sources=("aws-ml",), depth="full", lens=lens, skill_md="")


def _fetch(source, _w):
    return [FetchedArticle(source.key, "u", "t", "직원 약 100명.", "2026-06-27T00:00:00Z")]


def test_card_cache_skips_pipeline_on_second_same_lens(tmp_path):
    store = SourceStore(str(tmp_path / "store"))
    cache = LocalCardCache(str(tmp_path / "cache"))
    settings = SimpleNamespace(author_model_id="m")
    calls = {"draft": 0, "interp": 0}

    def draft(*_a):
        calls["draft"] += 1
        return DraftCard("sid", "H", "S", "W", (Claim("C1", "직원이 100명이다.", "arithmetic", "core"),))

    def interp(*_a):
        calls["interp"] += 1
        return Interpretation("engineer 관점 해석.", ("C1",))

    common = dict(window_hours=0, fetch_article_fn=_fetch, draft_fn=draft, interp_fn=interp,
                  verify_fn=lambda c: (CertVerdict("C1", "VERIFIED", "ev"),), card_cache=cache)

    run_briefing(settings, store, [_user("alice")], **common)
    assert calls == {"draft": 1, "interp": 1}  # 첫 실행: 사실층 1회 + 해석층(engineer) 1회
    out = run_briefing(settings, store, [_user("bob")], **common)
    assert calls == {"draft": 1, "interp": 1}  # ★ 같은 (source, lens) → 두 층 다 캐시 hit → 재실행 0회
    assert out[0].published == 1               # 캐시본으로도 정상 발행
    assert "engineer 관점 해석." in out[0].email  # bob 도 공유 해석층을 받는다
