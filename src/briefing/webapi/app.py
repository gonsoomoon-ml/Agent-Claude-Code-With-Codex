"""FastAPI 앱 — ④ Web UI public API. v1.0: GET /catalog·/sample·/health(무지출).

CORS 는 앱 레벨(CORSMiddleware) — 배포(Mangum→HTTP API)·로컬(uvicorn) 공통 + preflight 처리.
v1.0 allow_origins=* (public GET); v1.1+ env WEB_ORIGIN 로 CloudFront 도메인 좁힘.
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .authz import claims_from_request
from .catalog import DEPTHS, SEND_HOURS, build_catalog
from .policy import max_sources
from .profile import validate_profile
from .trial import TrialStore, handle_trial, _parse_emails

_SAMPLE_HTML = (Path(__file__).parent / "sample_briefing.html").read_text(encoding="utf-8")

app = FastAPI(title="Briefing Web API", version="1.0.0")

_origins = [o.strip() for o in os.getenv("WEB_ORIGIN", "*").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins or ["*"],
    allow_methods=["GET", "POST", "PUT", "OPTIONS"],
    allow_headers=["*", "Authorization"],
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


def _profile_deps() -> dict:
    """실 boto3 의존성(운영). 테스트는 monkeypatch 로 fake 주입."""
    import boto3
    region = os.getenv("AWS_REGION", "us-east-1")
    from ..core.config import load_settings
    from ..core.stores.dynamo import user_store_from_settings
    store = user_store_from_settings(load_settings())
    ses = boto3.client("ses", region_name=region)
    cat = build_catalog()
    return {"store": store, "ses": ses, "sender": os.getenv("SES_SENDER", ""),
            "keys": [s["key"] for g in cat["categories"] for s in g["sources"]],
            "lenses": [ln["key"] for ln in cat["lenses"]]}


def _ensure_ses(ses, email: str) -> str:
    """trial 패턴 재사용 — SES 미검증이면 verify 트리거. active|verification_pending."""
    if ses is None:  # 테스트 모드
        return "active"
    attrs = ses.get_identity_verification_attributes(Identities=[email])
    st = attrs.get("VerificationAttributes", {}).get(email, {}).get("VerificationStatus")
    if st == "Success":
        return "active"
    ses.verify_email_identity(EmailAddress=email)
    return "verification_pending"


@app.get("/profile")
def get_profile(req: Request) -> dict:
    """구독 프로필 조회(prefill). JWT claims 로 sub 확인 후 store 에서 사용자 레코드 조회."""
    cl = claims_from_request(req)
    rec = _profile_deps()["store"].get_user(cl["sub"])
    return {"subscribed": rec is not None, "recipient": cl["email"], "profile": rec or {},
            "max_sources": max_sources(cl["is_admin"])}


@app.put("/profile")
async def put_profile(req: Request):
    """구독 프로필 저장. JWT claims 로 sub·email 취득(body 무시), 6 선호 필드 검증 후 저장."""
    cl = claims_from_request(req)
    body = await req.json()
    d = _profile_deps()
    err = validate_profile(body, catalog_keys=d["keys"], lens_keys=d["lenses"],
                           depths=DEPTHS, send_hours=SEND_HOURS,
                           max_sources=max_sources(cl["is_admin"]))
    if err:
        return JSONResponse(status_code=400, content={"error": err})
    d["store"].update_profile_from_jwt(sub=cl["sub"], email=cl["email"], fields=body)
    return JSONResponse(status_code=200,
                        content={"status": "subscribed", "delivery": _ensure_ses(d["ses"], cl["email"])})


def _status_store() -> TrialStore:
    """trial 상태 조회용 lazy 의존성. 테스트는 monkeypatch 로 fake 주입."""
    import boto3
    region = os.getenv("AWS_REGION", "us-east-1")
    table = boto3.resource("dynamodb", region_name=region).Table(
        os.getenv("BRIEFING_TRIALS_TABLE", "briefing-trials"))
    return TrialStore(table)


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
            "cooldown_s": int(os.getenv("TRIAL_COOLDOWN_SECONDS", "3600")),
            "test_emails": _parse_emails(os.getenv("TRIAL_TEST_EMAILS", ""))}


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
        today=now.strftime("%Y-%m-%d"), catalog_keys=keys,
        test_emails=d["test_emails"])
    return JSONResponse(status_code=code, content=body)


@app.get("/trial/status")
def trial_status(email: str):
    """trial 상태 조회(폴링). JWT 불필요(public). I1: 이메일 소문자화(DDB 키 대소문자 매칭)."""
    import re
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email or ""):
        return JSONResponse(status_code=400, content={"error": "유효한 이메일이 아닙니다."})
    email = (email or "").strip().lower()
    return _status_store().get_status(email)


from .admin import router as admin_router  # noqa: E402
app.include_router(admin_router)
