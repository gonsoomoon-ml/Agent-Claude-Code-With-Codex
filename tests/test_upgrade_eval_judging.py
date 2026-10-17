"""업그레이드 비교 실험 — 채점 실행 테스트: 중간 길이 반복·판정 불일치·채점 대상·최종 판정 합치기."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from upgrade_eval import judging  # noqa: E402


def rec(rep=1, summary="요약이다.", decision="PUBLISH", arm="A2", source_id="s1"):
    return {"arm": arm, "source_id": source_id, "rep": rep, "summary": summary, "decision": decision}


def test_median_length_rep():
    recs = [rec(rep=1, summary="가" * 100), rec(rep=2, summary="가" * 300), rec(rep=3, summary="가" * 200)]
    assert judging.median_length_rep(recs)["rep"] == 3
    two = [rec(rep=2, summary="가" * 300), rec(rep=1, summary="가" * 100)]
    assert judging.median_length_rep(two)["rep"] == 1              # 짝수면 짧은 쪽(아래 중간)


def test_disagreements():
    assert judging.fidelity_disagreements({0: ["귀속 누락"], 1: []}, {0: [], 1: []}) == [0]
    assert judging.align_disagreements({"K1": True, "K2": False}, {"K1": True, "K2": True}) == ["K2"]


def test_only_published_runs_are_scored():
    recs = [rec(decision="PUBLISH"), rec(decision="QUARANTINE"), rec(decision="ERROR")]
    assert [r["decision"] for r in judging.scoring_targets(recs)] == ["PUBLISH"]


def test_merge_final_uses_tiebreak_only_where_judges_disagree():
    main = {"covered": {"K1": True, "K2": False}, "first_sentence_new": True, "fidelity": {0: ["귀속 누락"]}, "bypass": ["x"]}
    cross = {"covered": {"K1": True, "K2": True}, "first_sentence_new": True, "fidelity": {}, "bypass": []}
    tie = {"covered": {"K1": False, "K2": True}, "first_sentence_new": False, "fidelity": {0: []}}
    final = judging.merge_final(main, cross, tie)
    assert final["covered"] == {"K1": True, "K2": True}              # K1 은 둘이 같아 그대로, K2 만 가림
    assert final["first_sentence_new"] is True and final["fidelity"] == {} and final["bypass"] == ["x"]
    assert judging.merge_final(main, main, None)["fidelity"] == {0: ["귀속 누락"]}
