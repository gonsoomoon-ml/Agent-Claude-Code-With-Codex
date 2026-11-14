"""rereport — 재보도 판정자("B 는 주로 A 와 같은 발표인가")의 파싱·fail-open·입력 상한(2026-10-28)."""
from briefing.core.retrieval.rereport import MAX_JUDGE_CHARS, REREPORT_SYSTEM, llm_rereport


def test_llm_rereport_parses_same():
    v = llm_rereport("A", "B", invoke=lambda s, u: 'ok {"same": true, "reason": "same launch"}')
    assert v.same is True and v.reason == "same launch"


def test_rereport_prompt_asks_reason_before_same():
    """답 형식은 이유 먼저·값 나중 — 값을 먼저 쓰게 하면 판정자가 따져 보기 전에 값을 써서 이유와 어긋난다.

    2026-11-14 실측(정답 붙인 47쌍·Haiku 5.5): same 먼저 = 이미 보낸 원문의 한국어 소개 2쌍을 0/10,
    reason 먼저 = 20/20 이고 나머지 45쌍은 225/225 그대로(사고 블록은 호출의 ~30% 에서만 나온다).
    """
    fmt = REREPORT_SYSTEM.rsplit("Answer only JSON:", 1)[1]
    assert fmt.index('"reason"') < fmt.index('"same"')


def test_llm_rereport_parses_reason_first():
    v = llm_rereport("A", "B", invoke=lambda s, u: '{"reason": "Korean write-up of A", "same": true}')
    assert v.same is True and v.reason == "Korean write-up of A"


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
