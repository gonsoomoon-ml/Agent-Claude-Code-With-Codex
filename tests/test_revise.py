"""S4(2026-10-18) — 막힌 claim 을 다시 쓸 때 그 claim 이 덮는 요약 문장만 고치게 한다.

다시 쓰기 지시는 이전 요약·막힌 claim·고칠 문장을 보여 주고(검증 AI 의 이유는 주지 않는다 — decorrelation),
gate 의 diff guard 는 고칠 문장 밖이 바뀌었거나 문장이 늘면 다시 쓴 카드를 버린다(이전 카드를 ⚠ 로).
"""
import inspect

from briefing.core.authoring.author import (
    Claim, DraftCard, _build_revise_prompt, revise_targets, summary_sentences,
)
from briefing.core.stores.source_store import FrozenSource

SRC = FrozenSource("sid", "https://example.com/a", "제목", "원문 본문이다.", "2026-10-18T00:00:00Z")
PRIOR = DraftCard(
    "sid", "제목",
    "OpenAI는 GPT-X를 공개했다. GPT-X는 SWE-bench Verified에서 72%를 기록했다. 가격은 월 20달러다.",
    "개발자에게 의미가 크다.",
    (Claim("C1", "OpenAI는 GPT-X를 공개했다.", "entailment", "core"),
     Claim("C2", "GPT-X는 SWE-bench Verified에서 72%를 기록했다.", "arithmetic", "core"),
     Claim("C3", "GPT-X의 가격은 월 20달러다.", "arithmetic", "supporting")),
)


def test_summary_sentences_split_after_sentence_end():
    assert summary_sentences(PRIOR.summary) == [
        "OpenAI는 GPT-X를 공개했다.", "GPT-X는 SWE-bench Verified에서 72%를 기록했다.", "가격은 월 20달러다."]


def test_revise_targets_map_failed_claim_to_the_sentence_it_covers():
    """고칠 문장 = 막힌 claim 과 낱말이 가장 많이 겹치는 요약 문장(숫자·영문 이름·두 글자 이상 한글 낱말)."""
    assert revise_targets(PRIOR, ("C2",)) == (1,)
    assert revise_targets(PRIOR, ("C3", "C2")) == (1, 2)
    assert revise_targets(PRIOR, ()) == ()


def test_revise_targets_empty_when_no_sentence_matches():
    """겹치는 문장이 없으면(요약 밖 사실) 고칠 문장이 없다 — 요약은 그대로 두고 claim 만 다시 도출한다."""
    prior = DraftCard("sid", "제목", PRIOR.summary, "w", (Claim("C9", "임원 교체가 발표됐다.", "entailment", "core"),))
    assert revise_targets(prior, ("C9",)) == ()


def test_revise_prompt_shows_prior_summary_failed_claim_and_target_sentence():
    p = _build_revise_prompt(SRC, PRIOR, ("C2",), today="2026-10-18")
    assert "오늘 날짜: 2026-10-18" in p and PRIOR.summary in p and PRIOR.why_it_matters in p
    assert "- C2 [재도출 필요]: GPT-X는 SWE-bench Verified에서 72%를 기록했다." in p and "- C1 [유지]:" in p
    targets = p.split("고칠 요약 문장")[1].split("규칙:")[0]
    assert "GPT-X는 SWE-bench Verified에서 72%를 기록했다." in targets and "가격은" not in targets
    assert "글자 그대로" in p and "새 사실" in p and "원문이 어떤 형태로도 뒷받침하지 않을 때만" in p
    assert p.rstrip().endswith(SRC.text)


def test_revise_prompt_says_so_when_no_sentence_maps():
    prior = DraftCard("sid", "제목", PRIOR.summary, "w", (Claim("C9", "임원 교체가 발표됐다.", "entailment", "core"),))
    assert "요약은 그대로 두고 claim 만 다시 도출" in _build_revise_prompt(SRC, prior, ("C9",), today="2026-10-18")


def test_revise_prompt_takes_no_verdicts():
    """decorrelation — 피드백은 실패 claim id 뿐이다. 검증 AI 의 판정 이유·근거는 지시를 만들 때 받지도 않는다."""
    assert set(inspect.signature(_build_revise_prompt).parameters) == {"source", "prior", "failed_ids", "today"}
