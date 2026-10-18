"""S2 측정 — claim 이 요약의 귀속·양태·수치 한정어를 담는지(코드 지표)와 검증 결과 분포. 판정 AI 없이 기록만 읽는다."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from upgrade_eval import s2_metrics as m  # noqa: E402

SUMMARY = "OpenAI는 GPT-X가 SWE-bench Verified에서 최대 72%를 기록했다고 밝혔다."


# ── 귀속 ─────────────────────────────────────────────────────────────────────

def test_attr_marker_covers_present_and_connective_forms():
    """S1C 표본 점검에서 놓친 꼴('말하며'·'본다')까지 — 이름 붙이기('이라고 불리는')는 귀속이 아니다."""
    for s in ("글쓴이는 뒤집힐 수 있다고 본다.", "Runway는 시간을 잃는다고 말하며 줄이려 한다.", "OpenAI는 점수가 72%라고 밝혔다.",
              "보고서에 따르면 비용이 늘었다.", "발레스니는 확률을 10% 이상으로 추정했다.",
              "Azhar는 CEO들로부터 예산이 늘고 있다고 들었다.", "Meta는 이 모델을 코딩 최적화 모델로 설명한다."):
        assert m.ATTR.search(s), s
    assert not m.ATTR.search("GWM-1이라고 불리는 모델을 공개했다.")


def test_attributed_clause_starts_at_nearest_clause_boundary():
    s = "에이전트 분야는 벤치마크가 17개로 가장 많으며, 글쓴이는 원인을 평가 비용으로 보인다고 추정했다."
    assert m.attributed_clauses(s) == ["글쓴이는 원인을 평가 비용으로 보인다고 추정했"]


def test_attribution_judged_on_best_matching_claim():
    """귀속 절과 낱말이 가장 많이 겹치는 claim 이 귀속 표지를 가져야 보존 — 겹치는 claim 이 없으면 분모 밖(따로 센다)."""
    kept = ["OpenAI는 GPT-X의 SWE-bench Verified 점수가 최대 72%라고 밝혔다.", "GPT-X는 오늘 공개됐다."]
    dropped = ["GPT-X는 SWE-bench Verified에서 최대 72%를 기록했다.", "OpenAI는 GPT-X를 공개했다."]
    assert m.attribution(SUMMARY, kept) == (1, 1, 0)
    assert m.attribution(SUMMARY, dropped) == (0, 1, 0)
    assert m.attribution(SUMMARY, ["Anthropic은 새 요금제를 내놓았다."]) == (0, 0, 1)


# ── 양태 · 수치 한정어 ────────────────────────────────────────────────────────


def test_modality_preserved_by_same_word():
    s = "구글은 올해 안으로 기능을 통합할 계획이며, 일부 기능은 프리뷰로 먼저 공개한다."
    assert m.modality(s, ["구글은 올해 안으로 기능을 통합할 계획이다.", "일부 기능은 프리뷰로 먼저 공개된다."]) == (2, 2)
    assert m.modality(s, ["구글은 기능을 통합한다.", "일부 기능을 공개한다."]) == (0, 2)


def test_qualifier_pairs_preserved_with_same_number():
    s = "점수는 최대 72%였고 비용은 30% 이상 줄었다."
    assert m.qualifiers(s, ["점수는 최대 72%였다.", "비용은 30% 줄었다."]) == (1, 2)
    assert m.qualifiers(s, ["점수는 최대 72%였다.", "비용은 30% 이상 줄었다."]) == (2, 2)
    assert m.qualifiers("점수는 72%였다.", ["점수는 72%였다."]) == (0, 0)


# ── claim 표지 · 검증 결과 · 카드 지표 ─────────────────────────────────────────

def test_marker_group():
    assert m.marker_group("OpenAI는 점수가 72%라고 밝혔다.") == "표지"
    assert m.marker_group("출시는 다음 달 예정이다.") == "표지"
    assert m.marker_group("비용은 30% 이상 줄었다.") == "표지"
    assert m.marker_group("GPT-X는 72%를 기록했다.") == "단정"


def _rec(arm="S2B", sid="s1", rep=1, summary=SUMMARY, claims=(), verdicts=(), decision="PUBLISH", attempts=1):
    return {"arm": arm, "source_id": sid, "rep": rep, "decision": decision, "attempts": attempts, "summary": summary,
            "claims": [{"id": f"C{i}", "text": t, "claim_type": ct, "importance": "core"}
                       for i, (t, ct) in enumerate(claims, 1)],
            "verdicts": [{"claim_id": f"C{i}", "verdict": v, "evidence": "", "model": ""} for i, v in enumerate(verdicts, 1)],
            "error": None}


def test_card_metrics_counts_verdicts_by_type_and_group():
    rec = _rec(claims=(("OpenAI는 점수가 최대 72%라고 밝혔다.", "arithmetic"), ("GPT-X는 공개됐다.", "entailment")),
               verdicts=("VERIFIED", "DEMOTED"), attempts=2)
    c = m.card_metrics(rec)
    assert c["claims"] == 2 and c["revised"] is True
    assert c["attribution"] == (1, 1, 0) and c["qualifiers"] == (1, 1)
    assert c["verdicts"] == {("arithmetic", "표지", "VERIFIED"): 1, ("entailment", "단정", "DEMOTED"): 1}


def test_summarize_arm_pools_counts_and_claims_range():
    recs = [_rec(claims=(("OpenAI는 점수가 최대 72%라고 밝혔다.", "arithmetic"),) * 12, verdicts=("VERIFIED",) * 12),
            _rec(sid="s2", claims=(("GPT-X는 72%를 기록했다.", "arithmetic"),) * 25, verdicts=("BLOCKED",) * 25,
                 decision="QUARANTINE")]
    s = m.summarize_arm([m.card_metrics(r) for r in recs])
    assert (s["cards"], s["quarantine"], s["claims_mean"], s["claims_out_of_range"]) == (2, 1, 18.5, 1)
    assert (s["attribution_kept"], s["attribution_total"]) == (1, 2)
    assert s["blocked"] == 25 and s["claims_total"] == 37


def test_paired_article_diffs_pool_reps_per_article():
    """기사별로 회차를 합쳐 비율을 낸 뒤 실험군 − 대조군 — 한쪽에 분모가 없는 기사는 뺀다."""
    base = {"a": [(1, 2), (1, 2)], "b": [(0, 0)]}
    arm = {"a": [(2, 2), (1, 2)], "b": [(1, 1)]}
    assert m.paired_diffs(base, arm) == {"a": 0.25}
