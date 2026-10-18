"""Stage A — 요약 AI 비교(설계 §7).

조건 6가지(A0–A5)를 같은 기사 12건 × 3회로 돌린다. 경로는 운영 `gate.produce_card` 그대로(초안 → 검증 →
실패 시 1회 다시 쓰기 → 발행/보류)이고, 요약 AI·검증 AI 실행기만 실험 러너로 주입한다. 지시는 운영 v3.4 +
사실층 사용자(general·skill 없음). 처리 시간은 동시 실행이 왜곡하므로 반복 1회분(seq_rep)만 순서대로 돌려 잰다.

유료 실행 전 보강(Stage B 에서 실제로 나온 결함 유형):
- 순서: 순차 회차를 먼저, 조건별로 이어서(같은 조건의 호출이 이어져야 프롬프트 캐시가 운영처럼 맞는다).
  병렬은 회차 → 조건 → 기사 — 상한에 걸려도 앞 회차는 모든 조건이 다 돈다.
- 인프라 오류(비정상 종료·API 오류·출력 봉투 깨짐)는 재시도하고 '끝남'으로 치지 않는다. 시간 초과·카드 형식 실패는 모델 행동.
- 예산 상한(작성 실비용 + 검증 목록가)과 조건별 차단기. 검증 호출의 인프라 오류도 재시도.

실행: PYTHONPATH=scripts uv run python -m upgrade_eval.stage_a run --arms A0,A1,A2,A3,A4,A5 --verifier <Stage B 승자>
"""
from __future__ import annotations

import argparse
import collections
import dataclasses
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from typing import Callable

from briefing.core.authoring.author import DraftCard
from briefing.core.config import Settings, load_settings
from briefing.core.gate import _build_envelope, produce_card
from briefing.core.pipeline import _FACT_USER
from briefing.core.stores.source_store import FrozenSource, SourceStore
from briefing.core.verification.certifier import CertVerdict, _certify_arithmetic

from . import costs
from .author_runner import ARMS, Arm, AuthorRun, make_author_fns
from .codex_runner import VERIFIERS, CodexModel, certify_entailment_json, run_codex_json
from .common import EXP_ROOT, append_jsonl, done_keys, read_jsonl
from .select_articles import load_manifest

RECORDS = EXP_ROOT / "runs" / "stage_a" / "records.jsonl"
RESULTS = EXP_ROOT / "results"
PROD_TIMEOUT_MS = 360_000
BUDGET_USD = 50.0                  # Stage A 실행 상한(요약 ~$30–40 + 검증 추정의 약 1.2배) — 넘으면 멈추고 보고
BREAKER_TASKS = 3                  # 한 조건이 연속 3건을 인프라 오류로 끝내면 그 조건 호출을 멈춘다
RETRY_BACKOFF_S = (30, 120)        # 인프라 오류 재시도 간격 — 첫 시도 + 재시도 2번
CODEX_BACKOFF_S = (15, 60)
_INFRA = re.compile(r"^(rc=|envelope 파싱 실패|is_error: API Error)")


def is_infra_error(rec: dict) -> bool:
    """요약 실행의 인프라 오류 — 비정상 종료·API 오류·출력 봉투 깨짐. 시간 초과·카드 형식 실패는 모델 행동이라 아니다."""
    return rec.get("decision") == "ERROR" and bool(_INFRA.match(rec.get("error") or ""))


def _store() -> SourceStore:
    return SourceStore(str(EXP_ROOT / "sources"))


def make_verify_fn(verifier: CodexModel, store: SourceStore, log: list[dict], *, runner=run_codex_json,
                   sleep=time.sleep) -> Callable[[DraftCard], tuple[CertVerdict, ...]]:
    """운영 certify 와 같은 디스패치 — 숫자 claim(재라우팅 후 arithmetic)은 Python, 나머지는 검증 AI.
    검증 호출의 인프라 오류(비정상 종료)는 간격을 두고 최대 2번 더 — 모든 시도를 log 에 남긴다(비용 포함)."""

    def verify(card: DraftCard) -> tuple[CertVerdict, ...]:
        source = store.get_source(card.source_id)
        verdicts = []
        for claim in card.claims:
            envelope = _build_envelope(source, claim)
            if claim.claim_type == "arithmetic":
                verdicts.append(_certify_arithmetic(claim.id, envelope))
                continue
            for attempt in range(1, len(CODEX_BACKOFF_S) + 2):
                verdict, run = certify_entailment_json(claim.id, envelope, verifier, runner=runner)
                log.append({"claim_id": claim.id, "usage": run.usage, "duration_ms": run.duration_ms, "error": run.error,
                            "attempt": attempt})
                if run.error in (None, "timeout") or attempt > len(CODEX_BACKOFF_S):
                    break
                sleep(CODEX_BACKOFF_S[attempt - 1])
            verdicts.append(verdict)
        return tuple(verdicts)

    return verify


def run_one(
    arm: Arm, source: FrozenSource, rep: int, *, sequential: bool, verifier: CodexModel, store: SourceStore,
    settings: Settings, timeout_s: int = 600, author_fns: tuple | None = None, verify_fn: Callable | None = None,
) -> dict:
    author_log: list[AuthorRun] = []
    codex_log: list[dict] = []
    draft, revise = author_fns or make_author_fns(arm, log=author_log, timeout_s=timeout_s)
    first: dict[str, str] = {}

    def draft_once(src, user, st):
        card = draft(src, user, st)
        first.setdefault("summary", card.summary)
        return card

    verify = verify_fn or make_verify_fn(verifier, store, codex_log)
    t0 = time.monotonic()
    record = {"arm": arm.key, "model_id": arm.model_id, "cli_version": arm.cli_version, "effort": arm.effort,
              **({"rules": arm.rules_name} if arm.rules_name else {}),
              "verifier": verifier.name, "source_id": source.source_id, "rep": rep, "sequential": sequential}
    try:
        gated = produce_card(source, _FACT_USER, settings, store, draft_fn=draft_once, revise_fn=revise, verify_fn=verify)
        record.update(decision=gated.decision, attempts=gated.attempts, summary=gated.card.summary,
                      why=gated.card.why_it_matters, claims=[asdict(c) for c in gated.card.claims],
                      verdicts=[asdict(v) for v in gated.verdicts], error=None)
    except Exception as exc:                                       # 실행 실패도 결과다 — 발행 실패율로 센다
        record.update(decision="ERROR", attempts=None, summary=None, why=None, claims=[], verdicts=[], error=str(exc))
    duration = int((time.monotonic() - t0) * 1000)
    record.update(first_draft_summary=first.get("summary"), author_runs=[asdict(r) for r in author_log],
                  codex_calls=codex_log, duration_ms=duration, over_360=duration > PROD_TIMEOUT_MS)
    return record


def plan_tasks(arm_keys: list[str], articles: list[dict], *, reps: int, seq_rep: int,
               done: set[tuple]) -> tuple[list[tuple], list[tuple]]:
    """(순차, 병렬) 작업 목록. 순차 = seq_rep 회차를 조건별로 이어서. 병렬 = 회차 → 조건 → 기사."""
    seq = [(ARMS[k], a["source_id"], seq_rep) for k in arm_keys for a in articles
           if 1 <= seq_rep <= reps and (k, a["source_id"], seq_rep) not in done]
    par = [(ARMS[k], a["source_id"], r) for r in range(1, reps + 1) if r != seq_rep for k in arm_keys for a in articles
           if (k, a["source_id"], r) not in done]
    return seq, par


class _Spend:
    """누적 비용(이전 실행분 포함 — 재개해도 상한은 하나)과 조건별 연속 인프라 실패."""

    def __init__(self, budget: float, prices: dict, verifier: str, previous: list[dict]):
        self.budget, self.prices, self.verifier, self.lock = budget, prices, verifier, threading.Lock()
        self.spent, self.n, self.by_arm, self.streak, self.left = 0.0, 0, {}, {}, set()
        for r in previous:
            self._cost(r)

    def _cost(self, rec: dict) -> None:
        usd, _ = costs.card_cost(rec, self.prices, self.verifier)
        self.spent += usd
        self.by_arm[rec["arm"]] = self.by_arm.get(rec["arm"], 0.0) + usd

    def add(self, rec: dict) -> None:
        with self.lock:
            self._cost(rec)

    def task_done(self, rec: dict) -> int:
        with self.lock:
            key = (rec["arm"], rec["source_id"], rec["rep"])
            if is_infra_error(rec):
                self.streak[rec["arm"]] = self.streak.get(rec["arm"], 0) + 1
                self.left.add(key)
            else:
                self.streak[rec["arm"]] = 0
                self.left.discard(key)
            self.n += 1
            return self.n

    def blocked(self, arm_key: str) -> str | None:
        with self.lock:
            if self.spent >= self.budget:
                return f"예산 상한 ${self.budget:.0f} 도달(누적 ${self.spent:.2f})"
            if self.streak.get(arm_key, 0) >= BREAKER_TASKS:
                return f"{arm_key}: 연속 {BREAKER_TASKS}건 인프라 오류 — 이 조건 호출 중단"
        return None

    def line(self) -> str:
        with self.lock:
            return (f"  … {self.n}건 · 누적 ${self.spent:.2f}/{self.budget:.0f} · "
                    + ", ".join(f"{a} ${v:.2f}" for a, v in sorted(self.by_arm.items())))


def run_stage_a(arm_keys: list[str], *, verifier: str, reps: int = 3, seq_rep: int = 1, concurrency: int = 4,
                budget: float = BUDGET_USD, run_one_fn: Callable | None = None, sleep=time.sleep,
                prices: dict | None = None) -> bool:
    """순차 회차 먼저(하나씩) → 병렬 회차. 반환: 상한·차단기·남은 인프라 오류 없이 끝났나(False 면 보고)."""
    articles = load_manifest()
    store = _store()
    base = load_settings()
    run = run_one_fn or run_one
    done = done_keys(RECORDS, ("arm", "source_id", "rep"), where=lambda r: not is_infra_error(r))
    sequential, parallel = plan_tasks(arm_keys, articles, reps=reps, seq_rep=seq_rep, done=done)
    spend = _Spend(budget, costs.load_prices() if prices is None else prices, verifier, read_jsonl(RECORDS))
    print(f"stage_a: sequential {len(sequential)}, parallel {len(parallel)}, skipped {len(done)}", flush=True)
    lock = threading.Lock()

    def work(task, *, seq: bool):
        arm, sid, rep = task
        if spend.blocked(arm.key):
            return
        settings = dataclasses.replace(base, author_model_id=arm.model_id, backend="local")
        for attempt in range(1, len(RETRY_BACKOFF_S) + 2):
            rec = run(arm, store.get_source(sid), rep, sequential=seq, verifier=VERIFIERS[verifier], store=store,
                      settings=settings, timeout_s=600)
            rec["attempt"] = attempt
            with lock:
                append_jsonl(RECORDS, rec)
            spend.add(rec)
            if not is_infra_error(rec) or attempt > len(RETRY_BACKOFF_S):
                break
            sleep(RETRY_BACKOFF_S[attempt - 1])
        if spend.task_done(rec) % 6 == 0:
            print(spend.line(), flush=True)

    for t in sequential:                                           # 처리 시간 측정분 — 하나씩, 먼저
        work(t, seq=True)
    with ThreadPoolExecutor(max_workers=min(concurrency, 4)) as pool:
        list(pool.map(lambda t: work(t, seq=False), parallel))
    print(spend.line(), flush=True)
    reasons = sorted({spend.blocked(k) for k in arm_keys} - {None})
    if spend.left:
        reasons.append(f"인프라 오류로 남은 키 {len(spend.left)}개 — 다시 실행하면 그것만 이어서 돈다")
    if reasons:
        print("중단: " + " / ".join(reasons), flush=True)
    return not reasons


def write_summary() -> str:
    recs = read_jsonl(RECORDS)
    by_arm = collections.defaultdict(list)
    for r in recs:
        by_arm[r["arm"]].append(r)
    lines = ["# Stage A 실행 기록", "", "| 조건 | 실행 | PUBLISH | QUARANTINE | ERROR | 순차분 360초 초과 |", "|---|---|---|---|---|---|"]
    for arm in sorted(by_arm):
        rs = by_arm[arm]
        c = collections.Counter(r["decision"] for r in rs)
        over = sum(r["over_360"] for r in rs if r["sequential"])
        lines.append(f"| {arm} | {len(rs)} | {c['PUBLISH']} | {c['QUARANTINE']} | {c['ERROR']} | {over} |")
    errors = [f"- {r['arm']} {r['source_id'][:10]} rep{r['rep']}: {r['error'][:120]}" for r in recs if r["decision"] == "ERROR"]
    text = "\n".join(lines + (["", "## 오류", *errors] if errors else [])) + "\n"
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "stage_a_runs.md").write_text(text, encoding="utf-8")
    return text


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="stage_a")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--arms", required=True)
    r.add_argument("--verifier", required=True, choices=sorted(VERIFIERS))
    r.add_argument("--reps", type=int, default=3)
    r.add_argument("--seq-rep", type=int, default=1)
    r.add_argument("--concurrency", type=int, default=4)
    r.add_argument("--budget", type=float, default=BUDGET_USD)
    sub.add_parser("summary")
    args = ap.parse_args(argv)
    ok = True
    if args.cmd == "run":
        ok = run_stage_a(args.arms.split(","), verifier=args.verifier, reps=args.reps, seq_rep=args.seq_rep,
                         concurrency=args.concurrency, budget=args.budget)
    print(write_summary())
    if not ok:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
