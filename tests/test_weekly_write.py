"""weekly.write — 원문(동결/재수집) · 작성 프롬프트(VERIFIED 만) · 출력 파싱 · 피드백 · 재작성 · 씨앗 없음 호(네트워크 0)."""
import json

import pytest

from briefing.core.authoring.author import Claim
from briefing.core.retrieval.sources import TRUNCATED_MIN_CHARS
from briefing.core.stores.source_store import SourceStore
from briefing.weekly.collect import WeekCard
from briefing.weekly.gate import GateItem, GateResult
from briefing.weekly.select import Candidate, Seed
from briefing.weekly.write import (build_revise_user_prompt, build_write_system_prompt, build_write_user_prompt,
                                   feedback_from_gate, none_issue_md, parse_draft, revise, source_text, write)


def _card(n, media, claims, verified, url="https://x/1"):
    return WeekCard(n=n, run_date="2026-11-03", source_id=f"s{n}", card_key=f"k{n}", headline=f"H{n}", summary=f"요약{n}",
                    why="왜", claims=claims, verified_ids=verified, url=url, title=f"T{n}", media=media, cached=True)


A = _card(36, "Anthropic Research", (Claim("C1", "분석가 50명", "arithmetic"), Claim("C2", "86% 일치", "arithmetic"),
                                     Claim("C3", "미검증", "entailment")), ("C1", "C2"))
W = _card(38, "AWS ML Blog", (Claim("C1", "96.8%", "arithmetic"),), ("C1",), url="https://x/38")
SEED = Seed(seed=36, support=(), aws_line=38, mechanism="무작위 입장", experiment="동전", candidates=(), not_chosen=(), reason="")


def test_source_text_frozen_then_refetch_only_when_truncated(tmp_path):
    store = SourceStore(str(tmp_path))
    short = store.freeze(url="https://x/1", title="t", raw_text="짧은 원문", fetched_at="f")
    long_ = store.freeze(url="https://x/2", title="t", raw_text="가" * TRUNCATED_MIN_CHARS, fetched_at="f")
    calls = []

    def refetch(url):
        calls.append(url)
        return "나" * (TRUNCATED_MIN_CHARS + 500)
    c1 = _card(1, "m", (), (), url="https://x/1")
    c2 = WeekCard(**{**c1.__dict__, "n": 2, "source_id": long_.source_id, "url": "https://x/2"})
    c1 = WeekCard(**{**c1.__dict__, "source_id": short.source_id})
    assert source_text(store, c1, refetch=refetch) == "짧은 원문" and calls == []
    assert len(source_text(store, c2, refetch=refetch)) == TRUNCATED_MIN_CHARS + 500 and calls == ["https://x/2"]
    assert len(source_text(store, c2, refetch=lambda u: (_ for _ in ()).throw(RuntimeError("x")))) == TRUNCATED_MIN_CHARS
    assert source_text(store, c2) and source_text(store, WeekCard(**{**c2.__dict__, "source_id": "없음"})) == ""


def test_system_prompt_carries_rules_and_terms():
    s = build_write_system_prompt()
    assert "## 출력 형식" in s and "내 시스템에 대입" in s and "② 의 문장은 전부 사실 문장이다" in s
    assert "- 전염 → 일치율(agreement rate)" in s and "(FAIL: 우리가 만든 비유)" in s and "(WARN: 원문 lean" in s


def test_user_prompt_shows_only_verified_claims_and_texts():
    p = build_write_user_prompt(SEED, [A, W], {36: "원문36", 38: "원문38"}, "2026-11-07", today="2026-11-07")
    assert "기간 줄 = 2026-10-31 ~ 11-06" in p and "씨앗 = #36" in p and "② 보강 한 줄 = #38" in p
    assert "### 카드 #36 (씨앗)" in p and "### 카드 #38 (보강 한 줄)" in p
    assert "- C1: 분석가 50명" in p and "- C2: 86% 일치" in p and "- C3: 미검증" not in p
    assert "동결 원문(4자):\n원문36" in p and p.index("#36") < p.index("#38")


def test_parse_draft_and_errors():
    d = parse_draft("x\n" + json.dumps({"md": "# 제목\n본문", "cites": [{"text": "문장.", "card": "36", "claims": ["C1"]}]}))
    assert d.md == "# 제목\n본문\n" and d.cites[0].card == 36 and d.cites[0].claims == ("C1",)
    assert json.loads(d.to_json())["cites"][0]["text"] == "문장."
    with pytest.raises(ValueError):
        parse_draft(json.dumps({"cites": []}))


def test_feedback_prefers_deterministic_feedback_over_evidence():
    r = GateResult("QUARANTINE", (GateItem("FAIL", "lint 9", "용어 '전염' → 일치율"),
                                  GateItem("FAIL", "cite", "#36 문장… — codex BLOCKED: 원문 근거 …", feedback="#36 문장… — 함의 아님"),
                                  GateItem("WARN", "repo", "오래됨"), GateItem("PASS", "model", "ok")),
                   ("9",), ("#36 문장… — 함의 아님",))
    assert feedback_from_gate(r) == ["용어 '전염' → 일치율", "#36 문장… — 함의 아님"]


def test_write_and_revise_pass_through_fake_author():
    seen = []

    def fake(system, user, settings, **kw):
        seen.append(user)
        return json.dumps({"md": "# 제목\n## ② 이번 주 근거\n문장.", "cites": [{"text": "문장.", "card": 36, "claims": ["C1"]}]})
    d = write(SEED, [A, W], {36: "원문"}, "2026-11-07", settings=None, model_id="m", run_author=fake, today="2026-11-07")
    assert d.cites == (d.cites[0],) and "### 카드 #36" in seen[0]
    d2 = revise(d, ["용어 '전염' → 일치율", "#36 문장. — 함의 아님"], settings=None, run_author=fake)
    assert d2.md == d.md and "이전 초안(JSON)" in seen[1] and "- 용어 '전염' → 일치율" in seen[1] and '"card": 36' in seen[1]
    assert "실패한 것만 고치고" in build_revise_user_prompt(d, ["x"])


def test_none_issue_md():
    s = Seed(seed=None, support=(), aws_line=None, mechanism="", experiment="",
             candidates=(Candidate(36, "Applied AI", False, True, "메커니즘 없음"),), not_chosen=((36, "제품 소식"),),
             reason="선정 #38 거부 — 하드 게이트 1: …")
    md = none_issue_md(s, [A, W], "2026-11-07")
    assert md.startswith("# 이번 주 아이디어 없음\n2026-10-31 ~ 11-06 · 프론티어 1차 글 1편 검토")
    assert "- Anthropic Research — T36 — 제품 소식" in md and "하드 게이트 1" in md
