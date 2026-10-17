"""Stage A — 요약 AI 비교(설계 §7).

조건 6가지(A0–A5)를 같은 기사 12건 × 3회로 돌린다. 경로는 운영 `gate.produce_card` 그대로(초안 → 검증 →
실패 시 1회 다시 쓰기 → 발행/보류)이고, 요약 AI·검증 AI 실행기만 실험 러너로 주입한다. 지시는 운영 v3.4 +
사실층 사용자(general·skill 없음). 처리 시간은 동시 실행이 왜곡하므로 반복 1회분(seq_rep)만 순서대로 돌려 잰다.

실행: PYTHONPATH=scripts uv run python -m upgrade_eval.stage_a run --arms A0,A1,A2,A3,A4,A5 --verifier <Stage B 승자>
"""
from __future__ import annotations

import argparse
import collections
import dataclasses
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

from .author_runner import ARMS, Arm, AuthorRun, make_author_fns
from .codex_runner import VERIFIERS, CodexModel, certify_entailment_json
from .common import EXP_ROOT, append_jsonl, done_keys, read_jsonl
from .select_articles import load_manifest

RECORDS = EXP_ROOT / "runs" / "stage_a" / "records.jsonl"
RESULTS = EXP_ROOT / "results"
PROD_TIMEOUT_MS = 360_000


def _store() -> SourceStore:
    return SourceStore(str(EXP_ROOT / "sources"))


def make_verify_fn(verifier: CodexModel, store: SourceStore, log: list[dict]) -> Callable[[DraftCard], tuple[CertVerdict, ...]]:
    """운영 certify 와 같은 디스패치 — 숫자 claim(재라우팅 후 arithmetic)은 Python, 나머지는 검증 AI."""

    def verify(card: DraftCard) -> tuple[CertVerdict, ...]:
        source = store.get_source(card.source_id)
        verdicts = []
        for claim in card.claims:
            envelope = _build_envelope(source, claim)
            if claim.claim_type == "arithmetic":
                verdicts.append(_certify_arithmetic(claim.id, envelope))
                continue
            verdict, run = certify_entailment_json(claim.id, envelope, verifier)
            log.append({"claim_id": claim.id, "usage": run.usage, "duration_ms": run.duration_ms, "error": run.error})
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


def run_stage_a(arm_keys: list[str], *, verifier: str, reps: int = 3, seq_rep: int = 1, concurrency: int = 4) -> None:
    articles = load_manifest()
    store = _store()
    base = load_settings()
    done = done_keys(RECORDS, ("arm", "source_id", "rep"))
    parallel, sequential = [], []
    for key in arm_keys:
        for a in articles:
            for rep in range(1, reps + 1):
                if (key, a["source_id"], rep) not in done:
                    (sequential if rep == seq_rep else parallel).append((ARMS[key], a["source_id"], rep))
    print(f"stage_a: parallel {len(parallel)}, sequential {len(sequential)}, skipped {len(done)}", flush=True)
    lock = threading.Lock()

    def work(task, *, seq: bool, timeout_s: int):
        arm, sid, rep = task
        settings = dataclasses.replace(base, author_model_id=arm.model_id, backend="local")
        rec = run_one(arm, store.get_source(sid), rep, sequential=seq, verifier=VERIFIERS[verifier], store=store,
                      settings=settings, timeout_s=timeout_s)
        with lock:
            append_jsonl(RECORDS, rec)

    with ThreadPoolExecutor(max_workers=min(concurrency, 4)) as pool:
        list(pool.map(lambda t: work(t, seq=False, timeout_s=600), parallel))
    for t in sequential:                                           # 처리 시간 측정분 — 하나씩
        work(t, seq=True, timeout_s=600)


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
    sub.add_parser("summary")
    args = ap.parse_args(argv)
    if args.cmd == "run":
        run_stage_a(args.arms.split(","), verifier=args.verifier, reps=args.reps, seq_rep=args.seq_rep,
                    concurrency=args.concurrency)
    print(write_summary())


if __name__ == "__main__":
    main()
