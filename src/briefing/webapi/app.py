"""FastAPI 앱 — ④ Web UI public API. v1.0: GET /catalog·/sample·/health(무지출).

CORS 는 앱 레벨(CORSMiddleware) — 배포(Mangum→HTTP API)·로컬(uvicorn) 공통 + preflight 처리.
v1.0 allow_origins=* (public GET); v1.1+ env WEB_ORIGIN 로 CloudFront 도메인 좁힘.
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from .catalog import build_catalog
from .trial import TrialStore, handle_trial

_SAMPLE_HTML = (Path(__file__).parent / "sample_briefing.html").read_text(encoding="utf-8")

app = FastAPI(title="Briefing Web API", version="1.0.0")

_origins = [o.strip() for o in os.getenv("WEB_ORIGIN", "*").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins or ["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


@app.get("/catalog")
def get_catalog() -> dict:
    """폼용 카탈로그(출처 그룹·시각·상한). 무지출 — CATALOG/LENS_LIBRARY 메모리 읽기."""
    return build_catalog()


@app.get("/sample")
def get_sample() -> Response:
    """랜딩 미리보기용 정적 샘플 브리핑 HTML."""
    return Response(content=_SAMPLE_HTML, media_type="text/html; charset=utf-8")


@app.get("/health")
def health() -> dict:
    return {"ok": True}


def _trial_deps() -> dict:
    """실 boto3 의존성(운영). 테스트는 monkeypatch 로 fake 주입."""
    import boto3
    region = os.getenv("AWS_REGION", "us-east-1")
    table = boto3.resource("dynamodb", region_name=region).Table(
        os.getenv("BRIEFING_TRIALS_TABLE", "briefing-trials"))
    ses = boto3.client("ses", region_name=region)
    arn = os.environ["BRIEFING_RUNTIME_ARN"]
    agentcore = boto3.client("bedrock-agentcore", region_name=region)

    def runtime_invoke(mode: str, p: dict) -> None:
        import json
        import uuid
        agentcore.invoke_agent_runtime(
            agentRuntimeArn=arn, qualifier="DEFAULT",
            runtimeSessionId=uuid.uuid4().hex + uuid.uuid4().hex[:1],
            payload=json.dumps(p))

    return {"store": TrialStore(table), "ses": ses, "runtime_invoke": runtime_invoke,
            "sender": os.getenv("SES_SENDER", ""), "cap": int(os.getenv("TRIAL_GLOBAL_CAP", "50")),
            "cooldown_s": int(os.getenv("TRIAL_COOLDOWN_SECONDS", "3600"))}


@app.post("/trial")
async def post_trial(req: Request):
    from datetime import datetime, timezone
    from fastapi.responses import JSONResponse
    payload = await req.json()
    d = _trial_deps()
    now = datetime.now(timezone.utc)
    keys = [s["key"] for g in build_catalog()["categories"] for s in g["sources"]]
    code, body = handle_trial(
        payload, store=d["store"], ses=d["ses"], runtime_invoke=d["runtime_invoke"],
        cap=d["cap"], cooldown_s=d["cooldown_s"],
        today=now.strftime("%Y-%m-%d"), catalog_keys=keys)
    return JSONResponse(status_code=code, content=body)
