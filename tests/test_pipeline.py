"""pipeline — host-agnostic run_briefing (curate→per-user gate→render). DI fakes 로 전 파이프라인 결정론 검증.

★ 이전엔 이 오케스트레이션이 AgentCore entrypoint 에 용접돼 *테스트로 안 덮였음* — 추출 후 여기서 결정론으로 덮는다.
"""
from datetime import datetime, timezone
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


def test_run_briefing_flags_card_with_blocked_supporting_claim(tmp_path):
    """F4: 핵심 아닌 claim 이 막혀도 카드는 ⚠ 표시로 실린다(QUARANTINE) — ✓ 카드에 확인 못 한 사실이 숨지 않게."""
    store = SourceStore(str(tmp_path / "store"))
    out = run_briefing(
        SimpleNamespace(), store, [_user("u", ["aws-ml"])], window_hours=0, fetch_article_fn=_fetch,
        draft_fn=lambda *_a: _card_two(), revise_fn=lambda *a, **k: _card_two(),
        verify_fn=lambda c: (CertVerdict("C1", "VERIFIED", "ev"), CertVerdict("C2", "BLOCKED", "ev")),
    )
    assert out[0].published == 0 and out[0].quarantined == 1
    assert "⚠ 요약의 사실 1건을 원문에서 확인하지 못함" in out[0].email   # 카드는 메일에 그대로 실림(N5)


def _fetch_distinct(source, _w):
    # 출처별 *다른 본문* → content-addressed source_id 가 출처마다 달라진다(분야 그룹 검증용).
    # "AI" 포함 → require_ai 소스(aws-kr-tech)의 relevance 필터를 통과(이 테스트 주제는 그룹핑).
    return [FetchedArticle(source.key, f"https://x/{source.key}", f"{source.key} AI 제목",
                           f"{source.key} 고유 AI 본문.", "2026-06-27T00:00:00Z")]


def test_run_briefing_isolates_failing_card(tmp_path):
    """한 카드의 author 가 TimeoutExpired 로 죽어도 나머지 카드는 발행된다(카드별 격리).

    2026-07-01 인시던트 재현: `claude -p` 한 건이 180s 타임아웃 → 예외가 run_briefing 전체를
    무너뜨려 그날 브리핑이 통째로 유실됐다(발송 0). 격리 후엔 실패 카드만 드롭하고 나머지는 발행.
    """
    import subprocess

    store = SourceStore(str(tmp_path / "store"))
    users = [_user("u", ["the-decoder", "claude-blog"])]   # 2개 출처 → 2개 카드

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
        SimpleNamespace(), store, [_user("u", ["aws-kr-tech"])], window_hours=0,   # require_ai 카드 소스
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
    users = [_user("alice", ["the-decoder", "claude-blog"])]   # News & Media + Anthropic = 2개 분야(발행처 기준)
    out = run_briefing(
        SimpleNamespace(), store, users, window_hours=0, fetch_article_fn=_fetch_distinct,
        draft_fn=lambda source, *_a: DraftCard(source.source_id, "헤드라인", "요약", "왜중요",
                                               (Claim("C1", "ok", "entailment", "core"),)),
        verify_fn=lambda c: (CertVerdict("C1", "VERIFIED", "ev"),),
        run_date="2026-06-29",
    )
    email = out[0].email
    assert "요약 2건" in email                                   # 부제 = 요약(카드) 수(분야 수는 표시 안 함)
    assert "News &amp; Media" in email and "Anthropic" in email     # 분야 밴드(2개+, 발행처)
    assert "6월 29일" in email                                   # run_date → 헤더 날짜


def test_run_briefing_header_date_follows_sent_at_in_recipient_timezone(tmp_path):
    """sent_at(발송 시각)이 있으면 머리 날짜 = 받는 사람 시간대의 날짜. timezone 이 없는 사용자는 Asia/Seoul(설정 기본값)."""
    store = SourceStore(str(tmp_path / "store"))
    out = run_briefing(
        SimpleNamespace(), store, [_user("alice", ["the-decoder"])], window_hours=0, fetch_article_fn=_fetch_distinct,
        draft_fn=lambda source, *_a: DraftCard(source.source_id, "헤드라인", "요약", "왜중요",
                                               (Claim("C1", "ok", "entailment", "core"),)),
        verify_fn=lambda c: (CertVerdict("C1", "VERIFIED", "ev"),),
        run_date="2026-10-17", sent_at=datetime(2026, 10, 17, 20, 0, tzinfo=timezone.utc),
    )
    assert "10월 18일 (일)" in out[0].email and "10월 17일" not in out[0].email


# ── 오늘의 핵심 3 (top_pick_fn) ─────────────────────────
def _fetch_three(source, _w):
    """출처당 서로 다른 기사 3건 — 출처 2개면 발행 카드 6장(핵심 3 문턱)."""
    return [FetchedArticle(source.key, f"https://x/{source.key}/{i}", f"{source.key} AI 제목 {i}",
                           f"{source.key} 고유 AI 본문 {i}.", "2026-06-27T00:00:00Z") for i in range(3)]


def _top_kw(sources=("the-decoder", "claude-blog")):
    return dict(window_hours=0, fetch_article_fn=_fetch_three,
                draft_fn=lambda source, *_a: DraftCard(source.source_id, source.title, "요약", "왜중요",
                                                       (Claim("C1", "ok", "entailment", "core"),)),
                verify_fn=lambda c: (CertVerdict("C1", "VERIFIED", "ev"),))


def test_run_briefing_top_picks_once_per_card_set_and_rendered_first(tmp_path):
    """같은 카드 묶음을 받는 사용자들은 판정 1회를 공유하고(lens 무관 — 재료는 사실층), 핵심 3 이 메일 맨 앞에 온다."""
    calls = []

    def top(cards, k):
        calls.append(([g.card.headline for g in cards], k))
        return list(cards)[-3:]

    users = [_user("alice", ["the-decoder", "claude-blog"]), _user("bob", ["the-decoder", "claude-blog"], lens="engineer")]
    from briefing.core.authoring.author import Interpretation

    out = run_briefing(SimpleNamespace(), SourceStore(str(tmp_path / "store")), users, top_pick_fn=top,
                       interp_fn=lambda source, claims, user, settings, summary="":
                       Interpretation(f"{user.lens} 관점 해석", (claims[0].id,)), **_top_kw())
    assert len(calls) == 1 and len(calls[0][0]) == 6 and calls[0][1] == 3
    for b in out:
        assert b.published == 6
        # catalog 순서상 Anthropic(claude-blog) → News & Media(the-decoder) — 뒤 3장(decoder)이 핵심으로 올라가고
        # 남는 밴드는 Anthropic 이다(2026-10-20 섹션 순서 변경).
        assert b.email.index("오늘의 핵심") < b.email.index("◆ Anthropic")


def test_run_briefing_skips_top_picks_under_threshold(tmp_path):
    def boom(_c, _k):
        raise AssertionError("발행 카드 6장 미만이면 판정 호출 금지(비용 0)")

    out = run_briefing(SimpleNamespace(), SourceStore(str(tmp_path / "store")), [_user("u", ["the-decoder"])],
                       top_pick_fn=boom, **_top_kw())
    assert out[0].published == 3 and "오늘의 핵심" not in out[0].email


def test_run_briefing_top_pick_failure_sends_without_section(tmp_path, capsys):
    def boom(_c, _k):
        raise RuntimeError("throttled")

    out = run_briefing(SimpleNamespace(), SourceStore(str(tmp_path / "store")),
                       [_user("u", ["the-decoder", "claude-blog"])], top_pick_fn=boom, **_top_kw())
    assert out[0].published == 6 and "오늘의 핵심" not in out[0].email   # 핵심 칸만 빠지고 발송은 그대로
    assert "WARN" in capsys.readouterr().err                              # non-silent


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


def test_run_briefing_quarantined_is_sent_once(tmp_path):
    """격리 카드도 ⚠ 표시로 메일에 실린다(N5, 2026-10-18 사용자 결정) → 받은 기사이므로 다음날 다시 안 보낸다.

    (예전 의미론 'QUARANTINE 은 다음날 재도전'은 격리 카드를 보내지 않던 때의 전제였다.)
    """
    from briefing.core.stores.ledger import LocalLedger

    store = SourceStore(str(tmp_path / "store"))
    ledger = LocalLedger(str(tmp_path / "led"))
    users = [_user("u", ["aws-ml"])]
    d1 = run_briefing(SimpleNamespace(), store, users, ledger=ledger, run_date="2026-07-10",
                      **_dedup_kw(published_verdict="BLOCKED"))   # core BLOCKED → QUARANTINE
    assert d1[0].quarantined == 1 and d1[0].published == 0
    assert "⚠ 요약의 사실" in d1[0].email                     # D1: 격리 카드도 메일에 실림
    d2 = run_briefing(SimpleNamespace(), store, users, ledger=ledger, run_date="2026-07-11", **_dedup_kw())
    assert len(d2[0].cards) == 0                              # D2: 이미 받은 기사 — 중복 발송 없음


def test_quarantined_fact_gets_lens_interpretation(tmp_path):
    """격리 카드도 관점 해석을 붙인다(사용자 요청) — 근거는 확인된 claim 만."""
    from briefing.core.authoring.author import Interpretation

    store = SourceStore(str(tmp_path / "store"))
    claims = (Claim("C1", "막힌 주장", "entailment", "core"), Claim("C2", "확인된 주장", "entailment", "supporting"))
    seen: list = []

    def interp(source, verified, user, settings, summary=""):
        seen.append(tuple(c.id for c in verified))
        return Interpretation("engineer 관점 해석", ("C2",))

    out = run_briefing(
        SimpleNamespace(), store, [_user("u", ["aws-ml"], lens="engineer")], window_hours=0, fetch_article_fn=_fetch,
        draft_fn=lambda source, *_a: DraftCard(source.source_id, "H", "S", "일반 해석", claims),
        revise_fn=lambda *_a, **_k: DraftCard("sid", "H", "S", "일반 해석", claims),
        verify_fn=lambda c: (CertVerdict("C1", "BLOCKED", "ev"), CertVerdict("C2", "VERIFIED", "ev")),
        interp_fn=interp,
    )
    assert out[0].quarantined == 1
    assert seen == [("C2",)]                                   # 확인된 claim 만 해석 재료로
    assert "engineer 관점 해석" in out[0].email


# ── 기사 신원 dedup (2026-10-16 — 해시·URL·제목 키 + source-store join + 90일) ──


def _fetch_one(url, title, text):
    """고정된 기사 1건을 내주는 fetch fake — 날마다 본문/URL 을 바꿔 원문 수정·slug 변경을 재현한다."""
    def f(source, _w):
        return [FetchedArticle(source.key, url, title, text, "2026-10-08T00:00:00Z")]
    return f


def _kw(fetch, verdict="VERIFIED"):
    kw = _dedup_kw(verdict)
    kw["fetch_article_fn"] = fetch
    return kw


_MLDRIFT_URL = "https://developers.googleblog.com/ml-drift-next-gen-gpu-aiml-inference-at-the-edge/"
_MLDRIFT = "ML Drift: Next-Gen GPU AI/ML Inference at the Edge"
_AWSKR = "Strands Agents와 Amazon Bedrock AgentCore을 이용한 발전설비진단 구현하기"


def test_dedup_catches_edited_article_by_url(tmp_path, capsys):
    """원문이 고쳐져 해시가 바뀌어도 URL 이 같으면 다음날 제외 — ML Drift(10-08→10-09) 재현."""
    from briefing.core.stores.ledger import LocalLedger

    store, ledger = SourceStore(str(tmp_path / "store")), LocalLedger(str(tmp_path / "led"))
    users = [_user("u", ["aws-ml"])]
    d1 = run_briefing(SimpleNamespace(), store, users, ledger=ledger, run_date="2026-10-08",
                      **_kw(_fetch_one(_MLDRIFT_URL, _MLDRIFT, "원문 v1. 직원 약 100명.")))
    d2 = run_briefing(SimpleNamespace(), store, users, ledger=ledger, run_date="2026-10-09",
                      **_kw(_fetch_one(_MLDRIFT_URL, _MLDRIFT, "원문 v2(한 문단 수정). 직원 약 100명.")))
    assert d1[0].published == 1 and d2[0].published == 0
    assert "url 키 일치" in capsys.readouterr().err


def test_dedup_catches_slug_change_by_title(tmp_path, capsys):
    """slug 오타 수정으로 URL·해시가 둘 다 바뀌어도 같은 매체·같은 제목이면 제외 — AWS KR(09-22→09-23) 재현."""
    from briefing.core.stores.ledger import LocalLedger

    store, ledger = SourceStore(str(tmp_path / "store")), LocalLedger(str(tmp_path / "led"))
    users = [_user("u", ["aws-ml"])]
    run_briefing(SimpleNamespace(), store, users, ledger=ledger, run_date="2026-09-22",
                 **_kw(_fetch_one("https://aws.amazon.com/ko/blogs/tech/arae-energy/", _AWSKR, "arae 본문. 직원 약 100명.")))
    d2 = run_briefing(SimpleNamespace(), store, users, ledger=ledger, run_date="2026-09-23",
                      **_kw(_fetch_one("https://aws.amazon.com/ko/blogs/tech/narae-energy/", _AWSKR, "narae 본문. 직원 약 100명.")))
    assert d2[0].published == 0
    assert "title 키 일치" in capsys.readouterr().err


def test_dedup_lookback_boundary(tmp_path):
    """정확히 lookback 일 전 발행은 막고, 그 하루 뒤에는 다시 보낸다(창 밖)."""
    from briefing.core.stores.ledger import LocalLedger

    store, ledger = SourceStore(str(tmp_path / "store")), LocalLedger(str(tmp_path / "led"))
    users = [_user("u", ["aws-ml"])]
    s = SimpleNamespace(dedup_lookback_days=90)
    assert run_briefing(s, store, users, ledger=ledger, run_date="2026-07-18", **_dedup_kw())[0].published == 1
    assert run_briefing(s, store, users, ledger=ledger, run_date="2026-10-16", **_dedup_kw())[0].published == 0  # 90일 전 = 포함
    assert run_briefing(s, store, users, ledger=ledger, run_date="2026-10-17", **_dedup_kw())[0].published == 1  # 91일 전 = 창 밖


def test_dedup_meta_missing_falls_back_to_hash(tmp_path, capsys):
    """source-store 에 원본이 없는 과거 발행(2026-08-01 이전 TTL 만료분)은 해시로만 비교 — fail-open."""
    from briefing.core.stores.ledger import LocalLedger

    store, ledger = SourceStore(str(tmp_path / "store")), LocalLedger(str(tmp_path / "led"))
    users = [_user("u", ["aws-ml"])]
    ledger.append("2026-10-08", "u", "gone-sid", "k", "PUBLISH", "H")     # 원본 없는(dangling) 포인터
    d = run_briefing(SimpleNamespace(), store, users, ledger=ledger, run_date="2026-10-09",
                     **_kw(_fetch_one(_MLDRIFT_URL, _MLDRIFT, "원문. 직원 약 100명.")))
    assert d[0].published == 1                                            # 막을 근거가 없으면 막지 않는다
    assert "원본 없는 이전 발행 1건" in capsys.readouterr().err


class _CountingStore(SourceStore):
    """get_meta 호출을 세는 store — run 메모(사용자 간 공유)가 재조회를 막는지 확인."""

    def __init__(self, root):
        super().__init__(root)
        self.meta_calls: list[list[str]] = []

    def get_meta(self, source_ids):
        ids = list(source_ids)
        self.meta_calls.append(ids)
        return super().get_meta(ids)


def test_dedup_meta_join_shared_across_users(tmp_path):
    """같은 기사를 받은 두 번째 사용자는 source-store 를 다시 읽지 않는다(run 메모)."""
    from briefing.core.stores.ledger import LocalLedger

    store, ledger = _CountingStore(str(tmp_path / "store")), LocalLedger(str(tmp_path / "led"))
    users = [_user("a", ["aws-ml"]), _user("b", ["aws-ml"])]
    run_briefing(SimpleNamespace(), store, users, ledger=ledger, run_date="2026-10-08",
                 **_kw(_fetch_one(_MLDRIFT_URL, _MLDRIFT, "원문 v1. 직원 약 100명.")))
    store.meta_calls.clear()
    d2 = run_briefing(SimpleNamespace(), store, users, ledger=ledger, run_date="2026-10-09",
                      **_kw(_fetch_one(_MLDRIFT_URL, _MLDRIFT, "원문 v2. 직원 약 100명.")))
    assert [b.published for b in d2] == [0, 0]
    assert len(store.meta_calls) == 1                     # 첫 사용자만 조회, 두 번째는 메모 히트


class _FailingMetaStore(SourceStore):
    """source-store 조회가 예외를 던지는 store — DDB ClientError(RequestLimitExceeded 등) 재현."""

    def get_meta(self, source_ids):
        raise RuntimeError("RequestLimitExceeded (simulated)")


def test_dedup_join_failure_does_not_abort_briefing(tmp_path, capsys):
    """dedup join 이 예외를 던져도 브리핑은 나간다 — 그 run 만 dedup off(fail-open) + warn. 빈 메일함보다 중복 1건이 낫다."""
    from briefing.core.stores.ledger import LocalLedger

    store, ledger = _FailingMetaStore(str(tmp_path / "store")), LocalLedger(str(tmp_path / "led"))
    users = [_user("u", ["aws-ml"])]
    ledger.append("2026-10-08", "u", "prev-sid", "k", "PUBLISH", "H")   # 과거 발행이 있어야 join 이 호출된다
    d = run_briefing(SimpleNamespace(), store, users, ledger=ledger, run_date="2026-10-09", **_dedup_kw())
    assert d[0].published == 1
    assert "dedup off" in capsys.readouterr().err


def test_dedup_title_key_only_within_short_window(tmp_path):
    """같은 매체가 같은 제목을 반복 쓰는 연재(월간 호 등)는 한 달 뒤 새 호를 막지 않는다 — 제목 키는 짧은 창만."""
    from briefing.core.stores.ledger import LocalLedger

    store, ledger = SourceStore(str(tmp_path / "store")), LocalLedger(str(tmp_path / "led"))
    users = [_user("u", ["aws-ml"])]
    title = "What's new in Amazon Bedrock this month"
    run_briefing(SimpleNamespace(), store, users, ledger=ledger, run_date="2026-09-01",
                 **_kw(_fetch_one("https://aws.amazon.com/blogs/ml/whats-new-2026-09/", title, "9월호. 직원 약 100명.")))
    d = run_briefing(SimpleNamespace(), store, users, ledger=ledger, run_date="2026-10-01",
                     **_kw(_fetch_one("https://aws.amazon.com/blogs/ml/whats-new-2026-10/", title, "10월호. 직원 약 100명.")))
    assert d[0].published == 1                    # 30일 뒤 같은 제목·다른 URL·다른 본문 = 새 호 → 보낸다


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

    def interp(source, claims, user, settings, summary=""):
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


# ── 헤드라인 전용 소스(aitimes): 본문 미수집 · 구독자 메일에만 제목·링크 칸 ──
def _headline_feed(source, _w):
    return [FetchedArticle(source.key, "https://www.aitimes.com/n/1", "국내 AI 반도체 신제품 공개", "",
                           "2026-10-17T00:00:00+00:00")]


def test_run_briefing_attaches_headlines_only_to_subscribers(tmp_path):
    store = SourceStore(str(tmp_path / "store"))
    users = [_user("alice", ["aws-ml", "aitimes"]), _user("bob", ["aws-ml"])]
    out = run_briefing(
        SimpleNamespace(), store, users, window_hours=0, fetch_article_fn=_fetch,
        headline_fetch_fn=_headline_feed,
        draft_fn=lambda source, *_a: DraftCard(source.source_id, "H", "S", "W",
                                               (Claim("C1", "ok", "entailment", "core"),)),
        verify_fn=lambda c: (CertVerdict("C1", "VERIFIED", "ev"),),
    )
    assert "국내 AI 반도체 신제품 공개" in out[0].email           # aitimes 구독자 → 헤드라인 칸
    assert "국내 AI 반도체 신제품 공개" not in out[1].email       # 비구독자 → 없음
    assert out[0].published == 1                                 # aitimes 는 카드를 만들지 않는다(aws-ml 1건뿐)


def test_run_briefing_never_fetches_bodies_for_headlines_only(tmp_path):
    store = SourceStore(str(tmp_path / "store"))
    calls: list[str] = []

    def fetch(source, w):
        calls.append(source.key)
        return _fetch(source, w)

    run_briefing(
        SimpleNamespace(), store, [_user("u", ["aws-ml", "aitimes"])], window_hours=0,
        fetch_article_fn=fetch, headline_fetch_fn=lambda _s, _w: [],
        draft_fn=lambda source, *_a: DraftCard(source.source_id, "H", "S", "W",
                                               (Claim("C1", "ok", "entailment", "core"),)),
        verify_fn=lambda c: (CertVerdict("C1", "VERIFIED", "ev"),),
    )
    assert calls == ["aws-ml"]                                   # aitimes 본문 fetch 0회


def test_run_briefing_threads_headline_area_fn(tmp_path):
    out = run_briefing(
        SimpleNamespace(), SourceStore(str(tmp_path / "store")), [_user("u", ["aws-ml", "aitimes"])], window_hours=0,
        fetch_article_fn=_fetch, headline_fetch_fn=_headline_feed,
        headline_area_fn=lambda titles: ["Industry & Business"] * len(titles),
        draft_fn=lambda source, *_a: DraftCard(source.source_id, "H", "S", "W",
                                               (Claim("C1", "ok", "entailment", "core"),)),
        verify_fn=lambda c: (CertVerdict("C1", "VERIFIED", "ev"),),
    )
    assert "Industry &amp; Business 1" in out[0].email           # 분야 소제목이 메일까지 온다


def test_run_briefing_passes_card_source_titles_as_covered(tmp_path):
    store = SourceStore(str(tmp_path / "store"))
    seen = {}

    def hsel(cands, k, covered):
        seen["covered"] = list(covered)
        return [(a, "해외") for a in list(cands)[:k]]

    run_briefing(
        SimpleNamespace(), store, [_user("u", ["aws-ml", "aitimes"])], window_hours=0,
        fetch_article_fn=_fetch, headline_fetch_fn=_headline_feed, headline_select_fn=hsel,
        draft_fn=lambda source, *_a: DraftCard(source.source_id, "H", "S", "W",
                                               (Claim("C1", "ok", "entailment", "core"),)),
        verify_fn=lambda c: (CertVerdict("C1", "VERIFIED", "ev"),),
    )
    assert seen["covered"] == ["제목"]   # aws-ml 동결본 제목(_fetch) — 헤드라인이 카드와 겹치지 않게
