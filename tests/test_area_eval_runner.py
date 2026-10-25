"""area_eval.run_golden — 골든셋 평가 러너의 지표(정확 일치·boundary 분해·안정성·게이트)를 fake 라벨로 고정."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from area_eval import run_golden as rg  # noqa: E402


def _row(sid, area, run_date="2026-10-23", boundary=False, repeat=False):
    return {"run_date": run_date, "source_id": sid, "card_key": "k" + sid, "decision": "PUBLISH", "media": "AWS ML Blog",
            "category": "Amazon (AWS)", "headline": f"제목-{sid}", "summary": f"요약-{sid}", "area": area,
            "boundary": boundary, "alt_old_code": None, "genre": "가이드", "repeat_of_earlier_run": repeat}


def _golden():
    return {"areas_in_mail_order": list(rg.AREAS), "cards": [
        _row("a", "AI Agents"), _row("b", "Models & Releases", boundary=True), _row("c", None),   # c = 분류 불가 → 제외
        _row("a", "AI Agents", run_date="2026-10-22", repeat=True),                               # 반복 행 → 점수 제외
    ]}


def _fake(area_of):
    return lambda cards, secs: [{"n": i, "org": "", "type": "other", "importance": 3, "event": "e",
                                 "area": area_of(g.card.source_id)} for i, g in enumerate(cards)]


def test_run_golden_metrics_on_fake_labels():
    r = rg.evaluate(_golden(), _fake(lambda sid: "AI Agents" if sid in ("a", "c") else "Applied AI"), passes=2)
    assert r["scored"] == 2 and r["correct"] == 1 and r["accuracy"] == 0.5          # b(boundary) 만 틀림
    assert r["mismatch_boundary"] == 1 and r["mismatch_nonboundary"] == 0
    assert r["mismatch_boundary"] + r["mismatch_nonboundary"] == len(r["mismatches"])
    assert r["stability"] == 1.0 and r["gate_pass"] is False                        # 같은 fake 2회 = 100% 일치 · 50% < 85%


def test_run_golden_all_correct_passes_gate_and_reports_failed_batches():
    g = _golden()
    gold = {c["source_id"]: c["area"] for c in g["cards"]}
    r = rg.evaluate(g, _fake(lambda sid: gold[sid] or "AI Agents"), passes=1)
    assert r["accuracy"] == 1.0 and r["gate_pass"] is True and r["stability"] is None

    def boom(cards, secs):
        raise RuntimeError("throttled")

    r2 = rg.evaluate(g, boom, passes=1)
    assert r2["scored"] == 2 and r2["correct"] == 0 and len(r2["failures"]) == 2       # run_date 묶음 2개 다 실패
    assert "throttled" in r2["failures"][0]["reason"] and r2["gate_pass"] is False
