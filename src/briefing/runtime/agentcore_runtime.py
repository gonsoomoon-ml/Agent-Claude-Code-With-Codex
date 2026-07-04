"""AgentCore Runtime entrypoint — *얇은 어댑터*. 오케스트레이션은 `core/pipeline.run_briefing` 이 소유.

core(진실)=로직, 이 파일=배포 어댑터. `BedrockAgentCoreApp` + `@app.entrypoint`(async generator → SSE dict).
★ 호스트 무관 드라이버(`pipeline.run_briefing`)를 호출만 — entrypoint·로컬 스모크·테스트가 같은 함수 공유
  (오케스트레이션을 어댑터에 용접 + 스모크 중복 제거). 배달(SES)·QUARANTINE 행선지는 여기(어댑터) 책임.
호출 경로(U2): EventBridge Scheduler → Lambda(async) → invoke_agent_runtime.
배포: starter-toolkit `Runtime.configure(entrypoint="agentcore_runtime.py", requirements_file=...).launch(env_vars=...)`.
"""
from __future__ import annotations

from datetime import datetime, timezone

from bedrock_agentcore.runtime import BedrockAgentCoreApp

from ..core import _debug
from ..core.stores.backends import make_stores
from ..core.config import list_users, load_settings, load_user
from ..core.pipeline import run_briefing
from ._smoke import harness_fns, smoke_fns, smoke_users

app = BedrockAgentCoreApp()


@app.entrypoint
async def briefing_entrypoint(payload, context):
    """매일 1회: `run_briefing`(host-agnostic) 실행 → 사용자별 결과를 dict 로 yield(SSE).

    payload:
      - `mode`: "real"(기본) | "smoke" | "harness".
        · smoke   = ②a plumbing 검증 — 전부 fake(claude/codex/네트워크 0) + 합성 사용자.
        · harness = ②b — **fetch 만 fake, draft/verify 는 진짜 claude·codex**(합성 source 로 CLI 실행만 격리 검증).
        · real    = 진짜 RSS fetch + 진짜 claude·codex(실 사용자 — fragile 출처는 ① 필요).
      - `users`: [id,...]?(real 기본=전체) · `window_hours`: 24? · `run_date`: "YYYY-MM-DD"?(미지정 시 UTC 오늘)
    ★ gate/certifier 는 user-blind(trust 경계). DEBUG=1 시 trace=stderr→CloudWatch(SSE 와 분리).
    """
    settings = load_settings()
    store, card_cache, ledger = make_stores(settings)  # backend(local|dynamo) 일관 선택(③)
    window_hours = int(payload.get("window_hours", 24))
    # run_date = 이 run 의 논리 날짜(ledger 시간 인덱스). 호스트 경계라 시계 읽기 허용; payload override(replay).
    run_date = payload.get("run_date") or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    mode = payload.get("mode", "real")

    if mode == "scheduled":   # ⑤ — fire-and-forget async: 즉시 accepted, 브리핑은 백그라운드(≤8h)
        import threading

        from ..scheduler.deliver import make_ses_deliver
        from ..scheduler.dispatch import dispatch
        from ..scheduler.sent_log import DynamoSentLog
        s_users = [load_user(uid, settings) for uid in (payload.get("users") or list_users(settings))]
        now = (datetime.fromisoformat(payload["now_utc"]) if payload.get("now_utc")
               else datetime.now(timezone.utc))
        rd = payload.get("run_date") or now.strftime("%Y-%m-%d")
        dry = bool(payload.get("dry_run"))
        deliver_fn = (lambda b: None) if dry else make_ses_deliver(settings)
        sent = None if dry else DynamoSentLog.from_settings(settings)
        task_id = app.add_async_task("scheduled_briefing")    # 세션 HealthyBusy 유지(≤8h)

        def _bg():
            try:
                dispatch(settings, store, s_users, now, deliver_fn=deliver_fn, run_date=rd,
                         card_cache=card_cache, ledger=ledger, sent_log=sent)
            except Exception as e:  # noqa: BLE001 — 백그라운드 실패는 보수적으로 로깅(이미 accepted 반환)
                _debug.warn("scheduled bg", f"{type(e).__name__}: {e}")
            finally:
                app.complete_async_task(task_id)

        threading.Thread(target=_bg, daemon=True).start()
        _debug.dprint("entrypoint", f"scheduled accepted · users={len(s_users)} · now={now.isoformat()} · dry={dry}")
        yield {"type": "accepted", "mode": "scheduled", "task_id": task_id,
               "users": len(s_users), "now_utc": now.isoformat(), "dry_run": dry}
        return

    if mode == "trial":   # v1.1a — 검증 polling → 검증 후 발행 1통(fire-and-forget)
        import threading
        import time as _time

        import boto3

        from ..scheduler.deliver import make_ses_deliver
        from ._trial import run_trial

        email = payload["email"]
        rd = payload.get("run_date") or run_date
        dry = bool(payload.get("dry_run"))
        deliver_fn = (lambda b: None) if dry else make_ses_deliver(settings, subject="브리핑 체험 (검증 후 발행)")
        fallback_fn = (lambda e: None) if dry else (lambda e: _send_trial_fallback(settings, e))
        ses = boto3.client("ses", region_name=settings.region)
        # briefing-trials 상태 기록 — Key=email, SET #s=status(reserved word 우회)
        trials = boto3.resource("dynamodb", region_name=settings.region).Table("briefing-trials")

        def _status(s, p=None):
            """trial 상태를 briefing-trials 에 기록. dry_run 시 no-op; 실패 시 발송 차단 안 함(swallow)."""
            if dry:
                return
            names = {"#s": "status"}
            vals = {":s": s}
            expr = "SET #s = :s"
            if p is not None:
                expr += ", published = :p"
                vals[":p"] = p
            try:
                trials.update_item(Key={"email": email}, UpdateExpression=expr,
                                   ExpressionAttributeNames=names, ExpressionAttributeValues=vals)
            except Exception as e:  # noqa: BLE001 — 상태 기록 실패가 발송을 막지 않게
                _debug.warn("trial status", f"{type(e).__name__}: {e}")

        task_id = app.add_async_task("trial_briefing")

        def _bg():
            try:
                msg = run_trial(settings, store, card_cache, payload, ses=ses,
                                run_briefing_fn=run_briefing, deliver_fn=deliver_fn,
                                fallback_fn=fallback_fn, sleep_fn=_time.sleep, run_date=rd,
                                attempts=int(payload.get("poll_max", 45)),
                                sleep_seconds=int(payload.get("poll_seconds", 20)), status_fn=_status)
                _debug.dprint("entrypoint ← trial", msg, "green")
            except Exception as e:  # noqa: BLE001
                _status("failed")
                _debug.warn("trial bg", f"{type(e).__name__}: {e}")
            finally:
                app.complete_async_task(task_id)

        threading.Thread(target=_bg, daemon=True).start()
        _debug.dprint("entrypoint", f"trial accepted · {email} · dry={dry}")
        yield {"type": "accepted", "mode": "trial", "task_id": task_id, "email": email, "dry_run": dry}
        return

    if mode == "smoke":
        users, fns = smoke_users(settings), smoke_fns()      # 전부 fake — plumbing 만 증명
    elif mode == "harness":
        users, fns = smoke_users(settings), harness_fns()    # fetch 만 fake → 진짜 claude+codex 실행 검증
    else:  # real
        users = [load_user(uid, settings) for uid in (payload.get("users") or list_users(settings))]
        fns = {}   # None 기본 = 실제 claude -p author + codex certifier
        if settings.gateway_enabled:   # ① 승격: retrieval 을 Gateway MCP 로(opt-in; off 면 직접 — 현 기본)
            from ..core.retrieval.gateway_client import gateway_fetch_factory
            fns["fetch_article_fn"] = gateway_fetch_factory(settings)

    # ★ 테스트 모드(smoke/harness)는 card_cache/ledger 우회 — 캐시-hit 으로 harness 의 진짜 CLI 실행이 가려지는 것
    #   + production 원장(③) 오염 방지. store 는 content-addressed 라 그대로 사용(무해).
    test_mode = mode in ("smoke", "harness")

    _debug.dprint("entrypoint",
                  f"mode={mode} · backend={settings.backend} · users={len(users)} · run_date={run_date}")
    yield {"type": "stage", "stage": "run_briefing", "mode": mode, "users": len(users),
           "backend": settings.backend, "run_date": run_date}
    for b in run_briefing(settings, store, users, window_hours=window_hours,
                          card_cache=None if test_mode else card_cache,
                          ledger=None if test_mode else ledger,
                          run_date=run_date, **fns):
        # TODO(deliver): SES send(b.recipient, b.email) · QUARANTINE → 사람-검토 큐(별도 행선지).
        _debug.dprint("entrypoint ← briefing",
                      f"{b.user_id}: published={b.published} quarantined={b.quarantined}",
                      "green" if b.published else "yellow")
        yield {
            "type": "user", "user": b.user_id, "recipient": b.recipient,
            "published": b.published, "quarantined": b.quarantined, "bytes": len(b.email),
        }
    yield {"type": "workflow_complete"}


def _send_trial_fallback(settings, recipient: str) -> None:
    """published==0(QUARANTINE-only/빈/에러) — 침묵 대신 안내 메일 1통."""
    import boto3
    html = ('<div style="font-family:system-ui;max-width:560px;margin:0 auto;padding:16px">'
            '<h2>체험 브리핑 준비 중 문제가 있었어요</h2>'
            '<p>오늘은 검증을 통과한 새 소식이 충분하지 않았습니다. 구독하시면 매일 자동으로 다시 시도합니다.</p></div>')
    boto3.client("ses", region_name=settings.region).send_email(
        Source=settings.ses_sender, Destination={"ToAddresses": [recipient]},
        Message={"Subject": {"Data": "브리핑 체험 — 잠시 후 다시"},
                 "Body": {"Html": {"Data": html}}})


if __name__ == "__main__":
    app.run()
