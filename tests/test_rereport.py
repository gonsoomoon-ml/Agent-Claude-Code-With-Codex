"""rereport — 재보도 판정자("B 는 주로 A 와 같은 발표인가")의 파싱·fail-open·입력 상한(2026-10-28)."""
from briefing.core.retrieval.rereport import MAX_JUDGE_CHARS, llm_rereport


def test_llm_rereport_parses_same():
    v = llm_rereport("A", "B", invoke=lambda s, u: 'ok {"same": true, "reason": "same launch"}')
    assert v.same is True and v.reason == "same launch"


def test_llm_rereport_returns_none_on_bad_json():
    assert llm_rereport("A", "B", invoke=lambda s, u: "no json").same is None


def test_llm_rereport_returns_none_on_exception():
    def boom(s, u):
        raise RuntimeError("throttled")
    v = llm_rereport("A", "B", invoke=boom)
    assert v.same is None and "RuntimeError" in v.reason


def test_llm_rereport_truncates_inputs():
    seen = {}
    llm_rereport("a" * 9000, "b" * 9000,
                 invoke=lambda s, u: seen.setdefault("u", u) and '{"same": false, "reason": "x"}')
    assert seen["u"].count("a") == MAX_JUDGE_CHARS and seen["u"].count("b") == MAX_JUDGE_CHARS
