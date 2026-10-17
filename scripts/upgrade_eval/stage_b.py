"""Stage B — 검증 AI 비교(설계 §6).

같은 claim 세트(운영 카드의 함의 claim + 일부러 틀리게 바꾼 '심은 오류')를 검증 AI 후보 5종에 두 번씩 돌려
심은 오류 검출률·오탐률·일관성·비용·처리 시간을 잰다. 숫자 claim 은 운영에서도 Python 이 검사하므로(모델 무관) 뺀다.
오탐은 BLOCKED 만이 아니라 'VERIFIED 가 아닌 것' 전부 — 모두 DEMOTED 로 판정하는 모델이 이기지 못하게(§6).

실행: PYTHONPATH=scripts uv run python -m upgrade_eval.stage_b <build-claims|validate|run|latency|score>
"""
from __future__ import annotations

import argparse
import json
import math
import random
import statistics
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass

from briefing.core.authoring.author import Claim
from briefing.core.gate import _build_envelope
from briefing.core.stores.source_store import SourceStore
from briefing.core.verification.certifier import _NUM_RE

from . import costs
from .codex_runner import VERIFIERS, certify_entailment_json
from .common import EXP_ROOT, SEED, append_jsonl, done_keys, read_jsonl
from .select_articles import load_manifest

PLANTED_TYPES = ("주체 바꾸기", "유보→단정", "단계 격상", "귀속 삭제", "의미 반전", "사실 추가")
_PLANTED_RANGE = (6, 8)
STAGE_B_DIR = EXP_ROOT / "stage_b"
RECORDS = EXP_ROOT / "runs" / "stage_b" / "records.jsonl"
RESULTS = EXP_ROOT / "results"


@dataclass(frozen=True)
class ClaimItem:
    key: str
    source_id: str
    text: str
    origin: str                      # "original" | "planted"
    planted_type: str | None = None
    base_key: str | None = None


@dataclass
class ModelScore:
    catch_rate: float
    catch_blocked_rate: float
    fp_rate: float
    fp_blocked: float
    fp_demoted: float
    consistency: float
    cost_per_claim: float
    cost_verified: bool
    p50_ms: float
    p95_ms: float
    timeouts: int
    n_true: int
    n_uncertain: int


def original_claims(cards: list[dict], source_ids: set[str]) -> list[ClaimItem]:
    """운영 사실층 카드에서 함의 claim 만(숫자가 든 claim 은 운영 재라우팅 규칙대로 Python 경로라 제외)."""
    out, seen = [], set()
    for d in cards:
        card = d["card"]
        sid = card["source_id"]
        if sid not in source_ids or card.get("based_on") or sid in seen:
            continue
        seen.add(sid)
        for c in card["claims"]:
            if not _NUM_RE.search(c["text"]):
                out.append(ClaimItem(f"{sid[:12]}:{c['id']}", sid, c["text"], "original"))
    return out


def validate_planted(planted: list[ClaimItem], originals: list[ClaimItem]) -> list[str]:
    errors = []
    base = {c.key: c for c in originals}
    lo, hi = _PLANTED_RANGE
    for t in PLANTED_TYPES:
        n = sum(p.planted_type == t for p in planted)
        if not lo <= n <= hi:
            errors.append(f"{t}: {n}개(허용 {lo}–{hi})")
    for p in planted:
        if p.origin != "planted" or p.planted_type not in PLANTED_TYPES:
            errors.append(f"{p.key}: 유형·origin 이상({p.origin}, {p.planted_type})")
        if p.base_key not in base:
            errors.append(f"{p.key}: base_key 없음({p.base_key})")
        elif base[p.base_key].text == p.text:
            errors.append(f"{p.key}: 원본과 문장이 같음")
        if _NUM_RE.search(p.text):
            errors.append(f"{p.key}: 숫자 포함(숫자 claim 은 Python 경로라 Stage B 대상 아님)")
    return errors


def _rate(values: list[bool]) -> float:
    return sum(values) / len(values) if values else 0.0


def _p(values: list[float], q: float) -> float:
    if not values:
        return math.inf
    return statistics.quantiles(values, n=100, method="inclusive")[q - 1] if len(values) > 1 else values[0]


def score_stage_b(records: list[dict], claims: list[ClaimItem], prices: dict[str, costs.Price]) -> dict[str, ModelScore]:
    by_key = {c.key: c for c in claims}
    models = sorted({r["model"] for r in records})
    passes = [r for r in records if r["pass"] in (1, 2) and r["claim_key"] in by_key]
    need = math.ceil(0.8 * len(models))   # 5개 모델이면 4개 이상 VERIFIED → '맞는 claim'
    first = [r for r in passes if r["pass"] == 1]
    true_keys = {k for k, c in by_key.items() if c.origin == "original"
                 and sum(r["verdict"] == "VERIFIED" for r in first if r["claim_key"] == k) >= need}
    n_orig = sum(c.origin == "original" for c in claims)
    scores = {}
    for m in models:
        mine = [r for r in passes if r["model"] == m]
        planted = [r for r in mine if by_key[r["claim_key"]].origin == "planted"]
        true = [r for r in mine if r["claim_key"] in true_keys]
        v1 = {r["claim_key"]: r["verdict"] for r in mine if r["pass"] == 1}
        v2 = {r["claim_key"]: r["verdict"] for r in mine if r["pass"] == 2}
        both = set(v1) & set(v2)
        price = prices.get(m)
        cost_list = [costs.codex_cost(r.get("usage") or {}, price) for r in mine] if price else []
        seq = [float(r["duration_ms"]) for r in records if r["model"] == m and r["pass"] == "seq" and not r.get("error")]
        scores[m] = ModelScore(
            catch_rate=_rate([r["verdict"] != "VERIFIED" for r in planted]),
            catch_blocked_rate=_rate([r["verdict"] == "BLOCKED" for r in planted]),
            fp_rate=_rate([r["verdict"] != "VERIFIED" for r in true]),
            fp_blocked=_rate([r["verdict"] == "BLOCKED" for r in true]),
            fp_demoted=_rate([r["verdict"] == "DEMOTED" for r in true]),
            consistency=_rate([v1[k] == v2[k] for k in both]) if both else 0.0,
            cost_per_claim=statistics.fmean(cost_list) if cost_list else math.nan,
            cost_verified=bool(price and price.verified),
            p50_ms=_p(seq, 50), p95_ms=_p(seq, 95),
            timeouts=sum(r.get("error") == "timeout" for r in records if r["model"] == m),
            n_true=len(true_keys), n_uncertain=n_orig - len(true_keys),
        )
    return scores


def pick_winner(scores: dict[str, ModelScore], *, baseline: str = "gpt-5.5") -> str:
    eps = 1e-9
    top = max(s.catch_rate for s in scores.values())
    floor = scores[baseline].catch_rate if baseline in scores else 0.0
    cands = {m: s for m, s in scores.items() if s.catch_rate >= top - 0.05 - eps and s.catch_rate >= floor - eps}
    best_fp = min(s.fp_rate for s in cands.values())
    finalists = {m: s for m, s in cands.items() if s.fp_rate <= best_fp + 0.02 + eps}
    return min(finalists, key=lambda m: (finalists[m].cost_per_claim, finalists[m].p95_ms))


# ── CLI ──
def _scan_fact_cards() -> list[dict]:
    import boto3

    from briefing.core.config import load_settings

    table = boto3.resource("dynamodb", region_name="us-east-1").Table(load_settings().cache_table)
    items, start = [], None
    while True:                                                    # 읽기 전용: scan 만
        kw = {"ProjectionExpression": "card_json"}
        if start:
            kw["ExclusiveStartKey"] = start
        resp = table.scan(**kw)
        items += resp["Items"]
        start = resp.get("LastEvaluatedKey")
        if not start:
            return [json.loads(it["card_json"]) for it in items]


def _load_claims() -> tuple[list[ClaimItem], list[ClaimItem]]:
    originals = [ClaimItem(**r) for r in read_jsonl(STAGE_B_DIR / "originals.jsonl")]
    planted = [ClaimItem(**r) for r in read_jsonl(STAGE_B_DIR / "planted.jsonl")]
    return originals, planted


def _certify(model: str, item: ClaimItem, store: SourceStore, pass_: object) -> dict:
    envelope = _build_envelope(store.get_source(item.source_id), Claim(item.key, item.text, "entailment"))
    verdict, run = certify_entailment_json(item.key, envelope, VERIFIERS[model])
    return {"model": model, "pass": pass_, "claim_key": item.key, "verdict": verdict.verdict, "evidence": verdict.evidence,
            "usage": run.usage, "duration_ms": run.duration_ms, "returncode": run.returncode, "error": run.error}


def cmd_run(passes: int, concurrency: int) -> None:
    originals, planted = _load_claims()
    store = SourceStore(str(EXP_ROOT / "sources"))
    done = done_keys(RECORDS, ("model", "pass", "claim_key"))
    tasks = [(m, p, c) for m in VERIFIERS for p in range(1, passes + 1) for c in originals + planted
             if (m, p, c.key) not in done]
    random.Random(SEED).shuffle(tasks)
    lock = threading.Lock()
    print(f"stage_b run: {len(tasks)} calls (skipped {len(done)})", flush=True)

    def work(t):
        rec = _certify(t[0], t[2], store, t[1])
        with lock:
            append_jsonl(RECORDS, rec)

    with ThreadPoolExecutor(max_workers=min(concurrency, 4)) as pool:
        list(pool.map(work, tasks))


def cmd_latency(n: int) -> None:
    originals, _ = _load_claims()
    store = SourceStore(str(EXP_ROOT / "sources"))
    sample = sorted(random.Random(SEED).sample(originals, min(n, len(originals))), key=lambda c: c.key)
    done = done_keys(RECORDS, ("model", "pass", "claim_key"))
    for m in VERIFIERS:                                            # 순차 — 동시 실행은 처리 시간을 왜곡한다
        for c in sample:
            if (m, "seq", c.key) not in done:
                append_jsonl(RECORDS, _certify(m, c, store, "seq"))


def cmd_score() -> None:
    originals, planted = _load_claims()
    scores = score_stage_b(read_jsonl(RECORDS), originals + planted, costs.load_prices())
    winner = pick_winner(scores)
    per_card = len(originals) / max(len(load_manifest()), 1)
    w = scores[winner]
    projected = w.cost_per_claim * 216 * per_card * 1.3
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "stage_b_scores.json").write_text(json.dumps(
        {"winner": winner, "scores": {m: asdict(s) for m, s in scores.items()},
         "stage_a_certifier_cost_projection": projected, "entailment_claims_per_card": per_card},
        ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    lines = ["# Stage B 결과 — 검증 AI 비교", "",
             f"- 원본 claim {len(originals)}개(맞는 claim {w.n_true}, 불확실 {w.n_uncertain}), 심은 오류 {len(planted)}개, 모델당 2회",
             f"- **승자: {winner}** (규칙: 검출률 최고−5%p 이상·GPT-5.5 이상 → 오탐 최저+2%p 이내 → 비용·p95)", "",
             "| 모델 | 검출률 | BLOCKED 로 검출 | 오탐률 | 오탐 BLOCKED | 오탐 DEMOTED | 2회 일치 | claim 당 비용 | p50 | p95 | 시간 초과 |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    for m, s in sorted(scores.items(), key=lambda kv: -kv[1].catch_rate):
        warn = " ⚠" if s.consistency < 0.90 else ""
        price = f"${s.cost_per_claim:.4f}" + ("" if s.cost_verified else " (미확인)")
        lines.append(f"| {m} | {s.catch_rate:.1%} | {s.catch_blocked_rate:.1%} | {s.fp_rate:.1%} | {s.fp_blocked:.1%} | "
                     f"{s.fp_demoted:.1%} | {s.consistency:.1%}{warn} | {price} | {s.p50_ms / 1000:.1f}s | {s.p95_ms / 1000:.1f}s | {s.timeouts} |")
    lines += ["", "## 다음 단계 비용 추정(재승인 요청)",
              f"- Stage A 검증 비용: 약 ${projected:.0f} = 승자 claim 당 ${w.cost_per_claim:.4f} × 216회 × 카드당 함의 claim {per_card:.1f}개 × 1.3(다시 쓰기)"
              + ("" if w.cost_verified else " — 가격 미확인"),
              "- Stage A 요약 비용: 약 $30–40(추정)", "- 판정 비용: 약 $80–110(추정, 전체 채점)",
              "- ⚠ 표시는 2회 판정 일치율 90% 미만."]
    (RESULTS / "stage_b_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="stage_b")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("build-claims")
    sub.add_parser("validate")
    r = sub.add_parser("run")
    r.add_argument("--passes", type=int, default=2)
    r.add_argument("--concurrency", type=int, default=4)
    lat = sub.add_parser("latency")
    lat.add_argument("--n", type=int, default=30)
    sub.add_parser("score")
    args = ap.parse_args(argv)
    if args.cmd == "build-claims":
        ids = {a["source_id"] for a in load_manifest()}
        claims = original_claims(_scan_fact_cards(), ids)
        STAGE_B_DIR.mkdir(parents=True, exist_ok=True)
        (STAGE_B_DIR / "originals.jsonl").write_text(
            "".join(json.dumps(asdict(c), ensure_ascii=False) + "\n" for c in claims), encoding="utf-8")
        print(f"originals: {len(claims)} claims from {len({c.source_id for c in claims})} sources")
    elif args.cmd == "validate":
        originals, planted = _load_claims()
        errors = validate_planted(planted, originals)
        print("\n".join(errors) if errors else f"ok: planted {len(planted)}")
        sys.exit(1 if errors else 0)
    elif args.cmd == "run":
        cmd_run(args.passes, args.concurrency)
    elif args.cmd == "latency":
        cmd_latency(args.n)
    elif args.cmd == "score":
        cmd_score()


if __name__ == "__main__":
    main()
