"""deploy_gateway — ① Gateway 승격 실 배포(재현 가능). aiops cognito.yaml+setup_gateway.py+deploy_runtime.py 미러.

재현 절차(누구든): AWS creds + `uv sync` (docker 불필요) →
    AWS_REGION=us-east-1 DEMO_USER=<id> uv run python -m briefing.runtime.deploy_gateway
생성물(순서·전부 멱등): Cognito(CFN) → zip Lambda(S3) → OAuth2 provider(비밀=볼트) → Gateway + target(3도구).
출력: .env 에 붙일 GATEWAY_URL/COGNITO_*/OAUTH_PROVIDER_NAME. (실행=과금 — off-by-default capability.)

★ Lambda = **zip**(aiops 동일). lxml/trafilatura 는 네이티브 wheel(이 박스 = Lambda 플랫폼: linux x86_64 py3.12,
  lxml glibc≤2.25 ⊂ AL2023 2.34) → docker 없이 빌드. boto3 는 Lambda 런타임 기본 제공 → 미번들.
guardrail: toolSchema = retrieval 3도구뿐(fetch_article·get_source·discover_feed) — gate/certify/author 미노출.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import boto3

ROOT = Path(__file__).resolve().parents[3]          # repo 루트(src/briefing/runtime/ → parents[3])
REGION = os.getenv("AWS_REGION", "us-east-1")
DEMO_USER = os.getenv("DEMO_USER", "gonsoo")
STACK = f"briefing-gw-{DEMO_USER}-cognito"
LAMBDA_NAME = f"briefing-gw-{DEMO_USER}-handler"     # cognito.yaml LambdaName 파라미터로 전달(역할 invoke 대상)
GATEWAY_NAME = f"briefing-gw-{DEMO_USER}-gateway"
PROVIDER_NAME = f"briefing_gw_{DEMO_USER}_provider"  # AgentCore Identity provider(언더스코어)
TARGET_NAME = "briefing"                             # MCP 도구 prefix → config GATEWAY_TARGET 기본과 일치
BUILD_DIR = ROOT / ".gw_build"                       # gitignore — zip 빌드 산출물
ZIP_PATH = ROOT / ".gw_build.zip"

# ── toolSchema(inlinePayload): 승격 retrieval 3도구뿐 ── guardrail: 여기에 gate/certify/author 없음 ──
TOOL_SCHEMA = [
    {"name": "fetch_article",
     "description": "Vetted catalog 출처에서 최근 기사 raw 페치(fabric 권위 페치). 내부 source_key 로 호출.",
     "inputSchema": {"type": "object", "required": ["source_key"],
                     "properties": {"source_key": {"type": "string", "description": "sources.CATALOG 키"},
                                    "window_hours": {"type": "integer", "description": "최근 N시간(기본 24)"}}}},
    {"name": "get_source",
     "description": "content-addressed source-of-record 재열람(read-only). source_id=sha256.",
     "inputSchema": {"type": "object", "required": ["source_id"],
                     "properties": {"source_id": {"type": "string"}}}},
    {"name": "discover_feed",
     "description": "사이트 URL 의 RSS/Atom 피드 발견(비권위 보조).",
     "inputSchema": {"type": "object", "required": ["url"],
                     "properties": {"url": {"type": "string"}}}},
]


def _account() -> str:
    return boto3.client("sts").get_caller_identity()["Account"]


def _cfn() -> dict[str, str]:
    """cognito.yaml 배포(Cognito + IAM). 멱등: 존재 시 update(‘No updates’ 무시)."""
    cf = boto3.client("cloudformation", region_name=REGION)
    tmpl = (ROOT / "infra/gateway/cognito.yaml").read_text(encoding="utf-8")
    params = [{"ParameterKey": "DemoUser", "ParameterValue": DEMO_USER},
              {"ParameterKey": "LambdaName", "ParameterValue": LAMBDA_NAME}]
    kw = dict(StackName=STACK, TemplateBody=tmpl, Capabilities=["CAPABILITY_NAMED_IAM"], Parameters=params)
    try:
        cf.create_stack(**kw)
        print(f"⏳ CFN create: {STACK}")
        cf.get_waiter("stack_create_complete").wait(StackName=STACK)
    except cf.exceptions.AlreadyExistsException:
        try:
            cf.update_stack(**kw)
            cf.get_waiter("stack_update_complete").wait(StackName=STACK)
            print(f"♻ CFN update: {STACK}")
        except Exception as e:  # noqa: BLE001 — "No updates are to be performed" = 정상
            if "No updates" not in str(e):
                raise
            print(f"♻ CFN 변경 없음: {STACK}")
    out = {o["OutputKey"]: o["OutputValue"]
           for o in cf.describe_stacks(StackName=STACK)["Stacks"][0]["Outputs"]}
    print(f"✅ Cognito+IAM: pool={out['UserPoolId']}")
    return out


def _client_secret(pool_id: str, client_id: str) -> str:
    """ClientSecret 는 CFN output 이 아님 → describe 로 별도 조회(aiops 동일)."""
    return boto3.client("cognito-idp", region_name=REGION).describe_user_pool_client(
        UserPoolId=pool_id, ClientId=client_id)["UserPoolClient"]["ClientSecret"]


def _build_zip(account: str) -> tuple[str, str]:
    """Lambda zip 빌드(docker 없이): 네이티브 wheel(이 박스=Lambda 플랫폼) + briefing 소스 → S3.

    boto3 는 Lambda 기본 제공이라 제외. lxml/trafilatura 는 manylinux wheel(glibc≤2.25, AL2023 OK).
    """
    if BUILD_DIR.exists():
        shutil.rmtree(BUILD_DIR)
    BUILD_DIR.mkdir()
    subprocess.run(["uv", "pip", "install", "--target", str(BUILD_DIR),
                    "pyyaml", "feedparser", "trafilatura"], check=True)
    shutil.copytree(ROOT / "src/briefing", BUILD_DIR / "briefing",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    if ZIP_PATH.exists():
        ZIP_PATH.unlink()
    shutil.make_archive(str(ZIP_PATH.with_suffix("")), "zip", BUILD_DIR)
    bucket = f"briefing-gw-{DEMO_USER}-deploy-{account}-{REGION}"
    s3 = boto3.client("s3", region_name=REGION)
    try:
        if REGION == "us-east-1":          # us-east-1 은 LocationConstraint 금지
            s3.create_bucket(Bucket=bucket)
        else:
            s3.create_bucket(Bucket=bucket, CreateBucketConfiguration={"LocationConstraint": REGION})
    except Exception as e:  # noqa: BLE001 — 이미 소유 버킷이면 멱등 진행
        if not any(x in type(e).__name__ for x in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists")):
            raise
    key = "gateway/handler.zip"
    s3.upload_file(str(ZIP_PATH), bucket, key)
    print(f"✅ zip → s3://{bucket}/{key} ({ZIP_PATH.stat().st_size // (1024 * 1024)}MB)")
    return bucket, key


def _lambda(bucket: str, key: str, role_arn: str) -> str:
    """zip Lambda 생성/갱신(S3 코드). env=DDB backend(get_source). AWS_REGION 은 Lambda 자동 주입."""
    lam = boto3.client("lambda", region_name=REGION)
    env = {"Variables": {"BACKEND": "dynamo", "SOURCE_TABLE": "briefing-source-store"}}
    common = dict(FunctionName=LAMBDA_NAME, Runtime="python3.12", Role=role_arn,
                  Handler="briefing.runtime.gateway_handler.lambda_handler",
                  Timeout=120, MemorySize=512, Environment=env)
    try:
        lam.create_function(Code={"S3Bucket": bucket, "S3Key": key}, **common)
        print(f"⏳ Lambda create(zip): {LAMBDA_NAME}")
    except lam.exceptions.ResourceConflictException:
        lam.update_function_code(FunctionName=LAMBDA_NAME, S3Bucket=bucket, S3Key=key)
        print(f"♻ Lambda update(zip): {LAMBDA_NAME}")
    lam.get_waiter("function_active_v2").wait(FunctionName=LAMBDA_NAME)
    arn = lam.get_function(FunctionName=LAMBDA_NAME)["Configuration"]["FunctionArn"]
    print(f"✅ Lambda active: {arn}")
    return arn


def _provider(pool_id: str, domain: str, client_id: str, client_secret: str) -> str:
    """OAuth2CredentialProvider(CustomOauth2) — 비밀=AgentCore 볼트. Runtime 은 비밀 없이 토큰."""
    c = boto3.client("bedrock-agentcore-control", region_name=REGION)
    cfg = {"customOauth2ProviderConfig": {
        "clientId": client_id, "clientSecret": client_secret,
        "oauthDiscovery": {"authorizationServerMetadata": {
            "issuer": f"https://cognito-idp.{REGION}.amazonaws.com/{pool_id}",
            "authorizationEndpoint": f"https://{domain}.auth.{REGION}.amazoncognito.com/oauth2/authorize",
            "tokenEndpoint": f"https://{domain}.auth.{REGION}.amazoncognito.com/oauth2/token",
            "responseTypes": ["token"]}}}}
    try:
        c.create_oauth2_credential_provider(name=PROVIDER_NAME, credentialProviderVendor="CustomOauth2",
                                            oauth2ProviderConfigInput=cfg)
        print(f"✅ OAuth2 provider: {PROVIDER_NAME}")
    except Exception as e:  # noqa: BLE001 — 멱등(ConflictException / "already exists")
        if "Conflict" in type(e).__name__ or "already exists" in str(e):
            print(f"♻ OAuth2 provider 존재: {PROVIDER_NAME}")
        else:
            raise
    return PROVIDER_NAME


def _gateway(role_arn: str, pool_id: str, client_id: str, scope: str, lambda_arn: str) -> str:
    """Gateway(MCP·CUSTOM_JWT) + target(mcp.lambda·3도구·GATEWAY_IAM_ROLE). READY 대기 후 target."""
    c = boto3.client("bedrock-agentcore-control", region_name=REGION)
    existing = next((g for g in c.list_gateways().get("items", []) if g.get("name") == GATEWAY_NAME), None)
    if existing:
        gw = c.get_gateway(gatewayIdentifier=existing["gatewayId"])
        print(f"♻ Gateway 존재: {gw['gatewayId']}")
    else:
        disc = f"https://cognito-idp.{REGION}.amazonaws.com/{pool_id}/.well-known/openid-configuration"
        gw = c.create_gateway(name=GATEWAY_NAME, roleArn=role_arn, protocolType="MCP",
                              authorizerType="CUSTOM_JWT",
                              authorizerConfiguration={"customJWTAuthorizer": {
                                  "discoveryUrl": disc, "allowedClients": [client_id], "allowedScopes": [scope]}})
        print(f"⏳ Gateway create: {gw['gatewayId']}")
    gid = gw["gatewayId"]
    for _ in range(30):                                  # READY 대기(타깃 추가 전 — 필수)
        st = c.get_gateway(gatewayIdentifier=gid).get("status")
        if st == "READY":
            break
        if st in ("FAILED", "DELETING", "DELETED"):
            sys.exit(f"❌ Gateway 상태 {st}")
        time.sleep(3)
    tcfg = {"mcp": {"lambda": {"lambdaArn": lambda_arn, "toolSchema": {"inlinePayload": TOOL_SCHEMA}}}}
    cred = [{"credentialProviderType": "GATEWAY_IAM_ROLE"}]
    et = next((t for t in c.list_gateway_targets(gatewayIdentifier=gid).get("items", [])
               if t.get("name") == TARGET_NAME), None)
    if et:
        c.update_gateway_target(gatewayIdentifier=gid, targetId=et["targetId"], name=TARGET_NAME,
                                targetConfiguration=tcfg, credentialProviderConfigurations=cred)
        print(f"♻ Target update: {TARGET_NAME} (3 tools)")
    else:
        c.create_gateway_target(gatewayIdentifier=gid, name=TARGET_NAME,
                                targetConfiguration=tcfg, credentialProviderConfigurations=cred)
        print(f"✅ Target create: {TARGET_NAME} (3 tools)")
    return gw["gatewayUrl"]


def main() -> None:
    account = _account()
    print(f"▶ deploy_gateway · region={REGION} · user={DEMO_USER} · account={account}\n")
    out = _cfn()
    secret = _client_secret(out["UserPoolId"], out["ClientId"])
    bucket, key = _build_zip(account)
    lambda_arn = _lambda(bucket, key, out["LambdaExecRoleArn"])
    provider = _provider(out["UserPoolId"], out["Domain"], out["ClientId"], secret)
    url = _gateway(out["GatewayIamRoleArn"], out["UserPoolId"], out["ClientId"], out["Scope"], lambda_arn)
    token_url = f"https://{out['Domain']}.auth.{REGION}.amazoncognito.com/oauth2/token"
    print("\n=== ✅ 완료 — .env 에 추가(켜려면 GATEWAY_ENABLED=1) ===")
    print(f"GATEWAY_URL={url}")
    print(f"GATEWAY_TARGET={TARGET_NAME}")
    print(f"COGNITO_SCOPE={out['Scope']}")
    print(f"OAUTH_PROVIDER_NAME={provider}     # Runtime: 비밀 없이 볼트 토큰")
    print(f"COGNITO_TOKEN_URL={token_url}       # 로컬 직접 발급용")
    print(f"COGNITO_CLIENT_ID={out['ClientId']}")
    print("# COGNITO_CLIENT_SECRET=<describe 로 조회 — .env/로컬 전용, 커밋 금지>")


if __name__ == "__main__":
    main()
