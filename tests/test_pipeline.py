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


def _label_fake(calls):
    """라벨 seam fake — 카드 순서 = 카탈로그 순(claude-blog 3장 → the-decoder 3장): n=0 Anthropic 큰 발표·n=3 OpenAI 큰 발표·
    n=1 응용 → 핵심 3 성립, 나머지 2·4(Applied AI)·5(AI Agents)."""
    def label(cards, secs):
        calls.append(len(cards))
        base = [{"n": i, "org": "", "type": "other", "importance": 3, "event": f"e{i}",
                 "area": "AI Agents" if i % 2 else "Applied AI"} for i in range(len(cards))]
        base[0].update(org="Anthropic", type="launch")
        base[3].update(org="OpenAI", type="launch")
        base[1].update(type="applied")
        return base
    return label


def test_run_briefing_labels_once_per_card_set_and_renders_picks_then_area_bands(tmp_path):
    """같은 카드 묶음을 받는 사용자들은 라벨 1회를 공유하고(lens 무관 — 재료는 사실층), 핵심 3 → 분야 밴드 순."""
    calls = []
    users = [_user("alice", ["the-decoder", "claude-blog"]), _user("bob", ["the-decoder", "claude-blog"], lens="engineer")]
    from briefing.core.authoring.author import Interpretation

    out = run_briefing(SimpleNamespace(), SourceStore(str(tmp_path / "store")), users, label_fn=_label_fake(calls),
                       interp_fn=lambda source, claims, user, settings, summary="":
                       Interpretation(f"{user.lens} 관점 해석", (claims[0].id,)), **_top_kw())
    assert calls == [6]                                                 # 묶음당 1회(⚠ 없음 → 6장)
    for b in out:
        assert b.published == 6
        assert b.email.index("오늘의 핵심") < b.email.index("◆ AI Agents") < b.email.index("◆ Applied AI")
        assert "◆ Anthropic" not in b.email and "◆ News" not in b.email   # 발행처 밴드는 더 없다(2026-10-24)
        assert "출처 · Anthropic 3 · News &amp; Media 3" in b.email        # 집계 줄(카탈로그 순, 핵심 포함)


def test_run_briefing_skips_labels_under_threshold(tmp_path):
    def boom(_c, _s):
        raise AssertionError("발행 카드 6장 미만이면 라벨 호출 금지(비용 0)")

    out = run_briefing(SimpleNamespace(), SourceStore(str(tmp_path / "store")), [_user("u", ["the-decoder"])],
                       label_fn=boom, **_top_kw())
    assert out[0].published == 3 and "오늘의 핵심" not in out[0].email and "◆" not in out[0].email


def test_run_briefing_label_failure_drops_both_picks_and_bands(tmp_path, capsys):
    """한 호출이 핵심 3 과 분야를 같이 먹이므로 실패한 날은 둘 다 빠진다(평평) — 발송은 그대로(fail-open)."""
    from briefing.core.top_picks import LabelIncomplete

    def boom(_c, _s):
        raise LabelIncomplete("area 미배정 1/6")

    out = run_briefing(SimpleNamespace(), SourceStore(str(tmp_path / "store")),
                       [_user("u", ["the-decoder", "claude-blog"])], label_fn=boom, **_top_kw())
    assert out[0].published == 6 and "오늘의 핵심" not in out[0].email and "◆" not in out[0].email
    assert "출처 · Anthropic 3 · News &amp; Media 3" in out[0].email      # 집계 줄은 결정론 — 실패 날에도
    assert "WARN" in capsys.readouterr().err                              # non-silent


def test_run_briefing_labels_quarantined_cards_too(tmp_path):
    """⚠ 카드도 메일에 실리므로 라벨 입력에 들어간다(9장 = PUBLISH 8 + ⚠ 1) — 게이트는 PUBLISH 수(≥6)로 센다."""
    calls = []
    kw = _top_kw()
    kw["verify_fn"] = lambda c: ((CertVerdict("C1", "BLOCKED", "ev"),) if c.headline.endswith("제목 2") and "decoder" in c.headline
                                 else (CertVerdict("C1", "VERIFIED", "ev"),))
    kw["revise_fn"] = lambda *a, **k: k["prior"]                      # 재작성해도 그대로(prior) → 막힌 claim 유지 = ⚠
    out = run_briefing(SimpleNamespace(), SourceStore(str(tmp_path / "store")),
                       [_user("u", ["the-decoder", "claude-blog", "aws-ml"])], label_fn=_label_fake(calls), **kw)
    assert out[0].published == 8 and out[0].quarantined == 1 and calls == [9]   # 보이는 9장(8+⚠1) 전부 라벨
    assert "◆ AI Agents" in out[0].email and "오늘의 핵심" in out[0].email
