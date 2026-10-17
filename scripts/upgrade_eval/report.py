"""비교 리포트 생성 — 결정·성적표·Stage B·비용 실측을 한 문서로(설계 §10).

표와 사실 줄은 코드가 만들고, 결론·사례 모음·한계의 문장은 설계자가 채운다(`<!-- 설계자가 채운다 -->`).
확인되지 않은 가격에는 '미확인', 기준선과 '차이 없음'인 비교에는 그렇게 적는다. 값이 없으면 '–'(nan 을 찍지 않는다).

실행: PYTHONPATH=scripts uv run python -m upgrade_eval.report [--out PATH]
"""
from __future__ import annotations

import argparse
import datetime
import json
import math
import sys
from pathlib import Path

from .common import EXP_ROOT, read_jsonl
from .costs import project

RESULTS = EXP_ROOT / "results"
DEFAULT_OUT = Path("/home/ubuntu/Agent-Claude-Code-With-Codex/docs/work_note/Oct-2026/261016-upgrade-claude-codex/"
                   "upgrade-comparison-report.md")
FILL = "<!-- 설계자가 채운다 -->"


def _missing(x) -> bool:
    return x is None or (isinstance(x, float) and math.isnan(x))


def _pct(x) -> str:
    return "–" if _missing(x) else f"{x * 100:.1f}%"


def _num(x, d: int = 2) -> str:
    return "–" if _missing(x) else f"{x:.{d}f}"


def _usd(x, verified: bool = True, d: int = 4) -> str:
    return "–" if _missing(x) else f"${x:.{d}f}" + ("" if verified else " (미확인)")


def _secs(ms) -> str:
    return "–" if _missing(ms) else f"{ms / 1000:.0f}초"


def _diff(comp: list | None, *, as_pct: bool) -> str:
    """[평균, 하한, 상한, 차이없음, 짝 수] → '+9.0%p [+4.0%p, +14.0%p]' (+ ' · 차이 없음')."""
    if not comp or _missing(comp[0]):
        return "비교 불가(짝 없음)"
    mean, lo, hi, same = comp[:4]

    def f(v: float) -> str:
        return f"{v * 100:+.1f}%p" if as_pct else f"{v:+.3f}"

    return f"{f(mean)} [{f(lo)}, {f(hi)}]" + (" · 차이 없음" if same else "")


_QUALITY_ROWS = [
    ("발행 실패율", "failure_rate", _pct), ("발행 실패율(F2 제외 — 결정용)", "failure_rate_f2_adjusted", _pct),
    ("검증 우회(문장당 항목)", "bypass_rate", lambda x: _num(x, 3)), ("검증 우회 — 코드 검사분", "code_bypass_rate", lambda x: _num(x, 3)),
    ("인용 불일치(카드 비율)", "quote_mismatch_rate", _pct),
    ("충실도 결함(라벨 문장 비율)", "fidelity", _pct), ("부풀림", "inflation_rate", _pct), ("지나친 흐림", "oversoftening_rate", _pct),
    ("귀속 누락", "attribution_rate", _pct), ("의견→사실", "opinion_rate", _pct),
    ("커버리지(핵심 사실)", "coverage", _pct), ("커버리지 — 문장당 사실", "coverage_per_sentence", _num),
    ("첫 문장이 새 사실", "first_sentence_new_rate", _pct), ("AI 관련 사실 커버리지", "ai_coverage", _pct),
    ("문장 수", "sentences_mean", lambda x: _num(x, 1)), ("150자 초과 문장", "long_sentence_ratio", _pct),
    ("유보 표현 보존", "hedge_rate", _pct), ("최심 위치(보조)", "depth_mean", _num), ("이름 음역", "translit_rate", _pct),
    ("claim 수", "claims_mean", lambda x: _num(x, 1)), ("첫 문장 제목 반복", "title_repeat_rate", _pct),
    ("'왜 중요한가'의 새 수치", "why_new_numbers_rate", _pct), ("1차 통과", "first_pass_rate", _pct),
]


def _quality(decision: dict, cards: dict, meta: dict) -> list[str]:
    arms, base = list(cards), decision.get("baseline", "A0")
    elim, ranking = decision.get("eliminated", {}), decision.get("ranking", [])
    out = ["## 요약 품질", "", "### 조건", "", "| 조건 | 모델 | CLI | effort |", "|---|---|---|---|"]
    for a in arms:
        arm = meta.get("arms", {}).get(a, {})
        out.append(f"| {a} | {arm.get('model_id', '–')} | {arm.get('cli_version', '–')} | {arm.get('effort') or '기본'} |")
    out += ["", f"### {base} 대비 — 기사 짝 비교 평균 차이와 95% 구간", "",
            "| 조건 | 검증 우회(/문장) | 인용 불일치 | 충실도 결함 | 커버리지 | 결과 |", "|---|---|---|---|---|---|"]
    for a in arms:
        if a == base:
            continue
        c = decision.get("comparisons", {}).get(a, {})
        result = ("탈락 — " + "; ".join(elim[a])) if a in elim else (f"{ranking.index(a) + 1}위" if a in ranking else "–")
        out.append(f"| {a} | {_diff(c.get('bypass_rate'), as_pct=False)} | {_diff(c.get('quote_mismatch_rate'), as_pct=True)} | "
                   f"{_diff(c.get('fidelity'), as_pct=True)} | {_diff(c.get('coverage'), as_pct=True)} | {result} |")
    out += ["", "### 성적표 — 실행 평균(품질은 발행된 실행만)", "", "| 지표 | " + " | ".join(arms) + " |",
            "|---|" + "---|" * len(arms)]
    for label, key, fmt in _QUALITY_ROWS:
        out.append(f"| {label} | " + " | ".join(fmt(cards[a].get(key)) for a in arms) + " |")
    for t in ("앞", "중", "뒤"):
        out.append(f"| 커버리지 — 원문 {t} | " + " | ".join(_pct(cards[a].get("coverage_by_tercile", {}).get(t)) for a in arms) + " |")
    cats = sorted({k for a in arms for k in cards[a].get("coverage_by_category", {})})
    for cat in cats:
        out.append(f"| 커버리지 — {cat} | " + " | ".join(_pct(cards[a].get("coverage_by_category", {}).get(cat)) for a in arms) + " |")
    out.append("| 실행 / 발행 / 판정 누락 | " + " | ".join(
        f"{cards[a].get('n_runs', 0)} / {cards[a].get('n_published', 0)} / {cards[a].get('n_published', 0) - cards[a].get('n_judged', 0)}"
        for a in arms) + " |")
    return out + [""]


def _stage_b(stage_b: dict) -> list[str]:
    out = ["## 검증 AI (Stage B)", "",
           f"- 승자(승인된 §6 규칙 그대로): **{stage_b.get('winner') or '선택 불가'}**",
           f"- 승자(건강 필터 — 오류율 5% 초과·오탐 GPT-5.5+10%p 초과 제외, 사용자 승인 필요): **{stage_b.get('winner_healthy') or '선택 불가'}**",
           "", "| 모델 | 검출률 | 오탐률 | 2회 일치(n) | 오류율 | claim 당 비용 | p50 | p95(n) |", "|---|---|---|---|---|---|---|---|"]
    for m, s in sorted(stage_b.get("scores", {}).items(), key=lambda kv: -(kv[1].get("catch_rate") or 0)):
        out.append(f"| {m} | {_pct(s.get('catch_rate'))} | {_pct(s.get('fp_rate'))} | {_pct(s.get('consistency'))} ({s.get('n_pairs', '–')}) | "
                   f"{_pct(s.get('error_rate'))} | {_usd(s.get('cost_per_claim'), s.get('cost_verified', False))} | "
                   f"{_secs(s.get('p50_ms'))} | {_secs(s.get('p95_ms'))} ({s.get('n_seq', '–')}) |")
    if stage_b.get("warnings"):
        out += ["", "기록 점검:"] + [f"- {w}" for w in stage_b["warnings"]]
    return out + [""]


def _costs(cards: dict, stage_b: dict, costs: dict, meta: dict) -> list[str]:
    use1 = costs.get("by_region_model", {}).get("USE1", {})
    period = costs.get("period", ["?", "?"])
    eq = costs.get("gpt55_list_price_equivalent", {})
    sonnet = use1.get("anthropic.claude-sonnet-5")
    out = ["## 비용 전후", "", f"### 전 — 실제 청구({period[0]}–{period[1]}, us-east-1)", "",
           f"- 요약 AI(Claude Sonnet 5): {_usd(sonnet, d=2)} — 하루 약 {_usd(None if _missing(sonnet) else sonnet / 30, d=2)}",
           f"- 검증 AI(GPT-5.5): 청구 {_usd(use1.get('openai.gpt-5.5'), d=2)}, 목록가 환산 "
           f"{_usd(eq.get('usd'), eq.get('price_verified', False), d=2)}({eq.get('price_source', '출처 없음')})"]
    out += [f"- {n}" for n in costs.get("notes", [])]
    per_day = meta.get("cards_per_day", 19.0)
    out += ["", f"### 후 — 조건별 추정(카드당 비용 × 하루 {per_day:.0f}장, 사실층은 사용자끼리 공유)", "",
            "| 조건 | 카드당 | 하루 | 월(30일) |", "|---|---|---|---|"]
    for a, c in cards.items():
        ok = bool(c.get("cost_verified"))
        cpc = c.get("cost_per_card")
        p = {"day": None, "month": None} if _missing(cpc) else project(cpc, per_day)
        out.append(f"| {a} | {_usd(c.get('cost_per_card'), ok)} | {_usd(p['day'], ok, 2)} | {_usd(p['month'], ok, 2)} |")
    proj = stage_b.get("stage_a_certifier_cost_projection", {})
    if proj:
        out += ["", "Stage B 승자 기준 Stage A 검증 비용 추정: " + ", ".join(f"{k} ${v:.0f}" for k, v in proj.items())]
    prices = meta.get("prices", {})
    if prices:
        out += ["", "가격 확인 상태: 확인 — " + (", ".join(m for m, v in prices.items() if v) or "없음")
                + " / 미확인 — " + (", ".join(m for m, v in prices.items() if not v) or "없음")]
    return out + [""]


def _latency(cards: dict) -> list[str]:
    out = ["## 처리 시간", "", "순차 실행만(동시 실행은 지연을 부풀린다). 운영 상한은 카드당 360초.", "",
           "| 조건 | p50 | p95 | 순차 n |", "|---|---|---|---|"]
    for a, c in cards.items():
        out.append(f"| {a} | {_secs(c.get('latency_p50'))} | {_secs(c.get('latency_p95'))} | {c.get('n_sequential', '–')} |")
    return out + [""]


def render_report(decision: dict, cards: dict, stage_b: dict, costs: dict, meta: dict) -> str:
    j = meta.get("judges", {})
    elim = decision.get("eliminated", {})
    lines = ["# Claude Code·Codex 업그레이드 비교 리포트", "",
             f"> {meta.get('date', '')} · 기사 {meta.get('n_articles', '–')}건 × 반복 {meta.get('reps', '–')}회 · 요약 조건 {len(cards)}개 · "
             f"Stage A 검증 AI {meta.get('stage_a_verifier', '–')} · 판정자 주 {j.get('main', '–')} · 교차 {j.get('cross', '–')} · "
             f"가림 {j.get('tiebreak', '–')}", "",
             "## 결론", "", FILL, "",
             f"- 순위(코드 규칙): {' > '.join(decision.get('ranking', [])) or '–'}",
             "- 탈락: " + ("; ".join(f"{a} — {', '.join(r)}" for a, r in elim.items()) or "없음"),
             f"- 검증 AI: 승인 규칙 그대로 {stage_b.get('winner') or '–'} / 건강 필터 {stage_b.get('winner_healthy') or '–'}", ""]
    lines += _quality(decision, cards, meta) + _stage_b(stage_b) + _costs(cards, stage_b, costs, meta) + _latency(cards)
    lines += ["## 한계", "", FILL, "",
              f"- 표본: 기사 {meta.get('n_articles', '–')}건 × 반복 {meta.get('reps', '–')}회 — 구간이 넓어 작은 차이는 '차이 없음'으로 나온다.",
              f"- 판정자: 주 {j.get('main', '–')}, 교차 {j.get('cross', '–')}, 갈리면 {j.get('tiebreak', '–')} — 요약 AI(Claude)와 다른 계열.",
              "- 가격: '미확인' 표시는 Bedrock 가격 목록에 없어 2차 출처 단가를 쓴 값이다.", "",
              "## 사례 모음", "", FILL + " (점수 없이 사례만 — 설계자는 후보와 같은 계열이라 채점하지 않는다)", "",
              "## 다음 단계", "",
              "- U8: 배포할 요약·검증 조합 선택(사용자 결정).",
              "- §14-4: 다른 작업과의 배포 순서 결정 → F3·F7·F5·U8 계획.",
              "- F1·F2·F4 수정, 요약 지시 검토(S1–S5), 운영 정기 측정(M1·M2).", "",
              "## 부록", "", "### 쌍대 비교(순위 근거)", "", "| 쌍 | 이긴 쪽 | 갈린 단계 |", "|---|---|---|"]
    for pair, v in decision.get("pairwise", {}).items():
        lines.append(f"| {pair} | {v.get('winner') or '동률'} | {v.get('by', '–')} |")
    lines += ["", "결정 규칙: 안전(검증 우회·인용 불일치·발행 실패율 +5%p)이나 충실도가 기준선보다 나빠지면 탈락 → "
              "남은 조건을 쌍마다 충실도 → 커버리지 → 비용 → p95 순으로 겨룬다. '차이 없음' = 95% 구간이 0 을 포함하거나 "
              "평균 차이가 같은 조건 반복 사이 표준편차보다 작음.", ""]
    return "\n".join(lines)


def _load(name: str) -> dict:
    return json.loads((RESULTS / name).read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> None:
    from .author_runner import ARMS
    from .costs import load_prices
    from .select_articles import load_manifest

    ap = argparse.ArgumentParser(prog="report")
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    args = ap.parse_args(argv)
    need = ["decision.json", "scorecards.json", "stage_b_scores.json", "costs.json", "judges.json"]
    missing = [n for n in need if not (RESULTS / n).exists()]
    if missing:
        print("리포트 입력이 아직 없다: " + ", ".join(missing), file=sys.stderr)
        sys.exit(1)
    score = _load("scorecards.json")
    runs = read_jsonl(EXP_ROOT / "runs" / "stage_a" / "records.jsonl")
    prices = load_prices()
    meta = {"date": datetime.date.today().isoformat(), "n_articles": len(load_manifest()),
            "reps": max((r.get("rep", 0) for r in runs), default=0),
            "arms": {k: {"model_id": a.model_id, "cli_version": a.cli_version, "effort": a.effort} for k, a in ARMS.items()},
            "stage_a_verifier": score.get("verifier"), "judges": _load("judges.json"), "cards_per_day": 19.0,
            "prices": {m: p.verified for m, p in prices.items()}}
    md = render_report(_load("decision.json"), score["cards"], _load("stage_b_scores.json"), _load("costs.json"), meta)
    Path(args.out).write_text(md, encoding="utf-8")
    print(args.out)


if __name__ == "__main__":
    main()
