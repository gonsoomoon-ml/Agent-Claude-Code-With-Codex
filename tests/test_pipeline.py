"""pipeline — host-agnostic run_briefing (curate→per-user gate→render). DI fakes 로 전 파이프라인 결정론 검증.

★ 이전엔 이 오케스트레이션이 AgentCore entrypoint 에 용접돼 *테스트로 안 덮였음* — 추출 후 여기서 결정론으로 덮는다.
"""
from types import SimpleNamespace

from briefing.core.authoring.author import Claim, DraftCard
from briefing.core.verification.certifier import CertVerdict
from briefing.core.pipeline import run_briefing
from briefing.core.stores.source_store import SourceStore
from briefing.core.retrieval.sources import FetchedArticle


def _user(uid, sources, lens=""):
    return SimpleNamespace(id=uid, recipient=f"{uid}@example.com", sources=tuple(sources),
                           depth="full", lens=lens, skill_md="")


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
    assert "요약의 사실" in out[0].email and out[0].recipient == "alice@example.com"


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


def test_run_briefing_isolates_failing_card(tmp_path):
    """한 카드의 author 가 TimeoutExpired 로 죽어도 나머지 카드는 발행된다(카드별 격리).

    2026-07-01 인시던트 재현: `claude -p` 한 건이 180s 타임아웃 → 예외가 run_briefing 전체를
    무너뜨려 그날 브리핑이 통째로 유실됐다(발송 0). 격리 후엔 실패 카드만 드롭하고 나머지는 발행.
    """
    import subprocess

    store = SourceStore(str(tmp_path / "store"))
    users = [_user("u", ["aitimes", "claude-blog"])]   # 2개 출처 → 2개 카드

    calls = {"n": 0}

    def _draft(source, *_a):
        calls["n"] += 1
        if calls["n"] == 1:                        # 첫 카드 작성자 타임아웃(인시던트 재현)
            raise subprocess.TimeoutExpired(cmd=["claude", "-p"], timeout=240)
        return DraftCard(source.source_id, "헤드라인", "요약", "왜중요",
                         (Claim("C1", "ok", "entailment", "core"),))

    out = run_briefing(
        SimpleNamespace(), store, users, window_hours=0, fetch_article_fn=_fetch_distinct,
        draft_fn=_draft, verify_fn=lambda c: (CertVerdict("C1", "VERIFIED", "ev"),),
    )
    # 격리 전(버그)이면 run_briefing 이 TimeoutExpired 로 죽어 여기 도달조차 못 한다.
    assert out[0].published == 1                   # 실패 카드는 드롭, 나머지 1건은 발행
    assert len(out[0].cards) == 1                  # 죽은 카드는 브리핑에서 빠진다


def test_run_briefing_threads_relevance_fn_to_curate(tmp_path):
    """run_briefing 이 relevance_fn 을 curate 로 넘긴다 → require_ai 소스의 판정을 LLM-as-Judge 로 대체."""
    store = SourceStore(str(tmp_path / "store"))
    out = run_briefing(
        SimpleNamespace(), store, [_user("u", ["aitimes"])], window_hours=0,
        fetch_article_fn=_fetch_distinct,                       # "AI" 포함 → 키워드로는 통과할 기사
        relevance_fn=lambda _t, _x: False,                      # 판정자가 전부 컷
        draft_fn=lambda source, *_a: DraftCard(source.source_id, "H", "S", "W",
                                               (Claim("C1", "ok", "entailment", "core"),)),
        verify_fn=lambda c: (CertVerdict("C1", "VERIFIED", "ev"),),
    )
    assert out[0].published == 0 and len(out[0].cards) == 0     # 판정자가 컷 → 카드 0(키워드였다면 통과했을 것)


def test_run_briefing_threads_select_fn_to_curate(tmp_path):
    """run_briefing 이 select_fn 을 curate 로 넘긴다(시그니처+통과) — 선별 *행동*은 test_curation 이 검증.

    pytorch-kr(캡 3·select=llm)는 실 카탈로그 소스라 여기선 캡 없는 소스로 통과만 확인:
    select_fn 인자가 TypeError 없이 수용되고 기존 발행이 그대로 동작해야 한다.
    """
    store = SourceStore(str(tmp_path / "store"))
    out = run_briefing(
        SimpleNamespace(), store, [_user("u", ["aws-ml"])], window_hours=0,
        fetch_article_fn=_fetch, select_fn=lambda cands, k: list(cands)[:k],
        draft_fn=lambda source, *_a: DraftCard(source.source_id, "H", "S", "W",
                                               (Claim("C1", "ok", "entailment", "core"),)),
        verify_fn=lambda c: (CertVerdict("C1", "VERIFIED", "ev"),),
    )
    assert out[0].published == 1


def test_run_briefing_groups_by_area_and_dates_header(tmp_path):
    store = SourceStore(str(tmp_path / "store"))
    users = [_user("alice", ["aitimes", "claude-blog"])]   # 뉴스·미디어 + Anthropic = 2개 분야(발행처 기준)
    out = run_briefing(
        SimpleNamespace(), store, users, window_hours=0, fetch_article_fn=_fetch_distinct,
        draft_fn=lambda source, *_a: DraftCard(source.source_id, "헤드라인", "요약", "왜중요",
                                               (Claim("C1", "ok", "entailment", "core"),)),
        verify_fn=lambda c: (CertVerdict("C1", "VERIFIED", "ev"),),
        run_date="2026-06-29",
    )
    email = out[0].email
    assert "2개 분야" in email                                   # 출처 기준 분야 카운트
    assert "뉴스·미디어" in email and "Anthropic" in email     # 분야 밴드(2개+, 발행처)
    assert "6월 29일" in email                                   # run_date → 헤더 날짜


# ── cross-day 발행 dedup (late-post window 겹침에서 "사용자당 기사 1회" — ledger 조회) ──


def _dedup_kw(published_verdict="VERIFIED"):
    """dedup 테스트 공용 kwargs — 결정론 draft/verify(+revise) fake."""
    return dict(
        window_hours=0, fetch_article_fn=_fetch,
        draft_fn=lambda source, *_a: DraftCard(source.source_id, "H", "S", "W",
                                               (Claim("C1", "ok", "entailment", "core"),)),
        revise_fn=lambda *_a, **_k: DraftCard("sid", "H", "S", "W",
                                              (Claim("C1", "ok", "entailment", "core"),)),
        verify_fn=lambda c: (CertVerdict("C1", published_verdict, "ev"),),
    )


def test_run_briefing_dedups_previously_published(tmp_path):
    """전날 PUBLISH 된 기사는 다음날 run 에서 제외 — 48h 겹침 윈도우의 '정확히 1회' 보장."""
    from briefing.core.stores.ledger import LocalLedger

    store = SourceStore(str(tmp_path / "store"))
    ledger = LocalLedger(str(tmp_path / "led"))
    users = [_user("u", ["aws-ml"])]
    d1 = run_briefing(SimpleNamespace(), store, users, ledger=ledger, run_date="2026-07-10", **_dedup_kw())
    assert d1[0].published == 1                              # D1: 발행 + ledger 기록
    d2 = run_briefing(SimpleNamespace(), store, users, ledger=ledger, run_date="2026-07-11", **_dedup_kw())
    assert d2[0].published == 0 and len(d2[0].cards) == 0    # D2: 같은 기사 재수집돼도 제외


def test_run_briefing_same_day_rerun_not_deduped(tmp_path):
    """같은 run_date 재실행(강제 재발송 런북)은 dedup 에 안 걸린다 — strictly-earlier 비교."""
    from briefing.core.stores.ledger import LocalLedger

    store = SourceStore(str(tmp_path / "store"))
    ledger = LocalLedger(str(tmp_path / "led"))
    users = [_user("u", ["aws-ml"])]
    r1 = run_briefing(SimpleNamespace(), store, users, ledger=ledger, run_date="2026-07-10", **_dedup_kw())
    r2 = run_briefing(SimpleNamespace(), store, users, ledger=ledger, run_date="2026-07-10", **_dedup_kw())
    assert r1[0].published == 1 and r2[0].published == 1     # 멱등 재실행 보존


def test_run_briefing_quarantined_retries_next_day(tmp_path):
    """전날 QUARANTINE(사용자 미수신) 기사는 다음날 재도전 — PUBLISH 만 dedup."""
    from briefing.core.stores.ledger import LocalLedger

    store = SourceStore(str(tmp_path / "store"))
    ledger = LocalLedger(str(tmp_path / "led"))
    users = [_user("u", ["aws-ml"])]
    d1 = run_briefing(SimpleNamespace(), store, users, ledger=ledger, run_date="2026-07-10",
                      **_dedup_kw(published_verdict="BLOCKED"))   # core BLOCKED → QUARANTINE
    assert d1[0].quarantined == 1 and d1[0].published == 0
    d2 = run_briefing(SimpleNamespace(), store, users, ledger=ledger, run_date="2026-07-11", **_dedup_kw())
    assert d2[0].published == 1                              # 격리됐던 기사는 다음날 재도전 성공


# ── 2층화: 사실층 공유 + lens 해석층 (card-layering §5) ─────────────────


def test_layered_fact_once_interp_per_lens(tmp_path):
    """사실층은 출처당 1회(사용자 무관), 해석층은 (출처, lens)당 1회 — 캐시 없이도 run 내 공유."""
    from briefing.core.authoring.author import Interpretation

    store = SourceStore(str(tmp_path / "store"))
    users = [_user("alice", ["aws-ml"], lens="engineer"),
             _user("bob", ["aws-ml"], lens="business"),
             _user("carol", ["aws-ml"], lens="engineer")]   # 3명·2 lens
    calls = {"draft": 0, "interp": 0}

    def draft(source, *_a):
        calls["draft"] += 1
        return DraftCard(source.source_id, "헤드라인", "요약", "일반 해석",
                         (Claim("C1", "ok", "entailment", "core"),))

    def interp(source, claims, user, settings):
        calls["interp"] += 1
        return Interpretation(f"{user.lens} 관점 해석", (claims[0].id,))

    out = run_briefing(
        SimpleNamespace(), store, users, window_hours=0, fetch_article_fn=_fetch,
        draft_fn=draft, interp_fn=interp,
        verify_fn=lambda c: (CertVerdict("C1", "VERIFIED", "ev"),),
    )
    assert calls == {"draft": 1, "interp": 2}                  # 사실 1회 + lens 2종
    assert "engineer 관점 해석" in out[0].email                 # alice
    assert "business 관점 해석" in out[1].email                 # bob
    assert "engineer 관점 해석" in out[2].email                 # carol = alice 와 공유


def test_layered_general_lens_skips_interp(tmp_path):
    """general lens 는 해석층 호출 없이 사실층 why 를 그대로 쓴다(사실층=general 이라 동일물)."""
    store = SourceStore(str(tmp_path / "store"))
    called = {"n": 0}

    def interp(*_a):
        called["n"] += 1
        raise AssertionError("general 은 interp 를 부르면 안 됨")

    out = run_briefing(
        SimpleNamespace(), store, [_user("u", ["aws-ml"], lens="general")],
        window_hours=0, fetch_article_fn=_fetch,
        draft_fn=lambda source, *_a: DraftCard(source.source_id, "헤드라인", "요약", "일반 해석",
                                               (Claim("C1", "ok", "entailment", "core"),)),
        interp_fn=interp,
        verify_fn=lambda c: (CertVerdict("C1", "VERIFIED", "ev"),),
    )
    assert called["n"] == 0
    assert "일반 해석" in out[0].email


def test_layered_interp_failure_falls_back_to_fact_why(tmp_path):
    """층별 격리: 해석층이 죽어도 카드는 사실층 why 로 발행된다(브리핑 무붕괴)."""
    store = SourceStore(str(tmp_path / "store"))

    def interp(*_a):
        raise RuntimeError("interp harness down")

    out = run_briefing(
        SimpleNamespace(), store, [_user("u", ["aws-ml"], lens="engineer")],
        window_hours=0, fetch_article_fn=_fetch,
        draft_fn=lambda source, *_a: DraftCard(source.source_id, "헤드라인", "요약", "일반 해석",
                                               (Claim("C1", "ok", "entailment", "core"),)),
        interp_fn=interp,
        verify_fn=lambda c: (CertVerdict("C1", "VERIFIED", "ev"),),
    )
    assert out[0].published == 1
    assert "일반 해석" in out[0].email                          # 폴백 = 사실층(일반) why
