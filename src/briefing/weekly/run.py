"""주간 모드 진입점 — build · send · approve · pull. 로컬 CLI(1-A)와 런타임 분기(1-B)가 **같은 함수**를 부른다.

설정은 env-first(루트 `.env`, 데일리와 같은 방식):
  WEEKLY_ADMIN_USER_ID(필수 — `briefing-users` 의 user_id; 이메일은 거기서 읽는다, git 에 두지 않는다) ·
  WEEKLY_AUTHOR_MODEL_ID · WEEKLY_AUTHOR_EFFORT(기본 = 데일리 author) · WEEKLY_SELECT_MODEL_ID(기본 = 주간 author) ·
  WEEKLY_STRICT(1) · WEEKLY_REFETCH(1) · WEEKLY_MAX_REVISIONS(2) · WEEKLY_SENDER_NAME("Field Experiment") ·
  WEEKLY_WAIT_UNTIL("06:40" KST — 금요일 run 지연 대기 상한) · WEEKLY_ISSUES_BACKEND(local|dynamo, 기본 = BACKEND).
실행: uv run python -m briefing.weekly.run build|send|approve|pull [--date YYYY-MM-DD] [--dry-run]
  (BACKEND=dynamo + WEEKLY_ISSUES_BACKEND=local = 실제 원장을 읽고 결과는 `.data/weekly_issues/` 에만 — 1-A · 시험용)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from ..core import _debug
from ..core.config import Settings, load_settings, load_user
from ..core.stores.backends import make_stores
from ..core.stores.usage import UsageRecorder
from ..core.verification.certifier import certify
from .checks import check_models, check_repo_links
from .collect import collect, friday_ready
from .gate import run_gate
from .issues import TransitionError, issue_store_from_settings
from .render import email_subject, render_email, split_title
from .select import select
from .write import feedback_from_gate, none_issue_md, refetch_url, revise, source_text, write

KST = ZoneInfo("Asia/Seoul")
_POLL_S = 300


@dataclass(frozen=True)
class WeeklySettings:
    admin_user_id: str
    author_model_id: str
    author_effort: str
    select_model_id: str
    strict: bool = True
    refetch: bool = True
    max_revisions: int = 2
    sender_name: str = "Field Experiment"
    wait_until: str = "06:40"


def load_weekly_settings(settings: Settings) -> WeeklySettings:
    g = os.getenv
    author = g("WEEKLY_AUTHOR_MODEL_ID", "") or settings.author_model_id
    return WeeklySettings(
        admin_user_id=g("WEEKLY_ADMIN_USER_ID", ""),
        author_model_id=author,
        author_effort=g("WEEKLY_AUTHOR_EFFORT", "") or settings.author_effort,
        select_model_id=g("WEEKLY_SELECT_MODEL_ID", "") or author,
        strict=g("WEEKLY_STRICT", "1").strip().lower() in ("1", "true", "yes", "on"),
        refetch=g("WEEKLY_REFETCH", "1").strip().lower() in ("1", "true", "yes", "on"),
        max_revisions=int(g("WEEKLY_MAX_REVISIONS", "2")),
        sender_name=g("WEEKLY_SENDER_NAME", "Field Experiment"),
        wait_until=g("WEEKLY_WAIT_UNTIL", "06:40"),
    )


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _wait_for_friday(ledger, user_id: str, issue_date: str, wait_until: str, *, now=_now_utc, sleep=time.sleep,
                     notes: list[str]) -> bool:
    """재료 마감 — 금요일 run_date 행이 생길 때까지 KST 마감 시각까지 5분 간격으로 기다린다. 넘기면 있는 카드로 진행(기록)."""
    hh, mm = wait_until.split(":")
    deadline = datetime.fromisoformat(issue_date).replace(hour=int(hh), minute=int(mm), tzinfo=KST)
    while not friday_ready(ledger, user_id, issue_date):
        if now() >= deadline:
            notes.append(f"금요일 run_date 원장 행 없음({wait_until} KST 까지 대기) — 있는 카드로 생성")
            return False
        sleep(_POLL_S)
    return True


def build(issue_date: str, settings: Settings, ws: WeeklySettings, *, store, card_cache, ledger, issue_store,
          run_author=None, certify_fn=certify, refetch=refetch_url, repo_http=None, profiles=None,
          now=_now_utc, sleep=time.sleep, recorder: UsageRecorder | None = None) -> dict:
    """06:00 — 수집 → 씨앗 → 원문 → 작성 → 게이트(실패 항목만 돌려주는 재작성 ≤ max_revisions) → ready | quarantined | failed."""
    if not ws.admin_user_id:
        raise ValueError("WEEKLY_ADMIN_USER_ID 필요")
    try:
        issue_store.transition(issue_date, "building", started_at=now().isoformat(timespec="seconds"))
    except TransitionError as e:
        return {"status": "skipped", "reason": str(e)}
    recorder = recorder or UsageRecorder()
    notes: list[str] = []
    stage = "collect"
    try:
        _wait_for_friday(ledger, ws.admin_user_id, issue_date, ws.wait_until, now=now, sleep=sleep, notes=notes)
        cards = collect(ledger, card_cache, store, ws.admin_user_id, issue_date)
        notes.append(f"카드 {len(cards)}장(캐시 miss {sum(1 for c in cards if not c.cached)})")
        stage = "select"
        seed = select(cards, issue_date, settings, model_id=ws.select_model_id, effort=ws.author_effort,
                      run_author=run_author, recorder=recorder)
        if seed.none:
            md = none_issue_md(seed, cards, issue_date)
            issue_store.transition(issue_date, "ready", issue_md=md, email_html=render_email(md), seed_json=seed.to_json(),
                                   gate_json=json.dumps({"status": "PASS", "note": "씨앗 없음 — 게이트 생략"}, ensure_ascii=False),
                                   cites_json="[]", attempts="0", cost_usd=f"{recorder.total():.4f}", notes="; ".join(notes))
            return {"status": "ready", "none": True, "cards": len(cards), "cost_usd": recorder.total()}
        stage = "source"
        by_n = {c.n: c for c in cards}
        texts = {n: source_text(store, by_n[n], refetch=refetch if ws.refetch else None) for n in seed.cards}
        stage = "write"
        draft = write(seed, cards, texts, issue_date, settings, model_id=ws.author_model_id, effort=ws.author_effort,
                      run_author=run_author, recorder=recorder)
        extra = [lambda md: check_repo_links(md, **({"http": repo_http} if repo_http else {})),
                 lambda md: check_models(md, **({"profiles": profiles} if profiles else {}))]
        attempts = 1
        stage = "gate"
        result = run_gate(draft.md, draft.cites, cards, strict=ws.strict, certify_fn=certify_fn, extra_checks=extra)
        while result.status != "PASS" and attempts <= ws.max_revisions:
            stage = "revise"
            draft = revise(draft, feedback_from_gate(result), settings, model_id=ws.author_model_id,
                           effort=ws.author_effort, run_author=run_author, recorder=recorder)
            attempts += 1
            stage = "gate"
            result = run_gate(draft.md, draft.cites, cards, strict=ws.strict, certify_fn=certify_fn, extra_checks=extra)
        status = "ready" if result.status == "PASS" else "quarantined"
        fails = " / ".join(it.msg for it in result.items if it.verdict == "FAIL")
        banner = "" if status == "ready" else f"검사 실패 — 격리(1단계는 관리자에게만): {fails}"[:600]
        issue_store.transition(issue_date, status, issue_md=draft.md, email_html=render_email(draft.md, banner=banner),
                               cites_json=json.dumps([asdict(c) for c in draft.cites], ensure_ascii=False),
                               gate_json=result.to_json(), seed_json=seed.to_json(), attempts=str(attempts),
                               cost_usd=f"{recorder.total():.4f}", notes="; ".join(notes))
        return {"status": status, "attempts": attempts, "cards": len(cards), "seed": seed.seed, "cost_usd": recorder.total()}
    except Exception as e:  # noqa: BLE001 — 어느 단계든 실패를 기록(07:00 send 가 관리자에게 알린다)
        _debug.warn("weekly build", f"{stage}: {type(e).__name__}: {e}")
        try:
            issue_store.transition(issue_date, "failed", error=f"{stage}: {type(e).__name__}: {e}"[:1000],
                                   notes="; ".join(notes))
        except TransitionError as e2:
            _debug.warn("weekly build", f"failed 기록 불가: {e2}")
        return {"status": "failed", "stage": stage, "error": f"{type(e).__name__}: {e}"}


def _ses_sender(settings: Settings, ws: WeeklySettings):
    """기본 send_fn — SES SendEmail, 발신 = 데일리 신원 + 표시 이름. (4단계에서 scheduler/deliver 의 send_html 로 바꾼다.)"""
    def _send(to: str, subject: str, html: str) -> str:
        import boto3  # lazy
        ses = boto3.client("ses", region_name=settings.region)
        r = ses.send_email(Source=f"{ws.sender_name} <{settings.ses_sender}>", Destination={"ToAddresses": [to]},
                           Message={"Subject": {"Data": subject, "Charset": "UTF-8"},
                                    "Body": {"Html": {"Data": html, "Charset": "UTF-8"}}})
        return str(r["MessageId"])
    return _send


def _failure_html(issue_date: str, item: dict | None) -> str:
    status = item["status"] if item else "없음(build 가 돌지 않음)"
    err = (item or {}).get("error", "")
    return (f"<p>Field Experiment {issue_date} 호가 07:00 발송 시각에 준비되지 않았습니다.</p>"
            f"<p>상태: {status}</p><p>{err}</p><p>수동: build 뒤 send.</p>")


def send(issue_date: str, settings: Settings, ws: WeeklySettings, *, issue_store, send_fn=None, sent_log=None,
         dry_run: bool = False, load_user_fn=load_user) -> dict:
    """07:00 — ready · quarantined 면 관리자에게 발송(두 번째 실행은 상태 전이에서 멈춘다). building · failed · 없음 → 실패 통지."""
    if not ws.admin_user_id:
        raise ValueError("WEEKLY_ADMIN_USER_ID 필요")
    to = load_user_fn(ws.admin_user_id, settings).recipient
    send_fn = send_fn or _ses_sender(settings, ws)
    item = issue_store.get(issue_date)
    if item is None or item["status"] in ("building", "failed"):
        subject = f"[현장 실험] 생성 실패 {issue_date}"
        if dry_run:
            return {"status": "dry-run", "would": "failure-notice", "to": to, "subject": subject}
        return {"status": "notified_failure", "message_id": send_fn(to, subject, _failure_html(issue_date, item)), "to": to}
    if item["status"] not in ("ready", "quarantined"):
        return {"status": "skipped", "reason": f"status={item['status']}"}
    quarantined = item["status"] == "quarantined"
    subject = email_subject(split_title(item["issue_md"])[0]) + (" — 격리(검사 실패)" if quarantined else "")
    html = item["email_html"]
    if dry_run:
        return {"status": "dry-run", "to": to, "subject": subject, "bytes": len(html.encode("utf-8"))}
    try:
        issue_store.transition(issue_date, "sending")
    except TransitionError as e:
        return {"status": "skipped", "reason": str(e)}
    try:
        mid = send_fn(to, subject, html)
    except Exception as e:  # noqa: BLE001
        issue_store.transition(issue_date, "send_failed", error=f"{type(e).__name__}: {e}"[:500])
        raise
    issue_store.transition(issue_date, "sent", message_id=mid, sent_to_user=ws.admin_user_id,
                           sent_at=_now_utc().isoformat(timespec="seconds"))
    if sent_log is not None:   # 관리자 화면(/admin/emails 가 sent-log 를 Scan) — 데일리 키와 겹치지 않게 weekly#
        sent_log.mark_sent(f"weekly#{ws.admin_user_id}", issue_date,
                           record={"brand": "field-experiment", "message_id": mid, "subject": subject,
                                   "issue_status": item["status"], "cost_usd": item.get("cost_usd", "")})
    return {"status": "sent", "message_id": mid, "to": to, "subject": subject}


def approve(issue_date: str, **_) -> dict:
    """2단계(동료 opt-in) 에서 구현 — delivery-plan.md §1. 지금은 아무것도 보내지 않는다."""
    return {"status": "unimplemented", "reason": "approve 는 2단계(동료 opt-in)에서 — field-experiment/delivery-plan.md §1"}


def pull(issue_date: str, *, issue_store, out_dir: Path) -> dict:
    """표 → `issues/YYYY-MM-DD.md`(기사) + `.log.md`(run 로그: 씨앗 깔때기 · 게이트 · 비용 · 발송). 사람이 읽는 사본."""
    item = issue_store.get(issue_date)
    if item is None:
        raise KeyError(f"{issue_date} 호 없음")
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path, log_path = out_dir / f"{issue_date}.md", out_dir / f"{issue_date}.log.md"
    md_path.write_text(item.get("issue_md", ""), encoding="utf-8")
    seed = json.loads(item.get("seed_json") or "{}")
    gate = json.loads(item.get("gate_json") or "{}")
    lines = [f"# {issue_date} run 로그 (자동 생성 — 독자 메일에 넣지 않음)", "",
             f"- 상태: {item.get('status')} · 시도 {item.get('attempts', '')} · 비용 ${item.get('cost_usd', '')} · "
             f"발송 {item.get('sent_at', '')} {item.get('message_id', '')}",
             f"- 기록: {item.get('notes', '')}", f"- 오류: {item.get('error', '')}" if item.get("error") else "", ""]
    if seed:
        lines += ["## 씨앗", f"- seed #{seed.get('seed')} · support {seed.get('support')} · aws_line {seed.get('aws_line')}",
                  f"- 메커니즘: {seed.get('mechanism', '')}", f"- 근거: {seed.get('reason', '')}", "", "### 후보(영역 · 게이트 2 · 3)"]
        lines += [f"- #{c.get('card')} {c.get('area')} · 메커니즘 {c.get('mechanism')} · AWS {c.get('aws_path')} — {c.get('note', '')}"
                  for c in seed.get("candidates", [])]
        lines += ["", "### 고르지 않음"] + [f"- #{n} — {why}" for n, why in seed.get("not_chosen", [])] + [""]
    if gate:
        lines += [f"## 게이트: {gate.get('status', '')}" + (f" — {gate['note']}" if gate.get("note") else "")]
        lines += [f"- {it['verdict']:4} {it['check']}: {it['msg']}" for it in gate.get("items", [])] + [""]
    log_path.write_text("\n".join(lines), encoding="utf-8")
    return {"md": str(md_path), "log": str(log_path), "status": item.get("status")}


def _default_date() -> str:
    today = datetime.now(KST).date()
    if today.weekday() != 5:
        raise SystemExit("오늘은 토요일이 아니다 — --date YYYY-MM-DD 를 주세요")
    return today.isoformat()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="briefing.weekly.run", description=__doc__.split("\n")[0])
    ap.add_argument("cmd", choices=["build", "send", "approve", "pull"])
    ap.add_argument("--date", default="", help="발행일(토) YYYY-MM-DD. 기본 = 오늘(KST, 토요일일 때만)")
    ap.add_argument("--dry-run", action="store_true", help="send: 수신자 · 제목 · 바이트만 출력")
    ap.add_argument("--out", default="field-experiment/issues", help="pull: 저장 폴더")
    a = ap.parse_args(argv)
    issue_date = a.date or _default_date()
    settings = load_settings()
    ws = load_weekly_settings(settings)
    issue_store = issue_store_from_settings(settings)
    if a.cmd == "build":
        store, card_cache, ledger = make_stores(settings)
        r = build(issue_date, settings, ws, store=store, card_cache=card_cache, ledger=ledger, issue_store=issue_store)
    elif a.cmd == "send":
        sent_log = None
        if settings.backend == "dynamo" and not a.dry_run:
            from ..scheduler.sent_log import DynamoSentLog
            sent_log = DynamoSentLog.from_settings(settings)
        r = send(issue_date, settings, ws, issue_store=issue_store, sent_log=sent_log, dry_run=a.dry_run)
    elif a.cmd == "approve":
        r = approve(issue_date)
    else:
        r = pull(issue_date, issue_store=issue_store, out_dir=Path(a.out))
    print(json.dumps(r, ensure_ascii=False, indent=1))
    return 1 if r.get("status") in ("failed", "send_failed", "unimplemented") else 0


if __name__ == "__main__":
    sys.exit(main())
