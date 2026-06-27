"""AgentCore Runtime entrypoint — *얇은 어댑터*. 오케스트레이션은 `shared/pipeline.run_briefing` 이 소유.

shared(진실)=로직, 이 파일=배포 어댑터. `BedrockAgentCoreApp` + `@app.entrypoint`(async generator → SSE dict).
★ 호스트 무관 드라이버(`pipeline.run_briefing`)를 호출만 — entrypoint·로컬 스모크·테스트가 같은 함수 공유
  (오케스트레이션을 어댑터에 용접 + 스모크 중복 제거). 배달(SES)·QUARANTINE 행선지는 여기(어댑터) 책임.
호출 경로(U2): EventBridge Scheduler → Lambda(async) → invoke_agent_runtime.
배포: starter-toolkit `Runtime.configure(entrypoint="agentcore_runtime.py", requirements_file=...).launch(env_vars=...)`.
"""
from __future__ import annotations

from datetime import datetime, timezone

from bedrock_agentcore.runtime import BedrockAgentCoreApp

from ..shared.backends import make_stores
from ..shared.config import list_users, load_settings, load_user
from ..shared.pipeline import run_briefing

app = BedrockAgentCoreApp()


@app.entrypoint
async def briefing_entrypoint(payload, context):
    """매일 1회: `run_briefing`(host-agnostic) 실행 → 사용자별 결과를 dict 로 yield(SSE).

    payload: {"users": [id,...]?(기본=전체), "window_hours": 24?}. ★ gate/certifier 는 user-blind(trust 경계).
    """
    settings = load_settings()
    store, card_cache, ledger = make_stores(settings)  # backend(local|dynamo) 일관 선택
    window_hours = int(payload.get("window_hours", 24))
    # run_date = 이 run 의 논리 날짜(ledger 시간 인덱스). 호스트 경계라 시계 읽기 허용; payload 로 override 가능(replay).
    run_date = payload.get("run_date") or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    users = [load_user(uid, settings) for uid in (payload.get("users") or list_users(settings))]

    yield {"type": "stage", "stage": "run_briefing", "users": len(users),
           "backend": settings.backend, "run_date": run_date}
    for b in run_briefing(settings, store, users, window_hours=window_hours,
                          card_cache=card_cache, ledger=ledger, run_date=run_date):
        # TODO(deliver): SES send(b.recipient, b.email) · QUARANTINE → 사람-검토 큐(별도 행선지).
        yield {
            "type": "user", "user": b.user_id, "recipient": b.recipient,
            "published": b.published, "quarantined": b.quarantined, "bytes": len(b.email),
        }
    yield {"type": "workflow_complete"}


if __name__ == "__main__":
    app.run()
