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


def _run(survivors, cited, *, sent_index=None, past=(), judge=None, memo=None, **kw):
    by_sid = {fs.source_id: fs for fs in past}
    return drop_rereports(survivors, cited=cited, sent_index=sent_index or {},
                          get_source=lambda sid: by_sid[sid], judge=judge or _judge(),
                          memo={} if memo is None else memo, **kw)


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


def test_drop_rereports_mutual_date_only_vs_timestamp_same_day_keeps_both():
    """날짜만 있는 발행일(html 소스)은 그날 몇 시인지 모른다 — 같은 날 시각 있는 글과는 순서를 정하지 않는다(§4.2 ③).
    자정으로 보면 원문(시각 있음)이 늘 늦은 쪽이 돼 원문이 빠진다(최종 리뷰 2026-10-28)."""
    kr = _fs("K", "https://discuss.pytorch.kr/t/k/1", media="PyTorch Korea", fetched="2026-10-22")
    hf = _fs("H", "https://huggingface.co/blog/h", media="Hugging Face Blog", fetched="2026-10-22T05:00:00+00:00")
    j = _judge()
    out = _run([(kr, "Community"), (hf, "Engineering Blogs")],
               {"K": ("huggingface.co/blog/h",), "H": ("discuss.pytorch.kr/t/k/1",)}, judge=j)
    assert out == {} and j.calls == []


# ── 같은 사이트 다른 페이지(2026-11-14) — 재보도가 원문 기사 대신 제품 페이지·기술 보고서를 링크한 경우 ──
# recent_hosts = {호스트: 최근 7일 안에 보낸 기사 source_id}. 통과한 글(B)이 News & Media·Community 매체일 때만 본다.
_PRODUCT_PAGE = "claude.com/solutions/manufacturing"   # 원문(_A1 = claude.com/a)과 같은 사이트의 다른 페이지


def test_drop_rereports_same_site_past_pair():
    b = _fs("B", "https://the-decoder.com/b")
    out = _run([(b, "News & Media")], {"B": (_PRODUCT_PAGE,)}, recent_hosts={"claude.com": ["A1"]}, past=[_A1])
    assert out == {"B": (_A1, RereportVerdict(True, "r"))}


def test_drop_rereports_same_site_is_off_without_recent_hosts():
    a = _fs("A", "https://deepmind.google/blog/carbon", media="Google DeepMind")
    b = _fs("B", "https://the-decoder.com/b")
    j = _judge()
    out = _run([(a, "Google"), (b, "News & Media")], {"B": ("deepmind.google/fairwind-program",)}, judge=j)
    assert out == {} and j.calls == []


def test_drop_rereports_same_site_same_day_pair():
    a = _fs("A", "https://deepmind.google/blog/carbon", media="Google DeepMind")
    b = _fs("B", "https://the-decoder.com/b")
    out = _run([(a, "Google"), (b, "News & Media")], {"B": ("deepmind.google/fairwind-program",)}, recent_hosts={})
    assert set(out) == {"B"} and out["B"][0] is a


def test_drop_rereports_same_site_community_b():
    kr = _fs("K", "https://discuss.pytorch.kr/t/k/1", media="PyTorch Korea")
    out = _run([(kr, "Community")], {"K": (_PRODUCT_PAGE,)}, recent_hosts={"claude.com": ["A1"]}, past=[_A1])
    assert set(out) == {"K"}


def test_drop_rereports_same_site_never_asks_about_first_party_b():
    """1차 매체 글은 넓힌 경로로 판정자에게 가지 않는다 — 실측 256쌍 중 같은 발표 0, 원 발표 글이 빠질 길만 생긴다."""
    j = _judge()
    for media, cat in [("Google DeepMind", "Google"), ("Anthropic News", "Anthropic"), ("AWS ML Blog", "Amazon (AWS)"),
                       ("Hugging Face Blog", "Engineering Blogs"), ("Simon Willison", "Independent Voices")]:
        b = _fs("B", "https://example.org/b", media=media)
        assert _run([(b, cat)], {"B": (_PRODUCT_PAGE,)}, recent_hosts={"claude.com": ["A1"]}, past=[_A1], judge=j) == {}
    assert j.calls == []


def test_drop_rereports_same_site_stops_at_first_same():
    a3 = _fs("A3", "https://claude.com/c", media="Claude Blog")
    b = _fs("B", "https://the-decoder.com/b")
    j = _judge()
    out = _run([(b, "News & Media")], {"B": (_PRODUCT_PAGE,)}, recent_hosts={"claude.com": ["A1", "A3"]},
               past=[_A1, a3], judge=j)
    assert out["B"][0] is _A1 and len(j.calls) == 1


def test_drop_rereports_same_site_tries_next_candidate_when_different():
    a3 = _fs("A3", "https://claude.com/c", media="Claude Blog")
    b = _fs("B", "https://the-decoder.com/b")

    def j(a_text, _b_text):
        return RereportVerdict(a_text == "text-A3", "r")
    out = _run([(b, "News & Media")], {"B": (_PRODUCT_PAGE,)}, recent_hosts={"claude.com": ["A1", "A3"]},
               past=[_A1, a3], judge=j)
    assert set(out) == {"B"} and out["B"][0] is a3


def test_drop_rereports_same_site_exact_link_adds_no_site_candidates():
    """정확히 걸린 링크는 그 쌍만 판정한다 — 그 링크의 사이트로 다른 기사까지 후보를 넓히지 않는다(실측한 규칙 그대로)."""
    a3 = _fs("A3", "https://claude.com/c", media="Claude Blog")
    b = _fs("B", "https://the-decoder.com/b")
    j = _judge(False, "x")
    out = _run([(b, "News & Media")], {"B": ("claude.com/a",)}, sent_index={"claude.com/a": "A1"},
               recent_hosts={"claude.com": ["A1", "A3"]}, past=[_A1, a3], judge=j)
    assert out == {} and j.calls == [("text-A1", "text-B")]


def test_drop_rereports_same_site_leaves_exactly_cited_pair_to_exact_rules():
    """서로 인용해 일부러 판정하지 않은 쌍을, 같은 사이트의 다른 링크를 핑계로 다시 묶지 않는다(정할 수 없으면 둘 다 유지)."""
    x = _fs("X", "https://the-decoder.com/x", fetched="")
    y = _fs("Y", "https://pytorch.kr/y", media="PyTorch Korea", fetched="")
    j = _judge()
    out = _run([(x, "News & Media"), (y, "Community")],
               {"X": ("pytorch.kr/other-page", "pytorch.kr/y"), "Y": ("the-decoder.com/x",)}, judge=j, recent_hosts={})
    assert out == {} and j.calls == []


def test_drop_rereports_mutual_unknown_time_keeps_both_with_same_site_on():
    x = _fs("X", "https://the-decoder.com/x", fetched="")
    y = _fs("Y", "https://pytorch.kr/y", media="PyTorch Korea", fetched="")
    j = _judge()
    out = _run([(x, "News & Media"), (y, "Community")], {"X": ("pytorch.kr/y",), "Y": ("the-decoder.com/x",)},
               judge=j, recent_hosts={})
    assert out == {} and j.calls == []


def test_drop_rereports_same_site_skips_same_media():
    older = _fs("P", "https://pytorch.kr/older", media="PyTorch Korea")
    kr = _fs("K", "https://discuss.pytorch.kr/t/k/1", media="PyTorch Korea")
    j = _judge()
    out = _run([(kr, "Community")], {"K": ("pytorch.kr/some-page",)}, recent_hosts={"pytorch.kr": ["P"]},
               past=[older], judge=j)
    assert out == {} and j.calls == []


def test_drop_rereports_same_site_dropped_a_is_not_used():
    a = _fs("A", "https://the-decoder.com/a")                      # (a) 과거 원문 A1 의 재보도 → 빠진다
    c = _fs("C", "https://discuss.pytorch.kr/t/c/1", media="PyTorch Korea")   # 오늘 A 와 같은 사이트의 다른 페이지를 링크
    j = _judge()
    out = _run([(a, "News & Media"), (c, "Community")], {"A": ("claude.com/a",), "C": ("the-decoder.com/tag/x",)},
               sent_index={"claude.com/a": "A1"}, recent_hosts={"claude.com": ["A1"]}, past=[_A1], judge=j)
    assert set(out) == {"A"} and len(j.calls) == 1


def test_drop_rereports_same_site_skips_candidate_without_source():
    b = _fs("B", "https://the-decoder.com/b")
    out = _run([(b, "News & Media")], {"B": (_PRODUCT_PAGE,)}, recent_hosts={"claude.com": ["GONE", "A1"]}, past=[_A1])
    assert set(out) == {"B"} and out["B"][0] is _A1


def test_same_site_categories_are_catalog_categories():
    """분야 이름이 카탈로그에서 바뀌면 같은 사이트 판정이 조용히 꺼진다 — 이름이 어긋나면 여기서 잡는다."""
    from briefing.core.rereport_dedup import SAME_SITE_B_CATEGORIES
    from briefing.core.retrieval.sources import CATALOG
    assert SAME_SITE_B_CATEGORIES <= {s.category for s in CATALOG}
