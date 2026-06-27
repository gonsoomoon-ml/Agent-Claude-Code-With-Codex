"""AgentCore Runtime entrypoint — *얇은 어댑터*. 오케스트레이션은 `shared/pipeline.run_briefing` 이 소유.

shared(진실)=로직, 이 파일=배포 어댑터. `BedrockAgentCoreApp` + `@app.entrypoint`(async generator → SSE dict).
★ 호스트 무관 드라이버(`pipeline.run_briefing`)를 호출만 — entrypoint·로컬 스모크·테스트가 같은 함수 공유
  (오케스트레이션을 어댑터에 용접 + 스모크 중복 제거). 배달(SES)·QUARANTINE 행선지는 여기(어댑터) 책임.
호출 경로(U2): EventBridge Scheduler → Lambda(async) → invoke_agent_runtime.
배포: starter-toolkit `Runtime.configure(entrypoint="agentcore_runtime.py", requirements_file=...).launch(env_vars=...)`.
"""
from __future__ import annotations

from bedrock_agentcore.runtime import BedrockAgentCoreApp

from ..shared import _debug
from ..shared.config import list_users, load_settings, load_user
from ..shared.pipeline import run_briefing
from ..shared.source_store import SourceStore
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
      - `users`: [id,...]?(real 기본=전체) · `window_hours`: 24?
    ★ gate/certifier 는 user-blind(trust 경계). DEBUG=1 시 trace=stderr→CloudWatch(SSE 와 분리).
    """
    settings = load_settings()
    store = SourceStore(settings.source_store_path)
    window_hours = int(payload.get("window_hours", 24))
    mode = payload.get("mode", "real")

    if mode == "smoke":
        users, fns = smoke_users(settings), smoke_fns()      # 전부 fake — plumbing 만 증명
    elif mode == "harness":
        users, fns = smoke_users(settings), harness_fns()    # fetch 만 fake → 진짜 claude+codex 실행 검증
    else:  # real
        users = [load_user(uid, settings) for uid in (payload.get("users") or list_users(settings))]
        fns = {}   # None 기본 = 실제 claude -p author + codex certifier

    _debug.dprint("entrypoint", f"mode={mode} · users={len(users)} · window_hours={window_hours}")
    yield {"type": "stage", "stage": "run_briefing", "mode": mode, "users": len(users)}
    for b in run_briefing(settings, store, users, window_hours=window_hours, **fns):
        # TODO(deliver): SES send(b.recipient, b.email) · QUARANTINE → 사람-검토 큐(별도 행선지).
        _debug.dprint("entrypoint ← briefing",
                      f"{b.user_id}: published={b.published} quarantined={b.quarantined}",
                      "green" if b.published else "yellow")
        yield {
            "type": "user", "user": b.user_id, "recipient": b.recipient,
            "published": b.published, "quarantined": b.quarantined, "bytes": len(b.email),
        }
    yield {"type": "workflow_complete"}


if __name__ == "__main__":
    app.run()
