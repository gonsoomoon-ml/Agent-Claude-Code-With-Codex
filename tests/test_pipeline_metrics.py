"""pipeline metrics — UserBriefing.cost_usd/duration_ms carrier 필드 + run_briefing 델타 스냅샷 회귀 테스트.

앞의 두 테스트는 UserBriefing 을 직접 생성해 필드 *기본값*만 검사한다(300105e 리뷰 지적 — 실제
run_briefing 의 스냅샷 로직은 미검증). 아래 test_run_briefing_* 는 tests/test_pipeline.py 의 fake-DI
하니스를 재사용해 run_briefing() 을 실제로 호출하고, before/after 델타가 UserBriefing 에 반영되는지 검증한다.
"""
from types import SimpleNamespace

from briefing.core.authoring.author import Claim, DraftCard
from briefing.core.verification.certifier import CertVerdict
from briefing.core.pipeline import run_briefing, UserBriefing
from briefing.core.stores.source_store import SourceStore
from briefing.core.stores.usage import UsageRecorder
from briefing.core.retrieval.sources import FetchedArticle


def test_userbriefing_has_cost_and_duration_defaults():
    b = UserBriefing(user_id="u", recipient="r", cards=(), email="", published=0, quarantined=0)
    assert b.cost_usd == 0.0
    assert b.duration_ms == 0


def _user(uid, sources, lens=""):
    return SimpleNamespace(id=uid, recipient=f"{uid}@example.com", sources=tuple(sources),
                           depth="full", lens=lens, skill_md="")


def _fetch(source, _w):
    return [FetchedArticle(source.key, "https://x", "제목", "직원 약 100명.", "2026-06-27T00:00:00Z")]


def _draft_ok(source, *_a):
    return DraftCard(source.source_id, "헤드라인", "요약", "왜중요",
                     (Claim("C1", "ok", "entailment", "core"),))


def _verify_ok(_c):
    return (CertVerdict("C1", "VERIFIED", "ev"),)


def test_run_briefing_populates_duration_zero_cost_without_recorder(tmp_path):
    """recorder 미주입 시 — 스냅샷 로직 자체는 돌지만(before/after 델타=0-0), 실제 결과에 반영돼야 한다.

    dataclass 기본값(0.0/0)과 우연히 같아 보이지만, 여기선 run_briefing 이 계산해서 채운 값이다
    (fake draft/verify 는 recorder 를 전혀 안 건드리므로 델타는 항상 0 — '계측 없음 = 비용 0' 계약).
    """
    store = SourceStore(str(tmp_path / "store"))
    users = [_user("alice", ["aws-ml"]), _user("bob", ["aws-ml", "aitimes"])]
    out = run_briefing(
        SimpleNamespace(), store, users, window_hours=0, fetch_article_fn=_fetch,
        draft_fn=_draft_ok, verify_fn=_verify_ok,
    )
    assert len(out) == 2
    for b in out:
        assert b.cost_usd == 0.0
        assert isinstance(b.duration_ms, int) and not isinstance(b.duration_ms, bool)
        assert b.duration_ms >= 0


def test_run_briefing_attributes_cost_to_first_user_cache_hit_is_free(tmp_path):
    """같은 출처를 고른 두 사용자 — 사실층은 출처당 1회만 생성(run 내 memo)되므로 1번째 사용자만 '지불'한다.

    recorder 는 draft_fn 클로저가 직접 add() 한다(주입된 fake 는 gate 의 recorder partial-binding을
    우회하므로 — produce_card 는 draft_fn 이 not None 이면 그대로 호출하고 recorder 를 안 묶는다).
    따라서 rec 에 도달하는 유일한 비용은 이 클로저가 add 한 값뿐 — 델타를 정확히 예측할 수 있다.
    """
    store = SourceStore(str(tmp_path / "store"))
    users = [_user("alice", ["aws-ml"]), _user("bob", ["aws-ml"])]  # 동일 출처 선택 → 사실층 공유
    rec = UsageRecorder()
    amount = 0.0123

    def draft(source, *_a):
        rec.add(amount)     # author 실비용 자리 — fact_memo 미스일 때만(=1번째 사용자) 호출된다
        return _draft_ok(source)

    out = run_briefing(
        SimpleNamespace(), store, users, window_hours=0, fetch_article_fn=_fetch,
        draft_fn=draft, verify_fn=_verify_ok, recorder=rec,
    )
    assert [b.user_id for b in out] == ["alice", "bob"]
    assert out[0].cost_usd == amount     # alice: fact_memo 미스 → draft 호출 → 비용 귀속
    assert out[1].cost_usd == 0.0        # bob: fact_memo 히트(run 내 공유) → draft 미호출 → 비용 0
    assert rec.total() == amount         # run 전체 누적은 1회분만(중복 청구 없음)
