"""주간 모드 진입점 — build · send · approve · pull. 로컬 CLI(1-A)와 런타임 분기(1-B)가 **같은 함수**를 부른다.

설정은 env-first(루트 `.env`, 데일리와 같은 방식):
  WEEKLY_ADMIN_USER_ID(필수 — `briefing-users` 의 user_id; 이메일은 거기서 읽는다, git 에 두지 않는다) ·
  WEEKLY_AUTHOR_MODEL_ID · WEEKLY_AUTHOR_EFFORT(기본 = 데일리 author) · WEEKLY_SELECT_MODEL_ID(기본 = 주간 author) ·
  WEEKLY_STRICT(1) · WEEKLY_REFETCH(1) · WEEKLY_MAX_REVISIONS(2) · WEEKLY_SENDER_NAME("Field Experiment") ·
  WEEKLY_AUTHOR_TIMEOUT_S(0 = 데일리 author 기본 360 — Opus 5.5 high 기사 작성은 넘기므로 .env 에서 올린다, 2026-11-07) ·
  WEEKLY_WAIT_UNTIL("06:40" KST — 금요일 run 지연 대기 상한) · WEEKLY_ISSUES_BACKEND(local|dynamo, 기본 = BACKEND) ·
  WEEKLY_CRITIQUE(1 — 게이트 앞 자기 비평 pass) · WEEKLY_FIGURE(0 — 이미지 트랙; 호스트 · 컨테이너 둘 다, playwright 없으면 건너뜀.
  PNG 는 표의 `figure_png_b64` 로 07:00 send 세션에 넘긴다 — 1-B 는 build 와 send 가 다른 microVM, 2026-11-07 (d)).
실행: uv run python -m briefing.weekly.run build|send|approve|pull [--date YYYY-MM-DD] [--dry-run]
  (BACKEND=dynamo + WEEKLY_ISSUES_BACKEND=local = 실제 원장을 읽고 결과는 `.data/weekly_issues/` 에만 — 1-A · 시험용)
클라우드(1-B): 런타임 분기(`runtime/agentcore_runtime.py`)가 `run_cloud(mode, payload, …)` 를 부른다 — mode=weekly_build·weekly_send,
  발행일 = payload `issue_date` 또는 **KST** 오늘(`issue_date_kst`; 06:00 KST 토 = 21:00 UTC 금이라 UTC 날짜는 금요일 호가 된다).
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import tempfile
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
from .checks import check_models, check_repo_links, check_ruler
from .collect import collect, friday_ready
from .gate import run_gate
from .issues import TransitionError, issue_store_from_settings
from .render import email_subject, render_email, split_title
from .select import select
from .write import critique, feedback_from_gate, none_issue_md, refetch_url, revise, source_text, write

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
    critique: bool = False      # A 설계(2026-11-04): 게이트 앞 자기 비평 → revise. env 기본은 켬(테스트 기본은 끔)
    figure: bool = False        # 이미지 트랙(scheme A PNG) — 호스트 · 컨테이너(2026-11-07 (d)). env 기본 끔
    author_timeout_s: int = 0   # 작성자 subprocess 상한(초). 0 = 데일리 기본(360). 클라우드 build write 가 360 에 끊김(11-07)


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
        critique=g("WEEKLY_CRITIQUE", "1").strip().lower() in ("1", "true", "yes", "on"),
        figure=g("WEEKLY_FIGURE", "0").strip().lower() in ("1", "true", "yes", "on"),
        author_timeout_s=int(g("WEEKLY_AUTHOR_TIMEOUT_S", "0") or 0),
    )


FIGURE_B64_MAX_CHARS = 300_000   # 표 항목(DDB 400KB) 안에 PNG(b64)를 싣는 상한 — 넘으면 b64 생략(기사는 그대로, notes 에만)


def figure_dir(issue_date: str) -> Path:
    """호의 그림 작업 폴더(로컬 store 옆) — `.data/weekly_issues/fig/<date>/`.
    그 자리를 만들 수 없으면(컨테이너 CWD `/app` 은 root 소유 — 11-07 클라우드 build 가 `PermissionError: '.data'` 로 그림을 건너뜀)
    임시 폴더로 간다 — PNG 는 어차피 표(`figure_png_b64`)로 send 세션에 넘어가므로 폴더 위치는 중요하지 않다."""
    base = Path(os.getenv("WEEKLY_ISSUES_PATH", "./.data/weekly_issues")) / "fig"
    try:
        base.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        fallback = Path(tempfile.gettempdir()) / "briefing_weekly_fig"
        _debug.warn("weekly figure", f"그림 폴더 {base} 를 만들 수 없음({type(e).__name__}) → {fallback}")
        base = fallback
        base.mkdir(parents=True, exist_ok=True)
    return base / issue_date


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def issue_date_kst(now: datetime) -> str:
    """발행일 = KST 날짜(토요일 검사 없음 — 스케줄이 토요일에만 부른다; 수동 호출은 payload issue_date 로)."""
    return now.astimezone(KST).date().isoformat()


def run_cloud(mode: str, payload: dict, settings: Settings, ws: WeeklySettings, *, stores, issue_store, sent_log=None,
              now=_now_utc) -> dict:
    """런타임 분기 공용(1-B) — 로컬 CLI 와 **같은 build · send**. dry_run 은 send 에만 뜻이 있다(build 는 표에만 쓴다)."""
    issue_date = payload.get("issue_date") or issue_date_kst(now())
    if mode == "weekly_build":
        store, card_cache, ledger = stores
        r = build(issue_date, settings, ws, store=store, card_cache=card_cache, ledger=ledger, issue_store=issue_store)
    elif mode == "weekly_send":
        r = send(issue_date, settings, ws, issue_store=issue_store, sent_log=sent_log, dry_run=bool(payload.get("dry_run")))
    else:
        raise ValueError(f"알 수 없는 주간 mode: {mode}")
    return {"issue_date": issue_date, **r}


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
          now=_now_utc, sleep=time.sleep, recorder: UsageRecorder | None = None, figure_fn=None) -> dict:
    """06:00 — 수집 → 씨앗 → 원문 → 작성 → (자기 비평 → 수정) → 게이트(실패 항목만 돌려주는 재작성 ≤ max_revisions) → (그림) → ready | quarantined | failed.
    figure_fn(옵션) = make_figure 대체(테스트). 그림 실패 · 환경 없음은 기사 상태를 바꾸지 않는다(notes 에만)."""
    if not ws.admin_user_id:
        raise ValueError("WEEKLY_ADMIN_USER_ID 필요")
    try:
        issue_store.transition(issue_date, "building", started_at=now().isoformat(timespec="seconds"))
    except TransitionError as e:
        return {"status": "skipped", "reason": str(e)}
    recorder = recorder or UsageRecorder()
    notes: list[str] = []
    author_kw = dict(effort=ws.author_effort, run_author=run_author, recorder=recorder,
                     timeout_s=ws.author_timeout_s or None)   # None = 데일리 기본 360
    stage = "collect"
    try:
        _wait_for_friday(ledger, ws.admin_user_id, issue_date, ws.wait_until, now=now, sleep=sleep, notes=notes)
        cards = collect(ledger, card_cache, store, ws.admin_user_id, issue_date)
        notes.append(f"카드 {len(cards)}장(캐시 miss {sum(1 for c in cards if not c.cached)})")
        stage = "select"
        seed = select(cards, issue_date, settings, model_id=ws.select_model_id, **author_kw)
        if seed.none:
            md = none_issue_md(seed, cards, issue_date)
            issue_store.transition(issue_date, "ready", issue_md=md, email_html=render_email(md), seed_json=seed.to_json(),
                                   gate_json=json.dumps({"status": "PASS", "note": "씨앗 없음 — 게이트 생략"}, ensure_ascii=False),
                                   cites_json="[]", attempts="0", cost_usd=f"{recorder.total():.4f}", notes="; ".join(notes),
                                   calls_json=json.dumps(recorder.calls))
            return {"status": "ready", "none": True, "cards": len(cards), "cost_usd": recorder.total()}
        stage = "source"
        by_n = {c.n: c for c in cards}
        texts = {n: source_text(store, by_n[n], refetch=refetch if ws.refetch else None) for n in seed.cards}
        stage = "write"
        draft = write(seed, cards, texts, issue_date, settings, model_id=ws.author_model_id, **author_kw)
        if ws.critique:
            stage = "critique"
            issues = critique(draft, cards, texts, settings, model_id=ws.author_model_id, **author_kw)
            notes.append(f"자기 비평 {len(issues)}건")
            if issues:
                draft = revise(draft, issues, settings, model_id=ws.author_model_id, **author_kw)
        extra = [lambda md: check_repo_links(md, **({"http": repo_http} if repo_http else {})),
                 lambda md: check_models(md, **({"profiles": profiles} if profiles else {})), check_ruler]
        attempts = 1
        stage = "gate"
        gate_kw = dict(strict=ws.strict, certify_fn=certify_fn, extra_checks=extra, seed_card=seed.seed)
        result = run_gate(draft.md, draft.cites, cards, texts, **gate_kw)
        while result.status != "PASS" and attempts <= ws.max_revisions:
            feedback = feedback_from_gate(result)
            if not feedback:   # 작성자가 고칠 수 없는 실패(certifier 미가용)만 남음 — 재작성해도 못 넘는다(2026-11-04 실측 2회 × $0.9)
                notes.append("재작성 생략: 작성자가 고칠 수 없는 실패만(certifier 미가용)")
                break
            stage = "revise"
            draft = revise(draft, feedback, settings, model_id=ws.author_model_id, **author_kw)
            attempts += 1
            stage = "gate"
            result = run_gate(draft.md, draft.cites, cards, texts, **gate_kw)
        status = "ready" if result.status == "PASS" else "quarantined"
        fails = " / ".join(it.msg for it in result.items if it.verdict == "FAIL")
        banner = "" if status == "ready" else f"검사 실패 — 격리(1단계는 관리자에게만): {fails}"[:600]
        fig_fields: dict[str, str] = {}
        if ws.figure:
            stage = "figure"
            try:
                fn = figure_fn or _default_figure_fn()
                fig = fn(draft.md, settings, out_dir=figure_dir(issue_date), model_id=ws.author_model_id,
                         effort=ws.author_effort, run_author=run_author, recorder=recorder,
                         timeout_s=ws.author_timeout_s or None)
                notes.append(f"그림 {fig.status}" + (f"({fig.note})" if fig.note else ""))
                fig_fields = {"figure_status": fig.status, "figure_json": fig.to_json(), "figure_png": fig.png}
                fig_fields.update(_figure_b64_field(fig, notes))
            except Exception as e:  # noqa: BLE001 — 그림은 기사를 막지 않는다
                _debug.warn("weekly figure", f"{type(e).__name__}: {e}")
                notes.append(f"그림 실패: {type(e).__name__}")
        stage = "store"
        issue_store.transition(issue_date, status, issue_md=draft.md, email_html=render_email(draft.md, banner=banner), banner=banner,
                               cites_json=json.dumps([asdict(c) for c in draft.cites], ensure_ascii=False),
                               gate_json=result.to_json(), seed_json=seed.to_json(), attempts=str(attempts),
                               cost_usd=f"{recorder.total():.4f}", notes="; ".join(notes),
                               calls_json=json.dumps(recorder.calls), **fig_fields)
        return {"status": status, "attempts": attempts, "cards": len(cards), "seed": seed.seed, "cost_usd": recorder.total(),
                **({"figure": fig_fields.get("figure_status", "")} if ws.figure else {})}
    except Exception as e:  # noqa: BLE001 — 어느 단계든 실패를 기록(07:00 send 가 관리자에게 알린다)
        _debug.warn("weekly build", f"{stage}: {type(e).__name__}: {e}")
        try:
            issue_store.transition(issue_date, "failed", error=f"{stage}: {type(e).__name__}: {e}"[:1000],
                                   notes="; ".join(notes), calls_json=json.dumps(recorder.calls),
                                   cost_usd=f"{recorder.total():.4f}")
        except TransitionError as e2:
            _debug.warn("weekly build", f"failed 기록 불가: {e2}")
        return {"status": "failed", "stage": stage, "error": f"{type(e).__name__}: {e}"}


def _default_figure_fn():
    from .figure.build import make_figure  # lazy — 이미지 트랙 켠 호만
    return make_figure


def _figure_b64_field(fig, notes: list[str]) -> dict[str, str]:
    """ready 인 PNG 를 표에 실을 b64 — 1-B 는 06:00 build 와 07:00 send 가 다른 세션(파일시스템 공유 없음)이라 경로로는 못 넘긴다.
    항목 상한(DDB 400KB)을 넘길 크기면 생략하고 notes 에만 남긴다 — 그림이 기사를 막지 않는다."""
    png = Path(fig.png or "")
    if fig.status != "ready" or not fig.png or not png.is_file():
        return {}
    b64 = base64.b64encode(png.read_bytes()).decode("ascii")
    if len(b64) > FIGURE_B64_MAX_CHARS:
        notes.append(f"그림 b64 생략({len(b64) // 1024}KB > 상한 {FIGURE_B64_MAX_CHARS // 1024}KB)")
        return {}
    return {"figure_png_b64": b64}


def _figure_bytes(item: dict) -> bytes | None:
    """③ 그림 PNG — 표의 b64(세션을 넘는다 · 1-B) 우선, 없으면 호스트 경로(옛 호 · 로컬 1-A 폴백)."""
    if item.get("figure_png_b64"):
        return base64.b64decode(item["figure_png_b64"])
    png = Path(item.get("figure_png") or "")
    return png.read_bytes() if item.get("figure_png") and png.is_file() else None


def build_raw_email(sender: str, to: str, subject: str, html: str, inline: list[tuple[str, bytes, str]]) -> bytes:
    """HTML + 인라인 이미지(CID) MIME — multipart/related. 사내 메일이 외부 이미지를 막아 첨부로 싣는다(README §4)."""
    from email.message import EmailMessage
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, sender, to
    msg.set_content("이 메일은 HTML 로 읽어 주세요.")
    msg.add_alternative(html, subtype="html")
    html_part = msg.get_payload()[-1]
    for cid, data, mime in inline:
        maintype, subtype = mime.split("/", 1)
        html_part.add_related(data, maintype, subtype, cid=f"<{cid}>", disposition="inline", filename=f"{cid}.{subtype}")
    return msg.as_bytes()


def _ses_sender(settings: Settings, ws: WeeklySettings):
    """기본 send_fn — SES SendEmail(인라인 이미지가 있으면 SendRawEmail), 발신 = 데일리 신원 + 표시 이름."""
    def _send(to: str, subject: str, html: str, inline: list[tuple[str, bytes, str]] | None = None) -> str:
        import boto3  # lazy
        ses = boto3.client("ses", region_name=settings.region)
        source = f"{ws.sender_name} <{settings.ses_sender}>"
        if inline:
            r = ses.send_raw_email(Source=source, Destinations=[to],
                                   RawMessage={"Data": build_raw_email(source, to, subject, html, inline)})
        else:
            r = ses.send_email(Source=source, Destination={"ToAddresses": [to]},
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
    html, inline = item["email_html"], []
    png_bytes = _figure_bytes(item)
    if png_bytes:                                   # 이미지 트랙: ③ 그림을 CID 인라인 이미지로(b64 우선 · 경로 폴백)
        swapped = render_email(item["issue_md"], banner=item.get("banner", ""), figure_cid="fig2")
        if "cid:fig2" in swapped:                   # ③ 에 그림 블록이 있을 때만(참조 없는 첨부 금지)
            html, inline = swapped, [("fig2", png_bytes, "image/png")]
    if dry_run:
        return {"status": "dry-run", "to": to, "subject": subject, "bytes": len(html.encode("utf-8")),
                **({"inline_png_bytes": len(inline[0][1])} if inline else {})}
    try:
        issue_store.transition(issue_date, "sending")
    except TransitionError as e:
        return {"status": "skipped", "reason": str(e)}
    try:
        mid = send_fn(to, subject, html, inline) if inline else send_fn(to, subject, html)
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
             f"- 기록: {item.get('notes', '')}", f"- 오류: {item.get('error', '')}" if item.get("error") else "",
             f"- 그림: {item.get('figure_status', '')} {item.get('figure_png', '')}" if item.get("figure_status") else "", ""]
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
