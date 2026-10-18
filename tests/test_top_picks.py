"""top_picks — 오늘의 핵심 3: 발행 카드 전체에서 K장(재료=사실층 제목·요약), 실패면 칸 생략(최신순 대체 없음)."""
from briefing.core.authoring.author import Claim, DraftCard
from briefing.core.gate import GatedCard
from briefing.core.top_picks import TOP_K, TOP_MIN_CARDS, llm_top_picks, top_source_ids
from briefing.core.verification.certifier import CertVerdict


def _g(sid, decision="PUBLISH"):
    card = DraftCard(sid, f"제목-{sid}", f"요약-{sid}", f"해석-{sid}", (Claim("C1", "x", "entailment", "core"),))
    return GatedCard(card, (CertVerdict("C1", "VERIFIED", "ev"),), decision, 1)


def _cards(n):
    return [_g(f"s{i}") for i in range(1, n + 1)]


def test_llm_top_picks_uses_fact_layer_only_and_returns_chosen_cards():
    seen = {}

    def capture(system, user):
        seen["system"], seen["user"] = system, user
        return "[3, 1, 6]"

    cards = _cards(6)
    assert llm_top_picks(cards, 3, invoke=capture) == [cards[2], cards[0], cards[5]]
    assert "1. 제목-s1" in seen["user"] and "요약-s1" in seen["user"]   # 사실층(제목·요약)
    assert "해석-s1" not in seen["user"]                                # 해석층은 lens 별 → 넣으면 사용자 간 공유가 깨짐
    assert "(1) AI agents" in seen["system"]                           # 소스 선별과 같은 기준(P2b)


def test_llm_top_picks_returns_empty_on_failure_not_latest(capsys):
    cards = _cards(6)
    assert llm_top_picks(cards, 3, invoke=lambda s, u: "글쎄요") == []   # 앞 3장 대체 금지
    assert "WARN" in capsys.readouterr().err

    def boom(_s, _u):
        raise RuntimeError("throttled")

    assert llm_top_picks(cards, 3, invoke=boom) == []


def test_top_source_ids_threshold_memo_and_quarantine_excluded():
    calls = []

    def fn(cards, k):
        calls.append([g.card.source_id for g in cards])
        return list(cards)[:k]

    memo: dict = {}
    assert top_source_ids(_cards(TOP_MIN_CARDS - 1), fn, memo) == () and calls == []   # 문턱 미만 → 호출 없음
    cards = _cards(TOP_MIN_CARDS) + [_g("q", decision="QUARANTINE")]
    assert top_source_ids(cards, fn, memo) == ("s1", "s2", "s3")[:TOP_K]
    assert top_source_ids(cards, fn, memo) == ("s1", "s2", "s3")[:TOP_K] and len(calls) == 1   # 같은 묶음 = memo
    assert "q" not in calls[0]                                                                  # 발행 카드만 후보
    assert top_source_ids(cards, None, {}) == ()                                                # 미주입 = 칸 없음
