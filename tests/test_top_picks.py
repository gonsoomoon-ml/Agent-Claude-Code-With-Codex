"""top_picks — 오늘의 핵심 3: 발행 카드 전체에서 K장(재료=사실층 제목·요약 + 섹션), 실패면 칸 생략(최신순 대체 없음).

기준(2026-10-20): 5대 기업 큰 발표(≤2) → 응용 AI·에이전트(있으면 ≥1). LLM 은 라벨만, 배분은 코드(assign_top).
"""
import json

from briefing.core.authoring.author import Claim, DraftCard
from briefing.core.gate import GatedCard
from briefing.core.top_picks import (
    TOP_K,
    TOP_MIN_CARDS,
    assign_top,
    big_org,
    llm_top_picks,
    tier,
    top_source_ids,
)
from briefing.core.verification.certifier import CertVerdict


def _g(sid, decision="PUBLISH"):
    card = DraftCard(sid, f"제목-{sid}", f"요약-{sid}", f"해석-{sid}", (Claim("C1", "x", "entailment", "core"),))
    return GatedCard(card, (CertVerdict("C1", "VERIFIED", "ev"),), decision, 1)


def _cards(n):
    return [_g(f"s{i}") for i in range(1, n + 1)]


def _lb(n, org="", type_="other", importance=3, event=""):
    """0-기반 라벨(assign_top 입력)."""
    return {"n": n, "org": org, "type": type_, "importance": importance, "event": event or f"ev{n}"}


# ── 결정론 규칙: 5대 기업 · 등급 · 배분 ──────────────────────────────────────────

def test_big_org_normalizes_the_five_and_rejects_others():
    assert [big_org(o) for o in ("Anthropic", "OpenAI", "AWS", "Amazon Web Services", "Google DeepMind", "Meta AI")] \
        == ["Anthropic", "OpenAI", "Amazon", "Amazon", "Google", "Meta"]
    assert [big_org(o) for o in ("Microsoft", "DeepSeek", "Z.ai", "TwelveLabs", "")] == ["", "", "", "", ""]


def test_tier_requires_big_org_and_announcement_type():
    assert tier(_lb(0, "Google", "launch")) == 1
    assert tier(_lb(0, "Anthropic", "policy")) == 1
    assert tier(_lb(0, "Microsoft", "launch")) == 3     # 5대 기업이 아니면 출시라도 큰 발표 아님(10-16 실측 오분류)
    assert tier(_lb(0, "Google", "other")) == 3         # 5대 기업이어도 판결·비평 등은 큰 발표 아님
    assert tier(_lb(0, "", "applied")) == 2


def test_assign_caps_big_announcements_and_keeps_one_applied():
    labels = [_lb(0, "OpenAI", "launch", 5), _lb(1, "Google", "launch", 5), _lb(2, "Meta", "launch", 4),
              _lb(3, "", "applied", 2), _lb(4, "", "other", 5)]
    secs = ["News & Media", "Google", "Community", "Amazon (AWS)", "News & Media"]
    assert assign_top(labels, secs) == [0, 1, 3]          # 큰 발표 2 + 응용 1(중요도 낮아도), 큰 발표 먼저


def test_assign_fills_with_more_big_when_no_applied_then_other():
    labels = [_lb(0, "OpenAI", "launch", 5), _lb(1, "Google", "launch", 4), _lb(2, "Meta", "launch", 3),
              _lb(3, "", "other", 5)]
    assert assign_top(labels, [""] * 4) == [0, 1, 2]       # 응용이 없으면 큰 발표로 채운다
    assert assign_top([_lb(0, "", "other", 1), _lb(1, "", "other", 4), _lb(2, "", "applied", 2)],
                      ["a", "b", "c"]) == [2, 1, 0]        # 큰 발표가 없는 날: 응용 → 그 밖(중요도순)


def test_assign_drops_same_event_and_second_applied_from_same_section():
    labels = [_lb(0, "Anthropic", "policy", 5, event="public benefit fund"),
              _lb(1, "", "applied", 4, event="eks agent isolation part2"),
              _lb(2, "", "applied", 4, event="eks agent isolation part1"),   # event 키가 달라도(10-18 실측)
              _lb(3, "", "applied", 3),
              _lb(4, "OpenAI", "launch", 4, event="public benefit fund")]    # 같은 event = 같은 사건
    secs = ["Anthropic", "Amazon (AWS)", "Amazon (AWS)", "Community", "News & Media"]
    assert assign_top(labels, secs) == [0, 1, 3]          # AWS 연재 2부·1부 중 1장, 같은 사건 둘 금지


def test_assign_one_big_announcement_per_company():
    labels = [_lb(0, "Google", "launch", 5, event="gemini robotics"),
              _lb(1, "Google DeepMind", "launch", 5, event="gemini safety"),   # 같은 발표의 다른 글(10-13 실측)
              _lb(2, "OpenAI", "launch", 4), _lb(3, "", "applied", 2)]
    assert assign_top(labels, ["Google", "Google", "News & Media", "Community"]) == [0, 2, 3]
    only_google = [_lb(0, "Google", "launch", 5), _lb(1, "Google", "launch", 4), _lb(2, "", "other", 1)]
    assert assign_top(only_google, ["Google", "Google", "x"]) == [0, 2]   # 회사당 1장 — 다른 후보가 없으면 칸이 모자란다


def test_assign_allows_two_big_from_same_section():
    labels = [_lb(0, "Google", "launch", 5), _lb(1, "Anthropic", "policy", 4), _lb(2, "", "applied", 3)]
    secs = ["News & Media", "News & Media", "Amazon (AWS)"]   # 뉴스 칸이 두 회사의 발표를 함께 보도(10-14 실측)
    assert assign_top(labels, secs) == [0, 1, 2]


# ── LLM 경계: 재료 · 파싱 · 실패 ─────────────────────────────────────────────────

def test_llm_top_picks_sends_fact_layer_and_sections_and_returns_display_order():
    seen = {}

    def capture(system, user):
        seen["system"], seen["user"] = system, user
        return json.dumps([{"n": 1, "org": "", "type": "applied", "importance": 3, "event": "a"},
                           {"n": 2, "org": "AWS", "type": "launch", "importance": 4, "event": "b"},
                           {"n": 3, "org": "", "type": "other", "importance": 5, "event": "c"},
                           {"n": 4, "org": "DeepSeek", "type": "launch", "importance": 5, "event": "d"}])

    cards = _cards(6)
    secs = ["Community", "Amazon (AWS)", "News & Media", "News & Media", "Google", "Google"]
    got = llm_top_picks(cards, 3, secs, invoke=capture)
    # AWS 출시(큰 발표) → 응용 → 그 밖. DeepSeek 출시는 큰 발표 아님 + 같은 섹션(News & Media) 두 번째라 빠진다
    assert got == [cards[1], cards[0], cards[2]]
    assert "1. [Community] 제목-s1" in seen["user"] and "요약-s1" in seen["user"]   # 섹션 + 사실층(제목·요약)
    assert "해석-s1" not in seen["user"]                           # 해석층은 lens 별 → 넣으면 사용자 간 공유가 깨짐
    assert '"launch"' in seen["system"] and '"applied"' in seen["system"]


def test_llm_top_picks_returns_empty_on_failure_not_latest(capsys):
    cards = _cards(6)
    assert llm_top_picks(cards, 3, invoke=lambda s, u: "글쎄요") == []   # 앞 3장 대체 금지
    assert "WARN" in capsys.readouterr().err
    two = json.dumps([{"n": 1, "type": "applied"}, {"n": 2, "type": "other"}, {"n": 99, "type": "launch"}])
    assert llm_top_picks(cards, 3, invoke=lambda s, u: two) == []        # 유효 라벨 2장 < 3 → 칸 생략

    def boom(_s, _u):
        raise RuntimeError("throttled")

    assert llm_top_picks(cards, 3, invoke=boom) == []


def test_top_source_ids_threshold_memo_sections_and_quarantine_excluded():
    calls = []

    def fn(cards, k, sections):
        calls.append(([g.card.source_id for g in cards], list(sections)))
        return list(cards)[:k]

    memo: dict = {}
    assert top_source_ids(_cards(TOP_MIN_CARDS - 1), fn, memo) == () and calls == []   # 문턱 미만 → 호출 없음
    cards = _cards(TOP_MIN_CARDS) + [_g("q", decision="QUARANTINE")]
    secs = {"s1": "Anthropic", "s2": "Google"}
    assert top_source_ids(cards, fn, memo, secs) == ("s1", "s2", "s3")[:TOP_K]
    assert top_source_ids(cards, fn, memo, secs) == ("s1", "s2", "s3")[:TOP_K] and len(calls) == 1   # 같은 묶음 = memo
    assert "q" not in calls[0][0]                                                                     # 발행 카드만 후보
    assert calls[0][1][:3] == ["Anthropic", "Google", ""]                                             # 모르는 섹션 = ""
    assert top_source_ids(cards, None, {}) == ()                                                      # 미주입 = 칸 없음
