"""deploy_gateway — ① Gateway 승격을 실제로 배포하는 스크립트(재현 가능). aiops 의 cognito.yaml + setup_gateway.py + deploy_runtime.py 를 합쳐 미러.

누구든 재현하려면(docker 불필요):
    AWS 자격증명 + `uv sync` → AWS_REGION=us-east-1 DEMO_USER=<id> uv run python -m briefing.runtime.deploy_gateway

아래 순서로 만든다(전부 멱등 — 재실행해도 안전):
    Cognito + IAM(CloudFormation) → zip Lambda(S3 경유) → OAuth2 provider(비밀=볼트) → Gateway + target(3도구).
끝나면 `.env` 에 붙일 값(GATEWAY_URL·COGNITO_*·OAUTH_PROVIDER_NAME)을 출력한다. (실행은 과금된다 — 이 기능은 기본 off.)

★ Lambda 는 컨테이너가 아니라 **zip** 이다(aiops 와 동일). lxml/trafilatura 는 네이티브 wheel 로 묶는다 —
  이 빌드 호스트가 Lambda 와 같은 플랫폼(linux x86_64, py3.12)이고 lxml 의 glibc 요구(≤2.25)가 Lambda(AL2023, 2.34)에 포함되므로 docker 없이 빌드된다.
  boto3 는 Lambda 런타임이 기본 제공하므로 zip 에 넣지 않는다.
가드레일: toolSchema = retrieval 3도구(fetch_article·get_source·discover_feed)뿐 — gate/certify/author 는 노출하지 않는다.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import boto3

ROOT = Path(__file__).resolve().parents[3]          # 저장소 루트 — 이 파일이 src/briefing/runtime/ 안이라 3단계 위
REGION = os.getenv("AWS_REGION", "us-east-1")
DEMO_USER = os.getenv("DEMO_USER", "gonsoo")
STACK = f"briefing-gw-{DEMO_USER}-cognito"
LAMBDA_NAME = f"briefing-gw-{DEMO_USER}-handler"     # cognito.yaml 의 LambdaName 으로 넘긴다(Gateway 역할이 invoke 권한을 받을 대상)
GATEWAY_NAME = f"briefing-gw-{DEMO_USER}-gateway"
PROVIDER_NAME = f"briefing_gw_{DEMO_USER}_provider"  # AgentCore Identity provider 이름(하이픈 대신 언더스코어)
TARGET_NAME = "briefing"                             # MCP 도구 이름 앞 prefix — config 의 GATEWAY_TARGET 기본값과 맞춘다
BUILD_DIR = ROOT / ".gw_build"                       # zip 빌드 산출물(gitignore 됨)
ZIP_PATH = ROOT / ".gw_build.zip"

# Gateway 에 등록할 도구 스키마 — 승격하는 retrieval 3도구뿐. ★ 가드레일: 여기에 gate/certify/author 가 없다(노출 금지).
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
    """cognito.yaml 을 배포한다(Cognito + IAM 역할). 멱등 — 스택이 있으면 update 하고, 바꿀 게 없으면("No updates") 조용히 넘어간다."""
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
        except Exception as e:  # noqa: BLE001 — "No updates are to be performed" 는 에러가 아니라 정상(바뀐 게 없음)
            if "No updates" not in str(e):
                raise
            print(f"♻ CFN 변경 없음: {STACK}")
    out = {o["OutputKey"]: o["OutputValue"]
           for o in cf.describe_stacks(StackName=STACK)["Stacks"][0]["Outputs"]}
    print(f"✅ Cognito+IAM: pool={out['UserPoolId']}")
    return out


def _client_secret(pool_id: str, client_id: str) -> str:
    """Cognito ClientSecret 을 가져온다. CFN output 에는 안 담기므로 describe API 로 따로 조회한다(aiops 와 동일)."""
    return boto3.client("cognito-idp", region_name=REGION).describe_user_pool_client(
        UserPoolId=pool_id, ClientId=client_id)["UserPoolClient"]["ClientSecret"]


def _build_zip(account: str) -> tuple[str, str]:
    """Lambda 에 올릴 zip 을 docker 없이 빌드한다 — 네이티브 wheel(이 호스트=Lambda 플랫폼) + briefing 소스 → S3 업로드.

    boto3 는 Lambda 가 기본 제공하므로 넣지 않는다. lxml/trafilatura 는 manylinux wheel(glibc≤2.25 → AL2023 에서 동작).
    ⚠️ 리뷰 메모: 의존성을 버전 고정 없이 설치하고, 빌드 호스트가 linux x86_64·py3.12 라고 *가정*한다(다른 플랫폼이면 wheel 비호환).
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
        if REGION == "us-east-1":          # us-east-1 은 LocationConstraint 를 주면 안 된다(다른 리전과 규칙이 다름)
            s3.create_bucket(Bucket=bucket)
        else:
            s3.create_bucket(Bucket=bucket, CreateBucketConfiguration={"LocationConstraint": REGION})
    except Exception as e:  # noqa: BLE001 — 내가 이미 가진 버킷이면 무시하고 진행(멱등)
        if not any(x in type(e).__name__ for x in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists")):
            raise
    key = "gateway/handler.zip"
    s3.upload_file(str(ZIP_PATH), bucket, key)
    print(f"✅ zip → s3://{bucket}/{key} ({ZIP_PATH.stat().st_size // (1024 * 1024)}MB)")
    return bucket, key


def _lambda(bucket: str, key: str, role_arn: str) -> str:
    """zip Lambda 를 만들거나(있으면) 코드만 갱신한다. env 로 DDB backend 를 켠다(get_source 용). AWS_REGION 은 Lambda 가 자동 주입."""
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
    """OAuth2 자격증명 provider(CustomOauth2)를 만든다 — Cognito 비밀을 AgentCore 볼트에 보관. Runtime 은 비밀 없이 토큰을 받는다.

    ⚠️ 리뷰 메모: 이미 있으면 *건너뛰기만* 한다(업데이트 안 함) — Cognito 가 재생성돼 비밀이 바뀌면 stale 될 수 있음.
    """
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
    except Exception as e:  # noqa: BLE001 — 이미 존재(ConflictException 또는 "already exists")면 멱등 처리
        if "Conflict" in type(e).__name__ or "already exists" in str(e):
            print(f"♻ OAuth2 provider 존재: {PROVIDER_NAME}")
        else:
            raise
    return PROVIDER_NAME


def _gateway(role_arn: str, pool_id: str, client_id: str, scope: str, lambda_arn: str) -> str:
    """Gateway(MCP 프로토콜·CUSTOM_JWT 인증)와 target(Lambda·3도구·GATEWAY_IAM_ROLE)을 만든다. ★ Gateway 가 READY 된 뒤에 target 을 붙여야 한다."""
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
    for _ in range(30):                                  # Gateway 가 READY 될 때까지 대기 — 아직 CREATING 이면 target 생성이 실패하므로 필수
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
