"""top_picks — 라벨 1회로 핵심 3 + 분야 밴드: 보이는 카드(PUBLISH+⚠)마다 라벨(org·type·importance·event·area), 선택·분야는 코드.

기준(2026-10-20): 5대 기업 큰 발표(≤2) → 응용 AI·에이전트(있으면 ≥1). LLM 은 라벨만, 배분은 코드(assign_top).
"""
import json

import pytest

from briefing.core.authoring.author import Claim, DraftCard
from briefing.core.gate import GatedCard
from briefing.core.top_picks import (
    DEMOTED_BIG,
    ranks,
    TOP_MIN_CARDS,
    LabelIncomplete,
    _parse_labels,
    areas_of,
    assign_top,
    big_org,
    label_cards,
    labels_complete,
    llm_labels,
    pick_top,
    tier,
)
from briefing.core.verification.certifier import CertVerdict


def _g(sid, decision="PUBLISH"):
    card = DraftCard(sid, f"제목-{sid}", f"요약-{sid}", f"해석-{sid}", (Claim("C1", "x", "entailment", "core"),))
    return GatedCard(card, (CertVerdict("C1", "VERIFIED", "ev"),), decision, 1)


def _cards(n):
    return [_g(f"s{i}") for i in range(1, n + 1)]


def _lb(n, org="", type_="other", importance=3, event="", area="AI Agents"):
    """0-기반 라벨(assign_top 입력). area 는 2026-10-24 추가 필드 — 닫힌 목록(areas.AREAS) 정확 일치."""
    return {"n": n, "org": org, "type": type_, "importance": importance, "event": event or f"ev{n}", "area": area}


# ── 결정론 규칙: 5대 기업 · 등급 · 배분 ──────────────────────────────────────────

def test_big_org_normalizes_the_five_and_rejects_others():
    assert [big_org(o) for o in ("Anthropic", "OpenAI", "AWS", "Amazon Web Services", "Google DeepMind", "Meta AI")] \
        == ["Anthropic", "OpenAI", "Amazon", "Amazon", "Google", "Meta"]
    assert [big_org(o) for o in ("Microsoft", "DeepSeek", "Z.ai", "TwelveLabs", "")] == ["", "", "", "", ""]


def test_tier_requires_big_org_and_announcement_type():
    assert tier(_lb(0, "Google", "launch")) == 1
    assert tier(_lb(0, "Anthropic", "policy")) == 1
    assert tier(_lb(0, "Microsoft", "launch")) == 4     # 5대 기업이 아니면 출시라도 큰 발표 아님(10-16 실측 오분류)
    assert tier(_lb(0, "Google", "other")) == 4         # 5대 기업이어도 판결·비평 등은 큰 발표 아님
    assert tier(_lb(0, "", "applied")) == 2             # area 기본값 AI Agents


def test_tier_applied_slot_prefers_agents_and_applied_ai_areas():
    """2026-10-30 사용자 관심(AI Agents·Applied AI·5대 기업 큰 발표): 응용 칸(2티어)은 분야가 AI Agents/Applied AI 일 때만.
    type applied 라도 Inference & Hardware 등 다른 분야면 그 밖(3티어) — 10-29 'Nemotron on EKS' 가 응용 칸을 차지한 사례."""
    assert tier(_lb(0, "", "applied", area="AI Agents")) == 2
    assert tier(_lb(0, "", "applied", area="Applied AI")) == 3                  # 10-30 우선순위: Agents(2) 다음
    assert tier(_lb(0, "", "applied", area="Inference & Hardware")) == 4
    assert tier(_lb(0, "", "applied", area="Models & Releases")) == 4
    assert tier(_lb(0, "Amazon", "applied", area="Inference & Hardware")) == 4   # 5대 기업이어도 applied 는 큰 발표 아님
    assert tier(_lb(0, "Google", "launch", area="Inference & Hardware")) == 1    # 큰 발표는 분야 무관


def test_assign_applied_slot_takes_agents_area_over_infra_howto():
    # 10-29 재현: 큰 발표 1 + applied 셋(인프라 how-to 3 · Applied AI 3 · AI Agents 3) → 응용 칸은 선호 분야 둘, 인프라는 3티어
    labels = [_lb(0, "Anthropic", "policy", 3, area="Applied AI"),
              _lb(1, "Amazon", "applied", 3, area="Inference & Hardware"),
              _lb(2, "Amazon", "applied", 3, area="Applied AI"),
              _lb(3, "Google", "applied", 3, area="AI Agents")]
    secs = ["Anthropic", "Amazon (AWS)", "Amazon (AWS)", "Google"]
    assert assign_top(labels, secs) == [0, 3, 2]          # 큰 발표 → AI Agents → Applied AI (엄격 순서, 10-30)
    # 선호 분야 applied 가 없으면 기존대로 그 밖에서 채운다 — 인프라 how-to 도 후보(중요도순)
    labels2 = [_lb(0, "Anthropic", "policy", 3, area="Applied AI"),
               _lb(1, "Amazon", "applied", 3, area="Inference & Hardware"),
               _lb(2, "", "other", 4, area="Safety, Security & Policy")]
    assert assign_top(labels2, ["Anthropic", "Amazon (AWS)", "News & Media"]) == [0, 2, 1]


def test_assign_strict_priority_agents_before_applied_ai_regardless_of_importance():
    """2026-10-30 사용자 우선순위: ① 큰 발표 → ② AI Agents → ③ Applied AI. 중요도는 같은 등급 안에서만."""
    labels = [_lb(0, "Google", "launch", 5), _lb(1, "", "applied", 3, area="AI Agents"),
              _lb(2, "", "applied", 5, area="Applied AI")]
    assert assign_top(labels, ["Google", "Community", "Amazon (AWS)"]) == [0, 1, 2]   # Applied AI 5 보다 Agents 3 이 먼저


def test_assign_big_demoted_when_less_important_than_best_agents():
    """Arel: 큰 발표는 그날 최고 AI Agents 후보 importance 이상일 때만 1순위(동점은 큰 발표). 10-25 재현 —
    Open Responses(OpenAI policy 3) vs "one agent beats many subagents"(Agents 4) → Agents 가 앞, 큰 발표는 Agents 다음."""
    labels = [_lb(0, "OpenAI", "policy", 3, area="AI Agents"),
              _lb(1, "Anthropic", "applied", 4, area="AI Agents"),
              _lb(2, "Anthropic", "applied", 3, area="AI Agents")]
    secs = ["Community", "News & Media", "Community"]
    assert ranks(labels) == {0: DEMOTED_BIG, 1: 2, 2: 2}
    assert assign_top(labels, secs) == [1, 2, 0]
    # 동점(10-29): AI for Science 3 vs 최고 Agents 3 → 큰 발표가 1순위 유지
    tie = [_lb(0, "Anthropic", "policy", 3, area="Applied AI"), _lb(1, "Google", "applied", 3, area="AI Agents"),
           _lb(2, "Amazon", "applied", 3, area="Applied AI")]
    assert assign_top(tie, ["Anthropic", "Google", "Amazon (AWS)"]) == [0, 1, 2]
    # 강등된 큰 발표는 Applied AI 보다 앞, 큰 발표 합계 ≤MAX_BIG·회사당 1장은 그대로
    four = [_lb(0, "Google", "launch", 4), _lb(1, "OpenAI", "launch", 4), _lb(2, "Meta", "launch", 3),
            _lb(3, "", "applied", 4, area="AI Agents"), _lb(4, "", "applied", 3, area="Applied AI")]
    secs4 = ["Google", "News & Media", "News & Media", "Community", "Amazon (AWS)"]
    assert assign_top(four, secs4, k=4) == [0, 1, 3, 4]          # Meta 3 은 강등 + 큰 발표 2장 찼음 → Applied AI 가 4번째
    assert assign_top(four[1:], secs4[1:], k=4) == [1, 3, 2, 4]  # 큰 발표 1장뿐이면 강등분(Meta)이 Agents 다음·Applied AI 앞


def test_pick_top_log_marks_demoted_big(capsys):
    cards = _cards(6)
    labels = [_lb(0, "OpenAI", "policy", 3), _lb(1, "", "applied", 4, area="AI Agents"),
              _lb(2, "", "applied", 3, area="AI Agents")] + [_lb(i, type_="other") for i in range(3, 6)]
    secs = ["Community", "News & Media", "Amazon (AWS)", "x", "y", "z"]
    assert pick_top(cards, labels, secs) == ("s2", "s3", "s1")
    assert "p1↓" in capsys.readouterr().err                      # 강등된 큰 발표는 로그에서 구분된다


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


# ── LLM 경계: 재료 · 파싱 · 완전성 · 재시도 1회 ────────────────────────────────────
def test_parse_labels_area_must_match_closed_list_exactly():
    labs = _parse_labels(json.dumps([{"n": 1, "type": "other", "area": "ai agents"},
                                     {"n": 2, "type": "other", "area": "AI Agents"}]), 2)
    assert labels_complete(labs, 2).startswith("area")            # 대소문자 다른 값 = 미배정(정규화 금지 → 재시도 → 폴백)


def test_labels_complete_rejects_missing_or_duplicate_n():
    assert labels_complete([_lb(0), _lb(0)], 2) and labels_complete([_lb(0)], 2)
    assert labels_complete([_lb(0), _lb(1)], 2) == ""


def test_llm_labels_sends_shown_cards_with_sections_and_area_definitions():
    seen = {}

    def capture(system, user):
        seen["system"], seen["user"] = system, user
        return json.dumps([{"n": i, "type": "other", "importance": 3, "event": f"e{i}", "area": "AI Agents"}
                           for i in range(1, 4)])

    cards = _cards(2) + [_g("q", decision="QUARANTINE")]
    labs = llm_labels(cards, ["Amazon (AWS)", "Google", ""], invoke=capture)
    assert [lb["n"] for lb in labs] == [0, 1, 2] and all(lb["area"] == "AI Agents" for lb in labs)
    assert "1. [Amazon (AWS)] 제목-s1" in seen["user"] and "요약-s1" in seen["user"]   # 섹션 + 사실층(제목·요약)
    assert "3. 제목-q" in seen["user"] and "해석-s1" not in seen["user"]       # ⚠ 포함 · 해석층 제외(사용자 간 공유)
    assert "Applied AI" in seen["system"] and '"launch"' in seen["system"]      # 분야 정의 추가, 기존 type 문장 유지


def test_label_prompt_narrows_launch_to_new_products_not_features():
    """2026-10-30: launch = 새 모델·새 제품/서비스·플랫폼 GA 만. "major feature" 문구가 how-to·기능 글을 1티어로 끌어들였다
    (10-20~29 1티어의 약 1/4). 실측 근거는 top_picks 모듈 docstring. 정책(5대 기업·칸 배분)은 여전히 코드(assign_top)."""
    from briefing.core.top_picks import _LABEL_SYSTEM
    assert "major feature" not in _LABEL_SYSTEM
    assert "NEW model, NEW product or service, or general availability" in _LABEL_SYSTEM
    assert "tutorials, how-tos and engineering write-ups are NOT launch" in _LABEL_SYSTEM
    assert "Research findings" not in _LABEL_SYSTEM        # 기각된 문구(응용 칸의 연구 픽을 밀어냄) — 되돌아오지 않게
    assert '"importance": <1-5 for an AI practitioner>' in _LABEL_SYSTEM   # 앵커·하한 없음(기각)


def test_llm_labels_retries_once_on_exception_then_succeeds_quietly(capsys):
    calls = []

    def flaky(s, u):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("throttled")
        return json.dumps([{"n": 1, "type": "other", "area": "Models & Releases"}])

    assert llm_labels(_cards(1), [""], invoke=flaky)[0]["area"] == "Models & Releases" and len(calls) == 2
    assert "WARN" not in capsys.readouterr().err                               # 재시도 성공 = 조용히


def test_llm_labels_retries_once_on_partial_then_raises():
    calls = []
    partial = json.dumps([{"n": 1, "type": "other", "area": "AI Agents"}])      # 2장 중 1장(절단 모양)

    def fn(s, u):
        calls.append(1)
        return partial

    with pytest.raises(LabelIncomplete):
        llm_labels(_cards(2), ["", ""], invoke=fn)
    assert len(calls) == 2                                                     # 정확히 1회 재시도


def test_label_cards_gate_counts_publish_only():
    calls = []
    cards = _cards(TOP_MIN_CARDS - 1) + [_g(f"q{i}", decision="QUARANTINE") for i in range(3)]   # 보이는 8장, PUBLISH 5장
    assert label_cards(cards, lambda c, s: calls.append(1) or [], {}, {}) is None and calls == []
    assert label_cards(_cards(TOP_MIN_CARDS), None, {}, {}) is None            # 미주입 = 호출 없음


def test_label_cards_memo_by_shown_set_and_failure_is_none_with_warn(capsys):
    calls = []

    def fn(cards, secs):
        calls.append(([g.card.source_id for g in cards], list(secs)))
        return [_lb(i) for i in range(len(cards))]

    cards = _cards(TOP_MIN_CARDS) + [_g("q", decision="QUARANTINE")]
    memo: dict = {}
    assert label_cards(cards, fn, memo, {"s1": "Anthropic"}) is not None
    assert label_cards(cards, fn, memo, {"s1": "Anthropic"}) is not None and len(calls) == 1   # 같은 묶음 = memo
    assert "q" in calls[0][0] and calls[0][1][:2] == ["Anthropic", ""]        # ⚠ 포함 · 모르는 섹션 = ""
    assert "WARN areas 라벨" in capsys.readouterr().err                         # 성공 시 분포 로그 한 줄

    def boom(c, s):
        raise LabelIncomplete("area 미배정 1/7")

    assert label_cards(cards, boom, {}, {}) is None and "WARN" in capsys.readouterr().err


def test_pick_top_filters_quarantine_in_middle_and_keeps_full_section_indexing():
    cards = [_g("s1"), _g("q", decision="QUARANTINE"), _g("s2"), _g("s3"), _g("s4"), _g("s5"), _g("s6")]
    secs = ["Amazon (AWS)", "News & Media", "Google", "Google", "Community", "Community", "Anthropic"]
    labels = [_lb(0, "AWS", "launch", 5), _lb(1, "OpenAI", "launch", 5), _lb(2, type_="applied", importance=4),
              _lb(3, type_="applied", importance=3), _lb(4, type_="other"), _lb(5, type_="other"),
              _lb(6, "Anthropic", "launch", 4)]
    assert pick_top(cards, labels, secs) == ("s1", "s6", "s2")    # ⚠(q, OpenAI launch) 제외 · 응용 1장 · 섹션 인덱스 전체 기준


def test_pick_top_returns_empty_with_warn_when_fewer_than_k(capsys):
    cards = _cards(6)
    labels = [_lb(0, "Google", "launch", 5), _lb(1, "Google", "launch", 4)] + [_lb(i, type_="other") for i in range(2, 6)]
    secs = ["Google", "Google", "x", "y", "z", "w"]
    assert pick_top(cards, labels, secs) == ("s1", "s3", "s4")    # 회사당 1장 → 그 밖(서로 다른 섹션)에서 채움
    assert pick_top(cards[:3], labels[:3], secs[:3]) == ()        # 유효 선택 2 < 3 → 칸 생략(앞 3장 대체 금지)
    assert "WARN" in capsys.readouterr().err


def test_areas_of_maps_every_shown_card():
    cards = _cards(2) + [_g("q", decision="QUARANTINE")]
    assert areas_of(cards, [_lb(0, area="AI Agents"), _lb(1, area="Applied AI"), _lb(2, area="Models & Releases")]) == {
        "s1": "AI Agents", "s2": "Applied AI", "q": "Models & Releases"}


def test_label_cards_distribution_log_keeps_every_card(capsys):
    """스펙 §7 월 1회 표본 점검은 run 로그의 카드별 분야를 쓴다 — 24장이 400자 절단에 잘리면 안 된다(리뷰 I1)."""
    cards = [_g(f"s{i:02d}") for i in range(1, 25)]
    for g in cards:
        object.__setattr__(g.card, "headline", f"제목-{g.card.source_id}-" + "x" * 50)   # 실제 제목 길이(~60자)
    fn = lambda c, s: [_lb(i, area="AI Agents" if i % 2 else "Applied AI") for i in range(len(c))]  # noqa: E731
    assert label_cards(cards, fn, {}, {}) is not None
    err = capsys.readouterr().err
    line = next(ln for ln in err.splitlines() if "areas 라벨" in ln)
    assert "제목-s24-" in line and "제목-s01-" in line                 # 첫 장도 마지막 장도 로그에 남는다
