"""pipeline — host-agnostic run_briefing (curate→per-user gate→render). DI fakes 로 전 파이프라인 결정론 검증.

★ 이전엔 이 오케스트레이션이 AgentCore entrypoint 에 용접돼 *테스트로 안 덮였음* — 추출 후 여기서 결정론으로 덮는다.
"""
from types import SimpleNamespace

from briefing.shared.harness.author import Claim, DraftCard
from briefing.shared.harness.certifier import CertVerdict
from briefing.shared.pipeline import run_briefing
from briefing.shared.stores.source_store import SourceStore
from briefing.shared.retrieval.sources import FetchedArticle


def _user(uid, sources):
    return SimpleNamespace(id=uid, recipient=f"{uid}@example.com", sources=tuple(sources), depth="full")


def _fetch(source, _w):
    return [FetchedArticle(source.key, "https://x", "제목", "직원 약 100명.", "2026-06-27T00:00:00Z")]


def _card_two():
    return DraftCard("sid", "H", "S", "W",
                     (Claim("C1", "ok", "entailment", "core"),
                      Claim("C2", "bad", "arithmetic", "supporting")))


def test_run_briefing_multiuser_end_to_end(tmp_path):
    store = SourceStore(str(tmp_path / "store"))
    users = [_user("alice", ["aws-ml"]), _user("bob", ["aws-ml"])]
    out = run_briefing(
        SimpleNamespace(), store, users, window_hours=0, fetch_article_fn=_fetch,
        draft_fn=lambda *_a: DraftCard("sid", "헤드라인", "요약", "왜중요",
                                       (Claim("C1", "직원이 100명이다.", "arithmetic", "core"),)),
        verify_fn=lambda c: (CertVerdict("C1", "VERIFIED", "ev"),),
    )
    assert [b.user_id for b in out] == ["alice", "bob"]            # per-user 팬아웃
    assert all(b.published == 1 and b.quarantined == 0 for b in out)
    assert "다른 AI 에이전트가 사실" in out[0].email and out[0].recipient == "alice@example.com"


def test_run_briefing_degrades_blocked_supporting(tmp_path):
    store = SourceStore(str(tmp_path / "store"))
    out = run_briefing(
        SimpleNamespace(), store, [_user("u", ["aws-ml"])], window_hours=0, fetch_article_fn=_fetch,
        draft_fn=lambda *_a: _card_two(), revise_fn=lambda *a, **k: _card_two(),
        verify_fn=lambda c: (CertVerdict("C1", "VERIFIED", "ev"), CertVerdict("C2", "BLOCKED", "ev")),
    )
    assert out[0].published == 1 and "제외" in out[0].email        # graceful degradation 이 드라이버 통과로도 동작


def _fetch_distinct(source, _w):
    # 출처별 *다른 본문* → content-addressed source_id 가 출처마다 달라진다(분야 그룹 검증용).
    # "AI" 포함 → require_ai 소스(aitimes)의 relevance 필터를 통과(이 테스트 주제는 그룹핑).
    return [FetchedArticle(source.key, f"https://x/{source.key}", f"{source.key} AI 제목",
                           f"{source.key} 고유 AI 본문.", "2026-06-27T00:00:00Z")]


def test_run_briefing_groups_by_area_and_dates_header(tmp_path):
    store = SourceStore(str(tmp_path / "store"))
    users = [_user("alice", ["aitimes", "openai"])]   # AI 뉴스 + 프런티어 AI 랩 = 2개 분야
    out = run_briefing(
        SimpleNamespace(), store, users, window_hours=0, fetch_article_fn=_fetch_distinct,
        draft_fn=lambda source, *_a: DraftCard(source.source_id, "헤드라인", "요약", "왜중요",
                                               (Claim("C1", "ok", "entailment", "core"),)),
        verify_fn=lambda c: (CertVerdict("C1", "VERIFIED", "ev"),),
        run_date="2026-06-29",
    )
    email = out[0].email
    assert "2개 분야" in email                                   # 출처 기준 분야 카운트
    assert "AI 뉴스" in email and "프런티어 AI 랩" in email        # 분야 밴드(2개+)
    assert "6월 29일" in email                                   # run_date → 헤더 날짜
