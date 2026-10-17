"""업그레이드 비교 실험 — 기사 12건 층화 선정 테스트(할당·조건·결정론·부족분 보고)."""
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from upgrade_eval.select_articles import QUOTAS, CardRow, select_articles  # noqa: E402

_LENGTHS = [1500, 2500, 4000, 5000, 6000, 7000, 7950, 7990, 3500, 4500]


def make_rows(kind: str | None = None, n: int = 10) -> list[CardRow]:
    """층마다 n건 — 길이 1,500–7,990(그중 2건은 잘린 원문), 숫자·유보·인용 속성은 번갈아."""
    strata = [("뉴스", "ko"), ("뉴스", "en"), ("기업 발표", "en"), ("기술·연구", "en"), ("커뮤니티", "ko")]
    rows = []
    for k, lang in strata:
        if kind and k != kind:
            continue
        for i in range(n):
            length = _LENGTHS[i % len(_LENGTHS)]
            rows.append(CardRow(
                source_id=f"{k}-{lang}-{i:02d}", url=f"https://example.com/{k}/{lang}/{i}", title=f"{k} {i}",
                kind=k, lang=lang, length=length, truncated=length >= 7900,
                has_numbers=i % 2 == 0, has_hedge=i % 3 == 0, has_quote=i % 4 == 0,
            ))
    return rows


def test_quotas_constraints_and_determinism():
    rows = make_rows()
    m1, m2 = select_articles(rows, seed=1), select_articles(rows, seed=1)
    assert m1 == m2
    arts = m1["articles"]
    strata = Counter((a["kind"], a["lang"] if a["kind"] == "뉴스" else None) for a in arts)
    assert strata == Counter(QUOTAS)
    assert 3 <= sum(a["truncated"] for a in arts) <= 5 and any(a["length"] < 3000 for a in arts)
    assert sum(a["has_numbers"] for a in arts) >= 2 and sum(a["has_hedge"] for a in arts) >= 2
    assert any(a["has_quote"] for a in arts)
    assert sorted(a["kind"] for a in arts if a["human_check"]) == ["기술·연구", "기업 발표", "뉴스"]
    assert m1["shortfalls"] == []


def test_swaps_are_recorded_when_random_pick_misses_a_constraint():
    rows = [r for r in make_rows() if not r.truncated]                      # 잘린 원문이 하나도 없는 모집단에
    rows += [CardRow("tech-trunc", "u", "t", "기술·연구", "en", 7990, True, True, False, False),
             CardRow("biz-trunc", "u", "t", "기업 발표", "en", 7950, True, False, True, False),
             CardRow("news-trunc", "u", "t", "뉴스", "en", 7999, True, True, True, True)]   # 잘린 후보 3건만 추가
    arts = select_articles(rows, seed=1)["articles"]
    swapped = [a for a in arts if a["reason"].startswith("교체")]
    assert sum(a["truncated"] for a in arts) == 3 and swapped
    assert all("잘린 원문" in a["reason"] for a in swapped if a["truncated"])


def test_shortfall_is_reported():
    rows = [r for r in make_rows() if r.kind != "커뮤니티"] + make_rows(kind="커뮤니티", n=1)
    m = select_articles(rows, seed=1)
    assert any("커뮤니티" in s for s in m["shortfalls"]) and len(m["articles"]) == 11
