"""weekly.collect — 한 주 범위 · PUBLISH 만 · 같은 원문 첫 날만 · 캐시 miss · VERIFIED id (로컬 backend, 네트워크 0)."""
from briefing.core.authoring.author import Claim, DraftCard
from briefing.core.gate import GatedCard
from briefing.core.stores.cache import LocalCardCache
from briefing.core.stores.ledger import LocalLedger
from briefing.core.stores.source_store import SourceStore
from briefing.core.verification.certifier import CertVerdict
from briefing.weekly.collect import collect, friday_ready, week_range

U = "admin-1"


def _card(source_id: str, verdicts: tuple[str, ...]) -> GatedCard:
    claims = tuple(Claim(id=f"c{i}", text=f"사실 {i}", claim_type="entailment") for i in range(1, len(verdicts) + 1))
    draft = DraftCard(source_id=source_id, headline=f"H-{source_id[:6]}", summary="요약", why_it_matters="왜",
                      claims=claims)
    vs = tuple(CertVerdict(claim_id=c.id, verdict=v, evidence="") for c, v in zip(claims, verdicts))
    return GatedCard(draft, vs, "PUBLISH", 1)


def _stores(tmp_path):
    return LocalLedger(str(tmp_path / "ledger")), LocalCardCache(str(tmp_path / "cache")), SourceStore(str(tmp_path / "src"))


def test_week_range_is_previous_saturday_to_friday():
    assert week_range("2026-11-07") == ("2026-10-31", "2026-11-06")
    assert week_range("2026-10-31") == ("2026-10-24", "2026-10-30")


def test_collect_filters_window_decision_and_duplicates(tmp_path):
    ledger, cache, store = _stores(tmp_path)
    a = store.freeze(url="https://www.anthropic.com/research/a", title="A", raw_text="본문 A", fetched_at="x")
    b = store.freeze(url="https://developers.googleblog.com/b", title="B", raw_text="본문 B", fetched_at="x")
    c = store.freeze(url="https://aws.amazon.com/blogs/c", title="C", raw_text="본문 C", fetched_at="x")
    cache.put("k-a", _card(a.source_id, ("VERIFIED", "BLOCKED", "VERIFIED")))
    cache.put("k-b", _card(b.source_id, ("VERIFIED",)))
    ledger.append("2026-10-30", U, a.source_id, "k-a", "PUBLISH", "H-a")     # 범위 밖(전주 금)
    ledger.append("2026-10-31", U, a.source_id, "k-a", "PUBLISH", "H-a")     # 첫 날
    ledger.append("2026-11-02", U, a.source_id, "k-a", "PUBLISH", "H-a")     # 같은 원문 → 뺀다
    ledger.append("2026-11-03", U, b.source_id, "k-b", "PUBLISH", "H-b")
    ledger.append("2026-11-04", U, c.source_id, "k-miss", "PUBLISH", "원장 제목")  # 캐시 miss
    ledger.append("2026-11-05", U, c.source_id + "x", "k-q", "QUARANTINE", "격리")  # PUBLISH 아님
    ledger.append("2026-11-07", U, b.source_id + "y", "k-n", "PUBLISH", "다음 주")  # 범위 밖(발행일 당일)

    week = collect(ledger, cache, store, U, "2026-11-07")

    assert [(w.n, w.run_date, w.source_id) for w in week] == [
        (1, "2026-10-31", a.source_id), (2, "2026-11-03", b.source_id), (3, "2026-11-04", c.source_id)]
    assert week[0].verified_ids == ("c1", "c3") and len(week[0].claims) == 3
    assert week[0].media and week[0].url.endswith("/a") and week[0].cached
    assert not week[2].cached and week[2].headline == "원장 제목" and week[2].claims == ()


def test_friday_ready(tmp_path):
    ledger, _, _ = _stores(tmp_path)
    assert not friday_ready(ledger, U, "2026-11-07")
    ledger.append("2026-11-05", U, "s1", "k", "PUBLISH", "목")
    assert not friday_ready(ledger, U, "2026-11-07")
    ledger.append("2026-11-06", U, "s2", "k", "PUBLISH", "금")
    assert friday_ready(ledger, U, "2026-11-07")
