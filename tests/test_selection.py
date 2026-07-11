"""selection — 캡 초과 시 top-K 선별: 주=LLM pick-K(invoke seam), 폴백=최신순 잘림(latest_k=현행 동작)."""
from briefing.core.retrieval.selection import latest_k, llm_select
from briefing.core.retrieval.sources import FetchedArticle


def _arts(n):
    return [FetchedArticle("s", f"https://x/{i}", f"제목{i}", f"본문{i}", f"2026-07-1{i}T0{i}:00:00Z")
            for i in range(1, n + 1)]


def test_latest_k_is_current_truncation():
    arts = _arts(5)
    assert latest_k(arts, 3) == arts[:3]   # 피드 최신순 첫 K = 기존 캡과 동일(폴백의 결정론)


def test_llm_select_picks_by_returned_indices():
    arts = _arts(5)
    picked = llm_select(arts, 3, invoke=lambda system, user: "[2, 5, 1]")
    assert picked == [arts[1], arts[4], arts[0]]   # 1-기반 인덱스 → 해당 기사, 응답 순서 유지


def test_llm_select_passthrough_when_under_k():
    arts = _arts(2)
    called = {"n": 0}

    def boom(_s, _u):
        called["n"] += 1
        raise AssertionError("len<=k 면 판정 호출 금지(비용 0)")

    assert llm_select(arts, 3, invoke=boom) == arts and called["n"] == 0


def test_llm_select_falls_back_on_bad_json(capsys):
    arts = _arts(4)
    assert llm_select(arts, 2, invoke=lambda s, u: "글쎄요...") == arts[:2]   # 폴백=latest
    assert "WARN" in capsys.readouterr().err                                  # non-silent


def test_llm_select_filters_out_of_range_and_falls_back_when_short(capsys):
    arts = _arts(4)
    # 범위 밖(9)·중복(1,1) 걸러내면 유효 1개 < k=2 → 폴백+warn
    assert llm_select(arts, 2, invoke=lambda s, u: "[9, 1, 1]") == arts[:2]
    assert "WARN" in capsys.readouterr().err


def test_llm_select_takes_first_k_when_over_returned():
    arts = _arts(5)
    picked = llm_select(arts, 2, invoke=lambda s, u: "[3, 1, 4]")   # 유효 3개 ≥ k → 앞의 k
    assert picked == [arts[2], arts[0]]


def test_llm_select_falls_back_on_invoke_error(capsys):
    arts = _arts(4)

    def boom(_s, _u):
        raise RuntimeError("throttled")

    assert llm_select(arts, 2, invoke=boom) == arts[:2]
    assert "WARN" in capsys.readouterr().err


def test_llm_select_prompt_contains_numbered_titles_and_k():
    arts = _arts(4)
    seen = {}

    def capture(system, user):
        seen["system"], seen["user"] = system, user
        return "[1, 2]"

    llm_select(arts, 2, invoke=capture)
    assert "1. 제목1" in seen["user"] and "4. 제목4" in seen["user"]   # 번호 목록
    assert "본문1" in seen["user"]                                     # 리드 포함
    assert "2" in seen["system"] and "JSON" in seen["system"]          # k·형식 지시가 system 에
