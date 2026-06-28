#!/usr/bin/env python3
"""deploy_api.py — ④ webapi 를 Lambda + API Gateway HTTP API 로 배포 (boto3).

deploy_scheduler.py 스타일(색 단계·idempotent·.env writeback). 순서:
  [1] Lambda 실행 role(BasicExecution 만 — v1.0 무지출) · [2] zip(fastapi+mangum+pyyaml + briefing 패키지) ·
  [3] Lambda(python3.12 x86_64) · [4] HTTP API + $default(AWS_PROXY) 라우트 + Lambda 권한 · [5] .env writeback.

CORS 는 앱(CORSMiddleware)이 처리 → 게이트웨이 CorsConfiguration 미설정(이중 헤더 회피).
사용법: `uv run python -m briefing.webapi.deploy_api`
"""
from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

import boto3

from ..runtime.deploy_runtime import _upsert_env_lines
from ..shared.config import load_settings

PROJECT_ROOT = Path(__file__).resolve().parents[3]
ENV_FILE = PROJECT_ROOT / ".env"
PKG_DIR = Path(__file__).resolve().parents[1]            # src/briefing

LAMBDA_NAME = "briefing-webapi"
LAMBDA_ROLE = "briefing-webapi-lambda-role"
API_NAME = "briefing-webapi-http"
ENV_SECTION = "# ④ Briefing Web API (deploy_api.py)"
_MANAGED_BASIC = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
_G, _Y, _B, _R, _NC = "\033[0;32m", "\033[1;33m", "\033[0;34m", "\033[0;31m", "\033[0m"


def _ensure_role(iam) -> str:
    trust = {"Version": "2012-10-17", "Statement": [
        {"Effect": "Allow", "Principal": {"Service": "lambda.amazonaws.com"}, "Action": "sts:AssumeRole"}]}
    try:
        iam.create_role(RoleName=LAMBDA_ROLE, AssumeRolePolicyDocument=json.dumps(trust))
        print(f"   role 생성: {LAMBDA_ROLE}")
    except iam.exceptions.EntityAlreadyExistsException:
        print(f"   role 존재(재사용): {LAMBDA_ROLE}")
    iam.attach_role_policy(RoleName=LAMBDA_ROLE, PolicyArn=_MANAGED_BASIC)
    # v1.1 BriefingTrial inline policy — SES verify/get, InvokeAgentRuntime, DDB briefing-trials
    runtime_arn = os.getenv("BRIEFING_RUNTIME_ARN", "")
    iam.put_role_policy(RoleName=LAMBDA_ROLE, PolicyName="BriefingTrial",
        PolicyDocument=json.dumps({"Version": "2012-10-17", "Statement": [
            {"Sid": "SesVerify", "Effect": "Allow", "Action": [
                "ses:VerifyEmailIdentity", "ses:GetIdentityVerificationAttributes"], "Resource": "*"},
            {"Sid": "InvokeRuntime", "Effect": "Allow", "Action": "bedrock-agentcore:InvokeAgentRuntime",
             "Resource": [runtime_arn, runtime_arn + "/*"] if runtime_arn else "*"},
            {"Sid": "TrialsTable", "Effect": "Allow", "Action": [
                "dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem"],
             "Resource": "arn:aws:dynamodb:*:*:table/briefing-trials"}]}))
    print("   inline policy 추가: BriefingTrial")
    return iam.get_role(RoleName=LAMBDA_ROLE)["Role"]["Arn"]


def _ensure_trials_table(ddb) -> None:
    """briefing-trials DDB 테이블(PK: email, TTL: ttl) — 없으면 생성."""
    try:
        ddb.create_table(TableName="briefing-trials", BillingMode="PAY_PER_REQUEST",
            AttributeDefinitions=[{"AttributeName": "email", "AttributeType": "S"}],
            KeySchema=[{"AttributeName": "email", "KeyType": "HASH"}])
        ddb.get_waiter("table_exists").wait(TableName="briefing-trials")
        ddb.update_time_to_live(TableName="briefing-trials",
            TimeToLiveSpecification={"Enabled": True, "AttributeName": "ttl"})
        print("   DDB 테이블 생성: briefing-trials (TTL on)")
    except ddb.exceptions.ResourceInUseException:
        print("   DDB 테이블 존재(재사용): briefing-trials")


def _build_zip() -> bytes:
    """fastapi+mangum+pyyaml+boto3 설치 + briefing 패키지 복사 → zip.

    boto3 는 bedrock-agentcore 데이터플레인 클라이언트(Lambda 내장 boto3 에 없음) 때문에 포함.
    trafilatura/feedparser 는 lazy 라 미포함.
    """
    build = Path(tempfile.mkdtemp(prefix="webapi-lambda-"))
    try:
        subprocess.run(
            ["uv", "pip", "install", "--target", str(build), "fastapi", "mangum", "pyyaml", "boto3"],
            check=True, capture_output=True, text=True,
        )
        shutil.copytree(PKG_DIR, build / "briefing",
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".agentcore_build"))
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for p in sorted(build.rglob("*")):
                if p.is_file():
                    z.write(p, p.relative_to(build))
        return buf.getvalue()
    finally:
        shutil.rmtree(build, ignore_errors=True)


def _deploy_lambda(lam, role_arn, zip_bytes, settings) -> str:
    """Lambda 생성/업데이트. v1.1 — trial 관련 env 추가(BRIEFING_RUNTIME_ARN, BRIEFING_TRIALS_TABLE, SES_SENDER, 캡/쿨다운)."""
    env = {"Variables": {
        "WEB_ORIGIN": "*",
        "BRIEFING_RUNTIME_ARN": os.getenv("BRIEFING_RUNTIME_ARN", ""),
        "BRIEFING_TRIALS_TABLE": "briefing-trials",
        "SES_SENDER": settings.ses_sender,
        "TRIAL_GLOBAL_CAP": "50",   # hard cap — ⑤ 보호. 올리려면 코드 변경(고의적). env 패스스루 금지.
        "TRIAL_COOLDOWN_SECONDS": "3600",
    }}
    try:
        lam.create_function(
            FunctionName=LAMBDA_NAME, Runtime="python3.12", Architectures=["x86_64"],
            Role=role_arn, Handler="briefing.webapi.lambda_main.handler",
            Code={"ZipFile": zip_bytes}, Timeout=30, MemorySize=512, Environment=env,
        )
        print("   Lambda 생성")
    except lam.exceptions.ResourceConflictException:
        lam.update_function_code(FunctionName=LAMBDA_NAME, ZipFile=zip_bytes)
        lam.get_waiter("function_updated").wait(FunctionName=LAMBDA_NAME)
        lam.update_function_configuration(
            FunctionName=LAMBDA_NAME, Role=role_arn, Timeout=30, Environment=env)
        print("   Lambda 업데이트")
    lam.get_waiter("function_active_v2").wait(FunctionName=LAMBDA_NAME)
    return lam.get_function(FunctionName=LAMBDA_NAME)["Configuration"]["FunctionArn"]


def _ensure_http_api(api, lam, region, acct, lambda_arn) -> str:
    """HTTP API + $default(AWS_PROXY v2.0) 라우트 + Lambda invoke 권한. FastAPI 가 내부 라우팅."""
    existing = next((a for a in api.get_apis()["Items"] if a["Name"] == API_NAME), None)
    if existing:
        api_id = existing["ApiId"]
        print(f"   HTTP API 존재(재사용): {api_id}")
    else:
        api_id = api.create_api(Name=API_NAME, ProtocolType="HTTP")["ApiId"]   # CORS=앱레벨 → 게이트웨이 미설정
        print(f"   HTTP API 생성: {api_id}")
    integ_uri = f"arn:aws:apigateway:{region}:lambda:path/2015-03-31/functions/{lambda_arn}/invocations"
    integs = api.get_integrations(ApiId=api_id).get("Items", [])
    match = next((i for i in integs if i.get("IntegrationUri") == integ_uri), None)
    integ_id = match["IntegrationId"] if match else api.create_integration(
        ApiId=api_id, IntegrationType="AWS_PROXY", IntegrationUri=integ_uri,
        PayloadFormatVersion="2.0", IntegrationMethod="POST",
    )["IntegrationId"]
    # $default 라우트 1개 → 모든 경로를 Lambda 로(프레임워크 라우팅). 중복 생성은 무시.
    routes = {r["RouteKey"]: r["RouteId"] for r in api.get_routes(ApiId=api_id)["Items"]}
    if "$default" not in routes:
        api.create_route(ApiId=api_id, RouteKey="$default", Target=f"integrations/{integ_id}")
    else:
        api.update_route(ApiId=api_id, RouteId=routes["$default"], Target=f"integrations/{integ_id}")
    stages = {s["StageName"] for s in api.get_stages(ApiId=api_id)["Items"]}
    if "$default" not in stages:
        api.create_stage(ApiId=api_id, StageName="$default", AutoDeploy=True)
    try:
        lam.add_permission(
            FunctionName=LAMBDA_NAME, StatementId="apigw-invoke", Action="lambda:InvokeFunction",
            Principal="apigateway.amazonaws.com",
            SourceArn=f"arn:aws:execute-api:{region}:{acct}:{api_id}/*/*",
        )
    except lam.exceptions.ResourceConflictException:
        pass                                                 # 권한 이미 있음
    return f"https://{api_id}.execute-api.{region}.amazonaws.com"


def main() -> None:
    settings = load_settings()
    if not os.getenv("BRIEFING_RUNTIME_ARN"):
        sys.exit(f"{_R}❌ BRIEFING_RUNTIME_ARN 미설정 — deploy_runtime.py 먼저 실행{_NC}")
    region = settings.region
    acct = boto3.client("sts").get_caller_identity()["Account"]
    print(f"\n{_B}{'=' * 60}\n  ④ Web API 배포 (v1.1) — region={region}\n{'=' * 60}{_NC}\n")

    iam = boto3.client("iam")
    lam = boto3.client("lambda", region_name=region)
    api = boto3.client("apigatewayv2", region_name=region)
    ddb = boto3.client("dynamodb", region_name=region)

    print(f"{_Y}[1/5] Lambda 실행 role + BriefingTrial inline policy{_NC}")
    role_arn = _ensure_role(iam)
    time.sleep(10)                                           # IAM 전파

    print(f"{_Y}[2/5] briefing-trials DDB 테이블{_NC}")
    _ensure_trials_table(ddb)

    print(f"{_Y}[3/5] Lambda zip(fastapi+mangum+pyyaml+boto3+briefing){_NC}")
    zip_bytes = _build_zip()

    print(f"{_Y}[4/5] Lambda 함수{_NC}")
    lambda_arn = _deploy_lambda(lam, role_arn, zip_bytes, settings)

    print(f"{_Y}[5/5] HTTP API + $default 라우트{_NC}")
    api_url = _ensure_http_api(api, lam, region, acct, lambda_arn)

    text = ENV_FILE.read_text(encoding="utf-8") if ENV_FILE.exists() else ""
    ENV_FILE.write_text(_upsert_env_lines(text, {
        "BRIEFING_API_URL": api_url,
        "BRIEFING_WEBAPI_LAMBDA_NAME": LAMBDA_NAME,
        "BRIEFING_WEBAPI_LAMBDA_ROLE": LAMBDA_ROLE,
        "BRIEFING_WEBAPI_NAME": API_NAME,
    }, section=ENV_SECTION), encoding="utf-8")

    print(f"\n{_B}{'=' * 60}{_NC}\n{_G}  ④ Web API 배포 완료{_NC}")
    print(f"   라이브 검증: curl {api_url}/catalog")
    print(f"               curl {api_url}/health")
    print("   정리:        bash src/briefing/webapi/teardown_webui.sh\n")


if __name__ == "__main__":
    main()
