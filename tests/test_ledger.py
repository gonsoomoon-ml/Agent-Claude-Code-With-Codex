"""ledger — run history(시간·사용자 인덱스): append/query(since 필터) + 파이프라인이 매 처리 1줄 기록."""
from types import SimpleNamespace

from briefing.shared.harness.author import Claim, DraftCard
from briefing.shared.harness.certifier import CertVerdict
from briefing.shared.stores.ledger import LocalLedger, NullLedger
from briefing.shared.pipeline import run_briefing
from briefing.shared.stores.source_store import SourceStore
from briefing.shared.retrieval.sources import FetchedArticle


def test_null_ledger_noop():
    led = NullLedger()
    led.append("2026-06-27", "alice", "S", "k", "PUBLISH", "H")  # 무시
    assert led.query("alice") == []


def test_local_ledger_append_and_since_filter(tmp_path):
    led = LocalLedger(str(tmp_path))
    led.append("2026-06-20", "alice", "S1", "k1", "PUBLISH", "월요일")
    led.append("2026-06-27", "alice", "S2", "k2", "QUARANTINE", "금요일")
    led.append("2026-06-27", "bob", "S3", "k3", "PUBLISH", "딴 사람")

    rows = led.query("alice")
    assert [r["headline"] for r in rows] == ["월요일", "금요일"]   # 사용자 격리(bob 안 섞임)
    assert led.query("alice", since_date="2026-06-25") == [rows[1]]  # ISO 사전식=시간순 → 최근만
    assert led.query("nobody") == []                                # 미존재 user → 빈 목록


def test_local_ledger_query_dedups_on_reappend(tmp_path):
    # ★ 멱등 파리티: 같은 (user, run_date, source_id) 재기록(재실행) → query 1건(마지막 win) = DynamoLedger put 덮어쓰기.
    led = LocalLedger(str(tmp_path))
    led.append("2026-06-28", "u1", "src1", "k1", "PUBLISH", "old")
    led.append("2026-06-28", "u1", "src1", "k1", "PUBLISH", "new")
    rows = led.query("u1")
    assert len(rows) == 1 and rows[0]["headline"] == "new"


def _user(uid, lens="engineer"):
    return SimpleNamespace(id=uid, recipient=f"{uid}@x", sources=("aws-ml",), depth="full", lens=lens, skill_md="")


def _fetch(source, _w):
    return [FetchedArticle(source.key, "https://x/a", "제목", "직원 약 100명.", "2026-06-27T00:00:00Z")]


def test_pipeline_records_ledger(tmp_path):
    store = SourceStore(str(tmp_path / "store"))
    led = LocalLedger(str(tmp_path / "ledger"))
    settings = SimpleNamespace(author_model_id="m")
    common = dict(
        window_hours=0, fetch_article_fn=_fetch,
        draft_fn=lambda *_a: DraftCard("sid", "헤드라인", "S", "W", (Claim("C1", "직원이 100명이다.", "arithmetic", "core"),)),
        verify_fn=lambda c: (CertVerdict("C1", "VERIFIED", "ev"),),
        ledger=led, run_date="2026-06-27",
    )

    run_briefing(settings, store, [_user("alice")], **common)
    rows = led.query("alice")
    assert len(rows) == 1
    r = rows[0]
    assert r["run_date"] == "2026-06-27" and r["decision"] == "PUBLISH" and r["headline"] == "헤드라인"
    assert r["source_id"] and r["card_key"]           # source_store·card cache 로 join 가능(중복 저장 없음)
