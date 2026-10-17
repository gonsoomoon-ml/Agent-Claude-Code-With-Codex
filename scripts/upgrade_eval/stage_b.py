"""Stage B — 검증 AI 비교(설계 §6).

같은 claim 세트(운영 카드의 함의 claim + 일부러 틀리게 바꾼 '심은 오류')를 검증 AI 후보 5종에 두 번씩 돌려
심은 오류 검출률·오탐률·일관성·비용·처리 시간을 잰다. 숫자 claim 은 운영에서도 Python 이 검사하므로(모델 무관) 뺀다.
오탐은 BLOCKED 만이 아니라 'VERIFIED 가 아닌 것' 전부 — 모두 DEMOTED 로 판정하는 모델이 이기지 못하게(§6).

사전 리뷰 반영(유료 실행 전):
- 기록마다 판정 출처(cert_model)·원문 답·codex 버전·effort·시도 번호를 남긴다 — 사후 감사.
- 비정상 종료·예외(인프라 오류)는 간격을 두고 재시도하고 '끝남'으로 치지 않는다. 시간 초과·파싱 실패는 모델 행동이라 그대로 센다.
- 예산 상한(목록가 환산)과 모델별 차단기. 1차를 모든 모델에 끝낸 뒤 2차 — 상한에 걸려도 1차 합의는 온전하다.
- 채점: 키마다 최신 기록, 1차 완전성 필수, 오류는 검출로 세지 않고 비용 평균에서 빼며 처리 시간에는 넣는다.

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
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field

from briefing.core.authoring.author import Claim
from briefing.core.gate import _build_envelope
from briefing.core.stores.source_store import SourceStore
from briefing.core.verification.certifier import _NUM_RE, CertVerdict

from . import costs
from .codex_runner import VERIFIERS, CodexRun, certify_entailment_json, run_codex_json
from .common import EXP_ROOT, SEED, append_jsonl, done_keys, read_jsonl
from .select_articles import load_manifest

PLANTED_TYPES = ("주체 바꾸기", "유보→단정", "단계 격상", "귀속 삭제", "의미 반전", "사실 추가")
_PLANTED_RANGE = (6, 8)
STAGE_B_DIR = EXP_ROOT / "stage_b"
RECORDS = EXP_ROOT / "runs" / "stage_b" / "records.jsonl"
RESULTS = EXP_ROOT / "results"
BUDGET_USD = 60.0          # 승인 예산 상한(설계 §6 '약 $50–60', GPT-5.5 기준선 포함) — 목록가 환산, 캐시 단가 모르면 입력 단가
BREAKER = 10               # 한 모델이 연속 10번 실제 판정을 못 내면 그 모델 호출을 멈춘다
BACKOFF_S = (15, 60)       # 인프라 오류 재시도 간격(초) — 첫 시도 + 재시도 2번
TIMEOUT_MS = 120_000       # codex 호출 상한 — 시간 초과는 처리 시간 p95 에 이 값 이상으로 들어간다


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
    error_rate: float = 0.0                              # 1·2차 기록 중 실제 판정이 아닌 것(시간 초과·파싱 실패)
    errors: dict = field(default_factory=dict)          # {"timeout": n, "parse": n} — 처리 시간 측정분 포함
    n_pairs: int = 0                                     # 2회 일치를 잰 claim 수
    n_seq: int = 0                                       # 처리 시간 측정 수


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


def is_infra_error(rec: dict) -> bool:
    """비정상 종료·예외 = 인프라 문제(스로틀·네트워크·권한). 모델의 판정이 아니므로 재시도하고 채점에서 뺀다."""
    return rec.get("error") not in (None, "timeout")


def is_real_verdict(rec: dict) -> bool:
    """검증기가 실제로 내린 판정인가 — 시간 초과·파싱 실패·인프라 오류의 fail-closed DEMOTED 가 아님."""
    return rec.get("cert_model", "") != "codex-error" and rec.get("error") is None


def _rate(values: list[bool]) -> float:
    return sum(values) / len(values) if values else math.nan


def _p(values: list[float], q: int) -> float:
    if not values:
        return math.nan
    return statistics.quantiles(values, n=100, method="inclusive")[q - 1] if len(values) > 1 else values[0]


def _latest(records: list[dict]) -> dict[tuple, dict]:
    """(모델, 회차, claim) 마다 인프라 오류가 아닌 마지막 기록 — 재실행·재시도가 표를 두 번 세지 않게."""
    out: dict[tuple, dict] = {}
    for r in records:
        if not is_infra_error(r):
            out[(r["model"], r["pass"], r["claim_key"])] = r
    return out


def shared_pass2(latest: dict[tuple, dict], keys, models: list[str]) -> set[str]:
    """모든 모델에 2차 기록이 있는 claim — 예산 상한으로 2차가 모델마다 다른 claim 에서 끊겨도 같은 세트로 비교하게."""
    return {k for k in keys if all((m, 2, k) in latest for m in models)}


def score_stage_b(records: list[dict], claims: list[ClaimItem], prices: dict[str, costs.Price], *,
                  models: list[str]) -> dict[str, ModelScore]:
    """models 는 실행한 검증기 목록을 명시 — 기록에 있는 모델로 정하면 빠진 모델이 기준(4/5)을 조용히 바꾼다.
    1차가 하나라도 비면 채점하지 않는다(맞는 claim 합의가 무너진다). 2차는 일부여도 된다(예산 상한) —
    검출·오탐·오류율·비용에는 1차 전부 + 모든 모델에 공통인 claim 의 2차만 쓰고, 2회 일치는 있는 짝으로 잰다."""
    by_key = {c.key: c for c in claims}
    latest = _latest([r for r in records if r["model"] in models and r["claim_key"] in by_key])
    missing = [(m, k) for m in models for k in by_key if (m, 1, k) not in latest]
    if missing:
        raise ValueError(f"1차 판정 누락 {len(missing)}건 — 예: {missing[:3]}")
    need = math.ceil(0.8 * len(models))   # 5개 모델이면 4개 이상 VERIFIED → '맞는 claim'
    true_keys = {k for k, c in by_key.items() if c.origin == "original"
                 and sum(latest[(m, 1, k)]["verdict"] == "VERIFIED" for m in models) >= need}
    n_orig = sum(c.origin == "original" for c in claims)
    common2 = shared_pass2(latest, by_key, models)
    scores = {}
    for m in models:
        both_passes = [r for (mm, p, _), r in latest.items() if mm == m and p in (1, 2)]
        mine = [r for r in both_passes if r["pass"] == 1 or r["claim_key"] in common2]
        seq = [r for (mm, p, _), r in latest.items() if mm == m and p == "seq"]
        planted = [r for r in mine if by_key[r["claim_key"]].origin == "planted"]
        true = [r for r in mine if r["claim_key"] in true_keys]
        v = {p: {r["claim_key"]: r["verdict"] for r in both_passes if r["pass"] == p and is_real_verdict(r)} for p in (1, 2)}
        both = set(v[1]) & set(v[2])
        price = prices.get(m)
        cost_list = [costs.codex_cost(r["usage"], price) for r in mine if r.get("usage")] if price else []
        durations = [max(float(r["duration_ms"]), TIMEOUT_MS) if r.get("error") == "timeout" else float(r["duration_ms"])
                     for r in seq]
        errs = [r for r in mine + seq if not is_real_verdict(r)]
        errors = {}
        for r in errs:
            kind = "timeout" if r.get("error") == "timeout" else "parse"
            errors[kind] = errors.get(kind, 0) + 1
        scores[m] = ModelScore(
            catch_rate=_rate([is_real_verdict(r) and r["verdict"] != "VERIFIED" for r in planted]),
            catch_blocked_rate=_rate([is_real_verdict(r) and r["verdict"] == "BLOCKED" for r in planted]),
            fp_rate=_rate([r["verdict"] != "VERIFIED" for r in true]),          # 오류도 운영에선 발행을 막는다 → 오탐
            fp_blocked=_rate([is_real_verdict(r) and r["verdict"] == "BLOCKED" for r in true]),
            fp_demoted=_rate([is_real_verdict(r) and r["verdict"] == "DEMOTED" for r in true]),
            consistency=_rate([v[1][k] == v[2][k] for k in both]),
            cost_per_claim=statistics.fmean(cost_list) if cost_list else math.nan,
            cost_verified=bool(price and price.verified),
            p50_ms=_p(durations, 50), p95_ms=_p(durations, 95),
            timeouts=errors.get("timeout", 0),
            n_true=len(true_keys), n_uncertain=n_orig - len(true_keys),
            error_rate=_rate([not is_real_verdict(r) for r in mine]),
            errors=errors, n_pairs=len(both), n_seq=len(seq),
        )
    return scores


def pick_winner(scores: dict[str, ModelScore], *, baseline: str = "gpt-5.5", healthy_only: bool = False) -> str:
    """§6 규칙: 검출률 최고−5%p 이상·기준선 이상 → 오탐 최저+2%p 이내 → claim 당 비용·p95.
    healthy_only(사전 리뷰 제안, 사용자 승인 대기): 오류율 > 5% 이거나 오탐 > 기준선+10%p 인 모델을 먼저 뺀다 —
    전부 DEMOTED 로 답하는 모델이 '최고 검출률'을 차지해 정상 모델을 모두 밀어내는 구멍을 막는다."""
    eps = 1e-9
    if baseline not in scores:
        raise ValueError(f"기준선 {baseline} 점수 없음")
    pool = dict(scores)
    if healthy_only:
        b = scores[baseline]
        if math.isnan(b.fp_rate) or b.error_rate > 0.05 + eps:
            raise ValueError(f"기준선 {baseline} 이 건강하지 않음(오류율 {b.error_rate:.0%}) — 승자를 고르지 않는다")
        pool = {m: s for m, s in scores.items() if s.error_rate <= 0.05 + eps and s.fp_rate <= b.fp_rate + 0.10 + eps}
    bad = [m for m, s in pool.items() if any(math.isnan(x) for x in (s.catch_rate, s.fp_rate, s.cost_per_claim, s.p95_ms))]
    if bad:
        raise ValueError(f"NaN 지표 {bad} — 승자를 고르지 않는다")
    top = max(s.catch_rate for s in pool.values())
    floor = scores[baseline].catch_rate
    cands = {m: s for m, s in pool.items() if s.catch_rate >= top - 0.05 - eps and s.catch_rate >= floor - eps}
    best_fp = min(s.fp_rate for s in cands.values())
    finalists = {m: s for m, s in cands.items() if s.fp_rate <= best_fp + 0.02 + eps}
    return min(finalists, key=lambda m: (finalists[m].cost_per_claim, finalists[m].p95_ms))


def audit_records(records: list[dict], claims: list[ClaimItem], models: list[str]) -> list[str]:
    """채점 전 기록 점검 — 조용히 버려지거나 두 번 세일 수 있는 것을 숫자로 드러낸다."""
    keys = {c.key for c in claims}
    out = []
    unknown = sum(r["claim_key"] not in keys for r in records)
    if unknown:
        out.append(f"claim 세트에 없는 키의 기록 {unknown}건(채점 제외)")
    extra = sorted({r["model"] for r in records} - set(models))
    if extra:
        out.append(f"채점 대상이 아닌 모델의 기록: {extra}")
    seen: dict[tuple, int] = {}
    for r in records:
        if not is_infra_error(r):
            k = (r["model"], r["pass"], r["claim_key"])
            seen[k] = seen.get(k, 0) + 1
    dup = sum(n > 1 for n in seen.values())
    if dup:
        out.append(f"같은 키에 기록이 둘 이상 {dup}건(최신 것만 채점)")
    for m in models:
        infra = sum(is_infra_error(r) for r in records if r["model"] == m)
        p2 = sum(1 for (mm, p, k) in seen if mm == m and p == 2 and k in keys)
        nseq = sum(1 for (mm, p, _) in seen if mm == m and p == "seq")
        if infra or p2 < len(keys) or not nseq:
            out.append(f"{m}: 인프라 오류 시도 {infra}회 · 2차 {p2}/{len(keys)} · 처리 시간 측정 {nseq}건")
    return out


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


def _store() -> SourceStore:
    return SourceStore(str(EXP_ROOT / "sources"))


def _certify(model: str, item: ClaimItem, store, pass_: object, *, attempt: int = 1, runner=run_codex_json) -> dict:
    m = VERIFIERS[model]
    envelope = _build_envelope(store.get_source(item.source_id), Claim(item.key, item.text, "entailment"))
    try:
        verdict, run = certify_entailment_json(item.key, envelope, m, timeout_s=TIMEOUT_MS // 1000, runner=runner)
    except Exception as exc:                       # 예상 못 한 실행 예외도 인프라 오류로 남긴다 — 긴 실행 전체가 멈추지 않게
        run = CodexRun(None, {}, 0, None, f"exception: {type(exc).__name__}: {exc}"[:300])
        verdict = CertVerdict(item.key, "DEMOTED", f"검증기 실행 예외(보수적 미확인): {run.error}", "codex-error")
    return {"model": model, "pass": pass_, "claim_key": item.key, "verdict": verdict.verdict, "evidence": verdict.evidence,
            "cert_model": verdict.model, "final_text": (run.final_text or "")[:2000], "codex_version": m.codex_version,
            "effort": m.effort, "attempt": attempt, "usage": run.usage, "duration_ms": run.duration_ms,
            "returncode": run.returncode, "error": run.error}


def run_task(model: str, item: ClaimItem, store, pass_: object, *, runner=run_codex_json, sleep=time.sleep) -> list[dict]:
    """claim 1건 검증 — 인프라 오류면 간격을 두고 최대 2번 더. 모든 시도를 attempt 번호와 함께 남긴다."""
    recs = []
    for attempt in range(1, len(BACKOFF_S) + 2):
        rec = _certify(model, item, store, pass_, attempt=attempt, runner=runner)
        recs.append(rec)
        if not is_infra_error(rec) or attempt > len(BACKOFF_S):
            break
        sleep(BACKOFF_S[attempt - 1])
    return recs


class _Spend:
    """실행 중 누적 비용(이전 실행분 포함 — 재개해도 상한은 하나)과 모델별 연속 실패를 센다."""

    def __init__(self, budget: float, prices: dict[str, costs.Price], previous: list[dict]):
        self.budget, self.prices, self.lock = budget, prices, threading.Lock()
        self.spent, self.n, self.by_model = 0.0, 0, {}
        for r in previous:
            self._cost(r)

    def _cost(self, rec: dict) -> dict:
        st = self.by_model.setdefault(rec["model"], {"usd": 0.0, "in": 0, "cached": 0, "streak": 0})
        usage = rec.get("usage") or {}
        if usage:
            price = self.prices.get(rec["model"]) or costs.FALLBACK_PRICES[rec["model"]]
            usd = costs.codex_cost(usage, price)
            st["usd"] += usd
            self.spent += usd
            st["in"] += usage.get("input_tokens", 0) or 0
            st["cached"] += usage.get("cached_input_tokens", 0) or 0
        return st

    def add(self, recs: list[dict]) -> int:
        with self.lock:
            for r in recs:
                st = self._cost(r)
                st["streak"] = 0 if is_real_verdict(r) else st["streak"] + 1
            self.n += 1
            return self.n

    def blocked(self, model: str) -> str | None:
        with self.lock:
            if self.spent >= self.budget:
                return f"예산 상한 ${self.budget:.0f} 도달(누적 ${self.spent:.2f})"
            if self.by_model.get(model, {}).get("streak", 0) >= BREAKER:
                return f"{model}: 연속 {BREAKER}회 이상 실제 판정 없음 — 이 모델 호출 중단"
        return None

    def line(self) -> str:
        with self.lock:
            parts = [f"{m} ${st['usd']:.2f}(캐시 {st['cached'] / st['in']:.0%})" if st["in"] else f"{m} $0"
                     for m, st in sorted(self.by_model.items())]
            return f"  … {self.n}건 · 누적 ${self.spent:.2f}/{self.budget:.0f} · " + ", ".join(parts)


def cmd_run(passes: int, concurrency: int, *, budget: float = BUDGET_USD, runner=run_codex_json, sleep=time.sleep,
            prices: dict | None = None, models: list[str] | None = None) -> bool:
    """1차를 모든 모델에 끝낸 뒤 2차. 반환: 상한·차단기 없이 끝났나(False 면 사용자에게 보고)."""
    originals, planted = _load_claims()
    store = _store()
    models = models or list(VERIFIERS)
    spend = _Spend(budget, costs.load_prices() if prices is None else prices, read_jsonl(RECORDS))
    lock = threading.Lock()
    for p in range(1, passes + 1):
        done = done_keys(RECORDS, ("model", "pass", "claim_key"), where=lambda r: not is_infra_error(r))
        tasks = [(m, c) for m in models for c in originals + planted if (m, p, c.key) not in done]
        random.Random(SEED + p).shuffle(tasks)
        print(f"stage_b run pass {p}: {len(tasks)} calls", flush=True)

        def work(t, p=p):
            if spend.blocked(t[0]):
                return
            recs = run_task(t[0], t[1], store, p, runner=runner, sleep=sleep)
            with lock:
                for r in recs:
                    append_jsonl(RECORDS, r)
            if spend.add(recs) % 20 == 0:
                print(spend.line(), flush=True)

        with ThreadPoolExecutor(max_workers=min(concurrency, 4)) as pool:
            list(pool.map(work, tasks))
        print(spend.line(), flush=True)
        reasons = sorted({spend.blocked(m) for m in models} - {None})
        if reasons:
            print("중단: " + " / ".join(reasons), flush=True)
            return False
    return True


def cmd_latency(n: int, *, budget: float = BUDGET_USD, runner=run_codex_json, sleep=time.sleep,
                prices: dict | None = None, models: list[str] | None = None) -> bool:
    originals, _ = _load_claims()
    store = _store()
    models = models or list(VERIFIERS)
    spend = _Spend(budget, costs.load_prices() if prices is None else prices, read_jsonl(RECORDS))
    sample = sorted(random.Random(SEED).sample(originals, min(n, len(originals))), key=lambda c: c.key)
    done = done_keys(RECORDS, ("model", "pass", "claim_key"), where=lambda r: not is_infra_error(r))
    for m in models:                                               # 순차 — 동시 실행은 처리 시간을 왜곡한다
        for c in sample:
            if (m, "seq", c.key) in done:
                continue
            reason = spend.blocked(m)
            if reason:
                print("중단: " + reason, flush=True)
                return False
            recs = run_task(m, c, store, "seq", runner=runner, sleep=sleep)
            for r in recs:
                append_jsonl(RECORDS, r)
            spend.add(recs)
        print(spend.line(), flush=True)
    return True


def cmd_score(models: list[str]) -> None:
    originals, planted = _load_claims()
    records = read_jsonl(RECORDS)
    warnings = audit_records(records, originals + planted, models)
    scores = score_stage_b(records, originals + planted, costs.load_prices(), models=models)
    picks: dict[str, str | None] = {}
    for label, healthy in (("literal", False), ("healthy", True)):
        try:
            picks[label] = pick_winner(scores, healthy_only=healthy)
        except ValueError as exc:
            picks[label] = None
            warnings.append(f"승자 선택({label}) 불가: {exc}")
    per_card = len(originals) / max(len(load_manifest()), 1)
    projection = {k: scores[w].cost_per_claim * 216 * per_card * 1.3 for k, w in picks.items() if w}
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "stage_b_scores.json").write_text(json.dumps(
        {"winner": picks.get("literal"), "winner_healthy": picks.get("healthy"), "models": models,
         "scores": {m: asdict(s) for m, s in scores.items()}, "warnings": warnings,
         "stage_a_certifier_cost_projection": projection, "entailment_claims_per_card": per_card},
        ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    any_s = next(iter(scores.values()))
    keys = {c.key for c in originals + planted}
    n2 = len(shared_pass2(_latest([r for r in records if r["model"] in models]), keys, models))
    lines = ["# Stage B 결과 — 검증 AI 비교", "",
             f"- 원본 claim {len(originals)}개(맞는 claim {any_s.n_true}, 불확실 {any_s.n_uncertain}), 심은 오류 {len(planted)}개, 모델당 2회",
             f"- 검출·오탐·비용 = 1차 전부 + 모든 모델에 2차가 있는 claim {n2}/{len(keys)}개의 2차(2차가 일부만 돈 경우의 균형 기준)",
             f"- **승자(승인된 §6 규칙 그대로): {picks.get('literal')}** — 검출률 최고−5%p 이상·GPT-5.5 이상 → 오탐 최저+2%p 이내 → 비용·p95",
             f"- **승자(건강 필터 적용, 사용자 승인 필요): {picks.get('healthy')}** — 오류율 > 5% 또는 오탐 > GPT-5.5+10%p 인 모델을 먼저 뺌", "",
             "| 모델 | 검출률 | BLOCKED 로 검출 | 오탐률 | 오탐 BLOCKED | 오탐 DEMOTED | 2회 일치(n) | 오류율 | claim 당 비용 | p50 | p95(n) | 오류 |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for m, s in sorted(scores.items(), key=lambda kv: -kv[1].catch_rate):
        warn = " ⚠" if s.consistency < 0.90 else ""
        price = f"${s.cost_per_claim:.4f}" + ("" if s.cost_verified else " (미확인)")
        lines.append(f"| {m} | {s.catch_rate:.1%} | {s.catch_blocked_rate:.1%} | {s.fp_rate:.1%} | {s.fp_blocked:.1%} | "
                     f"{s.fp_demoted:.1%} | {s.consistency:.1%}{warn} ({s.n_pairs}) | {s.error_rate:.1%} | {price} | "
                     f"{s.p50_ms / 1000:.1f}s | {s.p95_ms / 1000:.1f}s ({s.n_seq}) | {s.errors or '-'} |")
    lines += ["", "## 다음 단계 비용 추정(재승인 요청)"]
    for k, w in picks.items():
        if w:
            lines.append(f"- Stage A 검증 비용({k} 승자 {w}): 약 ${projection[k]:.0f} = claim 당 ${scores[w].cost_per_claim:.4f} × 216회 × "
                         f"카드당 함의 claim {per_card:.1f}개 × 1.3(다시 쓰기)" + ("" if scores[w].cost_verified else " — 가격 미확인"))
    lines += ["- Stage A 요약 비용: 약 $30–40(추정)", "- 판정 비용: 약 $80–110(추정, 전체 채점)",
              "- ⚠ 표시는 2회 판정 일치율 90% 미만."]
    if warnings:
        lines += ["", "## 기록 점검"] + [f"- {w}" for w in warnings]
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
    for sp in (r, lat):
        sp.add_argument("--budget", type=float, default=BUDGET_USD)
        sp.add_argument("--models", default=",".join(VERIFIERS))
    sc = sub.add_parser("score")
    sc.add_argument("--models", default=",".join(VERIFIERS))
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
        sys.exit(0 if cmd_run(args.passes, args.concurrency, budget=args.budget, models=args.models.split(",")) else 2)
    elif args.cmd == "latency":
        sys.exit(0 if cmd_latency(args.n, budget=args.budget, models=args.models.split(",")) else 2)
    elif args.cmd == "score":
        cmd_score(args.models.split(","))


if __name__ == "__main__":
    main()
