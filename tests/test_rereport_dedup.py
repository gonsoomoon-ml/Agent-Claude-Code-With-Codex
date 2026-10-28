"""rereport_dedup — 재보도 제외 순수 로직(2026-10-28): 인용 쌍 찾기·서로 인용·메모·fail-open.

판정자는 fake(호출 기록). A 는 언제나 유지되고, 빠지는 것은 인용한 쪽(B)뿐이다.
"""
from briefing.core.rereport_dedup import drop_rereports
from briefing.core.retrieval.rereport import RereportVerdict
from briefing.core.stores.source_store import FrozenSource


def _fs(sid, url, *, media="The Decoder", fetched="2026-10-25"):
    return FrozenSource(sid, url, f"title-{sid}", f"text-{sid}", fetched, media)


def _judge(same=True, reason="r"):
    calls = []

    def j(a_text, b_text):
        calls.append((a_text, b_text))
        return RereportVerdict(same, reason)
    j.calls = calls
    return j


def _run(survivors, cited, *, sent_index=None, past=(), judge=None, memo=None):
    by_sid = {fs.source_id: fs for fs in past}
    return drop_rereports(survivors, cited=cited, sent_index=sent_index or {},
                          get_source=lambda sid: by_sid[sid], judge=judge or _judge(),
                          memo={} if memo is None else memo)


_A1 = _fs("A1", "https://claude.com/a", media="Claude Blog")


def test_drop_rereports_past_pair_same():
    b = _fs("B", "https://the-decoder.com/b")
    out = _run([(b, "News & Media")], {"B": ("claude.com/a",)}, sent_index={"claude.com/a": "A1"}, past=[_A1])
    assert out == {"B": (_A1, RereportVerdict(True, "r"))}


def test_drop_rereports_past_pair_different_keeps_b():
    b = _fs("B", "https://the-decoder.com/b")
    out = _run([(b, "News & Media")], {"B": ("claude.com/a",)}, sent_index={"claude.com/a": "A1"}, past=[_A1],
               judge=_judge(False, "x"))
    assert out == {}


def test_drop_rereports_keeps_b_when_judge_fails():
    b = _fs("B", "https://the-decoder.com/b")
    out = _run([(b, "News & Media")], {"B": ("claude.com/a",)}, sent_index={"claude.com/a": "A1"}, past=[_A1],
               judge=_judge(None, "err"))
    assert out == {}


def test_drop_rereports_same_day_pair():
    a = _fs("A", "https://claude.com/a", media="Claude Blog")
    b = _fs("B", "https://the-decoder.com/b")
    out = _run([(a, "Anthropic"), (b, "News & Media")], {"B": ("claude.com/a",)})
    assert set(out) == {"B"} and out["B"][0] is a


def test_drop_rereports_mutual_prefers_big_tech():
    decoder = _fs("D", "https://the-decoder.com/x", media="The Decoder", fetched="2026-10-21")
    claude = _fs("C", "https://claude.com/y", media="Claude Blog", fetched="2026-10-22")
    cited = {"D": ("claude.com/y",), "C": ("the-decoder.com/x",)}
    out = _run([(decoder, "News & Media"), (claude, "Anthropic")], cited)
    assert set(out) == {"D"} and out["D"][0] is claude   # 더 이른 비빅테크가 아니라 빅테크 1차 글을 남긴다


def test_drop_rereports_mutual_both_big_earlier_wins():
    first = _fs("F", "https://claude.com/f", media="Claude Blog", fetched="2026-10-21")
    later = _fs("L", "https://anthropic.com/news/l", media="Anthropic News", fetched="2026-10-22")
    cited = {"F": ("anthropic.com/news/l",), "L": ("claude.com/f",)}
    out = _run([(later, "Anthropic"), (first, "Anthropic")], cited)
    assert set(out) == {"L"} and out["L"][0] is first


def test_drop_rereports_mutual_unknown_time_keeps_both():
    x = _fs("X", "https://the-decoder.com/x", fetched="")
    y = _fs("Y", "https://pytorch.kr/y", media="PyTorch Korea", fetched="")
    j = _judge()
    out = _run([(x, "News & Media"), (y, "Community")], {"X": ("pytorch.kr/y",), "Y": ("the-decoder.com/x",)}, judge=j)
    assert out == {} and j.calls == []


def test_drop_rereports_dropped_a_is_not_used():
    a = _fs("A", "https://the-decoder.com/a")             # (a) 과거 원문 A1 의 재보도 → 빠진다
    c = _fs("C", "https://pytorch.kr/c", media="PyTorch Korea")   # 오늘 A 를 인용 — 빠진 A 로는 판정하지 않는다
    j = _judge()
    out = _run([(a, "News & Media"), (c, "Community")], {"A": ("claude.com/a",), "C": ("the-decoder.com/a",)},
               sent_index={"claude.com/a": "A1"}, past=[_A1], judge=j)
    assert set(out) == {"A"} and len(j.calls) == 1


def test_drop_rereports_any_same_drops():
    a2 = _fs("A2", "https://openai.com/index/a2", media="OpenAI")
    b = _fs("B", "https://the-decoder.com/b")

    def j(a_text, _b_text):
        return RereportVerdict(a_text == "text-A2", "r")
    out = _run([(b, "News & Media")], {"B": ("claude.com/a", "openai.com/index/a2")},
               sent_index={"claude.com/a": "A1", "openai.com/index/a2": "A2"}, past=[_A1, a2], judge=j)
    assert set(out) == {"B"} and out["B"][0] is a2


def test_drop_rereports_memo_reused():
    b = _fs("B", "https://the-decoder.com/b")
    j, memo = _judge(), {}
    for _ in range(2):   # 두 사용자 — 같은 run 메모 공유
        _run([(b, "News & Media")], {"B": ("claude.com/a",)}, sent_index={"claude.com/a": "A1"}, past=[_A1],
             judge=j, memo=memo)
    assert len(j.calls) == 1
