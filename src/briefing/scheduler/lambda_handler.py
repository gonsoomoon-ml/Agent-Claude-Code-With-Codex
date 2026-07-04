"""lambda_handler — ⑤ EventBridge Scheduler 가 시간당 부르는 *얇은* fire-and-return poker.

배포된 AgentCore Runtime 을 `mode=scheduled` 로 invoke → entrypoint 가 `add_async_task` 로 즉시 `accepted`
응답(브리핑은 백그라운드 ≤8h) → 이 핸들러는 그 ack 만 받고 ~2초 내 반환. **Lambda 15분과 무관**(대기 안 함).

★ boto3-only(`..core` 미import) — Lambda zip 을 최소로. SSE 파서는 invoke_runtime 의 동형 로직을 *복제*
  (core 의존 회피). 환경변수: BRIEFING_RUNTIME_ARN(필수) · BRIEFING_DRY_RUN(기본 "1"=발송 안 함, 안전).
"""
from __future__ import annotations

import json
import os
import uuid
from typing import Any


def _parse_sse(line: bytes) -> dict | None:
    """SSE `data: {...}` → dict (빈 줄·비-JSON·비-dict 는 None). invoke_runtime.parse_sse_event 동형."""
    if not line:
        return None
    try:
        text = line.decode("utf-8").strip()
    except UnicodeDecodeError:
        return None
    if text.startswith("data:"):
        text = text[len("data:"):].strip()
    if not text:
        return None
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def _build_client(region: str) -> Any:
    import boto3
    from botocore.config import Config
    # accepted ack 만 기다림(엔트리포인트가 즉시 응답). cold start 여유 110s, 재시도 0(비멱등 invoke).
    cfg = Config(connect_timeout=10, read_timeout=110, retries={"max_attempts": 0})
    return boto3.client("bedrock-agentcore", region_name=region, config=cfg)


def handler(event: Any, context: Any, *, client: Any = None) -> dict:
    """EventBridge Scheduler → invoke_agent_runtime(scheduled) → accepted 받고 반환.

    client=None 이면 boto3(운영); 테스트는 fake 주입.
    """
    arn = os.environ["BRIEFING_RUNTIME_ARN"]
    region = os.environ.get("AWS_REGION", "us-east-1")        # Lambda 가 AWS_REGION 자동 설정
    dry = os.environ.get("BRIEFING_DRY_RUN", "1").strip().lower() in ("1", "true", "yes", "on")

    ses = client or _build_client(region)
    resp = ses.invoke_agent_runtime(
        agentRuntimeArn=arn,
        qualifier="DEFAULT",
        runtimeSessionId=uuid.uuid4().hex + uuid.uuid4().hex[:1],   # ≥33자(AgentCore 제약)
        payload=json.dumps({"mode": "scheduled", "dry_run": dry}),
    )

    accepted = False
    if "text/event-stream" in resp.get("contentType", ""):
        for line in resp["response"].iter_lines(chunk_size=1):
            ev = _parse_sse(line)
            if ev and ev.get("type") == "accepted":
                accepted = True            # 브리핑은 백그라운드에서 계속; 우린 ack 만 확인
    return {"ok": True, "accepted": accepted, "dry_run": dry}
