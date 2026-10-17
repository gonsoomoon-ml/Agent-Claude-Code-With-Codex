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


def test_infra_errors_are_retried_not_done(tmp_path):
    import json
    p = tmp_path / "raw.jsonl"
    rows = [{"k": "a", "error": "호출 실패: Read timeout on endpoint URL"},
            {"k": "b", "error": "스키마 위반: 없는 라벨: ['x']"},
            {"k": "c", "error": None}]
    p.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    assert judging.done_ok(p, ("k",)) == {("b",), ("c",)}           # 호출 실패만 다시 돈다 — 스키마 위반은 판정자 실패


def test_gate_omission_check_uses_short_fact_id():
    from upgrade_eval import judge as J
    it = J.PlantedSummary("p1-4-omit", "s1", "요약.", "뒤쪽 사실 삭제", 4, "가" * 100)
    fact = judging.gate_fact(it)
    assert fact.id == "F1" and fact.text == it.removed_fact         # 긴 문장을 JSON 키로 되받아 적게 하지 않는다
    assert judging.gate_uncovered({"covered": {"F1": False}, "first_sentence_new": True}, it) == {it.removed_fact}
    assert judging.gate_uncovered({"covered": {"F1": True}, "first_sentence_new": True}, it) == set()
    assert judging.gate_uncovered(None, it) == set()


def test_bedrock_client_waits_for_slow_judges():
    from upgrade_eval import judge as J
    assert J._bedrock().meta.config.read_timeout >= 180              # 기본 60초는 Kimi 응답(≈60–100초)을 끊는다


def test_tiebreak_targets_only_disputed_without_tie_results():
    sel = {"main": "m", "cross": "c", "tiebreak": "t"}
    same = {"align": {"covered": {"K1": True}, "first_sentence_new": True}, "fidelity": {}}
    diff = {"align": {"covered": {"K1": False}, "first_sentence_new": True}, "fidelity": {}}
    grouped = {("A0", "s1", 1): {"m": same, "c": same},            # 같음 → 가림 불필요
               ("A0", "s2", 1): {"m": same, "c": diff},            # 갈림 → 가림
               ("A0", "s3", 1): {"m": same, "c": diff},            # 갈렸지만 가림 결과가 이미 있음
               ("A0", "s4", 1): {"m": same}}                       # 교차 판정 없음 → 판정 누락(가림 안 함)
    done = {("A0", "s3", 1, "t", "align"), ("A0", "s3", 1, "t", "fidelity")}
    assert judging.tiebreak_targets(grouped, sel, done) == [("A0", "s2", 1)]
