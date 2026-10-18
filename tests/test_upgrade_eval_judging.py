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


def test_overrides_reapply_after_merge():
    finals = [{"arm": "A4", "source_id": "s1", "rep": 1, "covered": {"K1": True}, "first_sentence_new": True,
               "fidelity": {2: ["사실 오류"]}, "bypass": []}]
    ov = [{"arm": "A4", "source_id": "s1", "rep": 1, "field": "fidelity", "key": 5, "value": ["부풀림-범위"],
           "reason": "사람 확인 2 #10"},
          {"arm": "A4", "source_id": "s1", "rep": 1, "field": "covered", "key": "K1", "value": False, "reason": "x"},
          {"arm": "A4", "source_id": "s1", "rep": 9, "field": "first_sentence_new", "value": False, "reason": "없는 카드"}]
    out, applied = judging.apply_overrides(finals, ov)
    assert applied == 2                                                   # 대상 없는 1건은 세지 않는다(보고용)
    assert out[0]["fidelity"] == {"2": ["사실 오류"], "5": ["부풀림-범위"]}  # 다른 문장의 판정은 그대로
    assert out[0]["covered"] == {"K1": False}


# ── S1(2026-10-18): 맞비교 기준 조건을 고른다(기본 A0 — 기존 기록과 호환) ─────────────────────

def _recs(arm, sid="s1"):
    return [{"arm": arm, "source_id": sid, "rep": r, "decision": "PUBLISH", "summary": "요" * (10 + r)} for r in (1, 2, 3)]


def test_pairwise_tasks_use_chosen_base_and_arms():
    groups = {("S1A", "s1"): _recs("S1A"), ("S1C", "s1"): _recs("S1C"), ("A0", "s1"): _recs("A0"), ("A2", "s1"): _recs("A2")}
    tasks = judging.pairwise_tasks(groups, base="S1C", arms=["S1A"], judges=["astra"], done=set())
    assert sorted((t[0], t[3]) for t in tasks) == [("S1A", "arm_first"), ("S1A", "s1c_first")]


def test_pairwise_default_base_keeps_a0_labels():
    """기본(A0) 기준의 순서 이름은 예전 그대로('a0_first') — 기존 pairwise.jsonl 의 완료 키를 다시 돌리지 않게."""
    groups = {("A2", "s1"): _recs("A2"), ("A0", "s1"): _recs("A0")}
    tasks = judging.pairwise_tasks(groups, base="A0", arms=None, judges=["astra"], done={("A2", "s1", "astra", "arm_first")})
    assert [(t[0], t[3]) for t in tasks] == [("A2", "a0_first")]


def test_pairwise_winner_labels_base_by_name():
    """승자 칸 = 'arm' / 기준 조건 이름 / 'tie'. (S1 실행에서 지역 변수가 인자를 가려 기준 요약 본문이 들어갔던 버그)"""
    assert judging.pairwise_winner("first", "arm_first", "S1C") == "arm"
    assert judging.pairwise_winner("second", "arm_first", "S1C") == "S1C"
    assert judging.pairwise_winner("first", "s1c_first", "S1C") == "S1C"
    assert judging.pairwise_winner("tie", "arm_first", "S1C") == "tie"
    assert judging.pairwise_winner(None, "arm_first", "A0") is None


def test_pairwise_summary_counts_candidate_wins_by_arm_label():
    """후보 조건의 승리는 'arm' 으로 기록된다 — 조건 이름으로 세면 후보 승리가 0 으로 빠진다(2026-10-18 S2 집계 실수).
    기사 단위 다수결은 판정 4번(판정자 2 × 순서 2)을 기사별로 모아 정한다."""
    rows = ([{"arm": "S2B", "source_id": "a", "winner": "arm"}] * 4
            + [{"arm": "S2B", "source_id": "b", "winner": "S1C"}] * 3 + [{"arm": "S2B", "source_id": "b", "winner": "tie"}]
            + [{"arm": "S2B", "source_id": "c", "winner": "arm"}] * 2 + [{"arm": "S2B", "source_id": "c", "winner": "S1C"}] * 2
            + [{"arm": "S1A", "source_id": "a", "winner": "S1C"}] * 4                  # 다른 후보 조건 — 섞이면 안 된다
            + [{"arm": "S2B", "source_id": "d", "winner": None}])                     # 판정 실패 — 빼고 센다
    s = judging.pairwise_summary(rows, "S2B")
    assert s["judgments"] == {"arm": 6, "S1C": 5, "tie": 1}
    assert s["articles"] == {"arm": 1, "base": 1, "tie": 1}
