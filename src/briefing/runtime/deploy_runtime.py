#!/usr/bin/env python3
"""deploy_runtime.py — ② AgentCore Runtime 프로모트 (starter-toolkit `Runtime.configure().launch()`).

흐름(aiops `monitor/runtime/deploy_runtime.py` 미러 + 우리 적응):
  [1] stage   — `src/briefing` 패키지를 self-contained 빌드 컨텍스트(.agentcore_build/)로 복사.
                ★ toolkit 빌드 컨텍스트 = entrypoint 디렉토리라, 우리 `from ..shared` 패키지 import 가
                  깨지지 않게 *패키지 통째로* 컨텍스트에 둔다(aiops 의 "copy shared in" 패턴의 패키지 버전).
  [2] configure — toolkit 이 Dockerfile·ECR·**IAM execution role 자동 생성**(우리는 손-생성 안 함).
  [3] launch  — CodeBuild 가 ARM64 이미지 빌드→ECR 푸시→Runtime 생성(로컬 docker 불필요).
                컨테이너는 `.env` 를 안 읽음 → `runtime_env(settings)` 로 OS-env 주입(**DEBUG forward 포함**).
  [4] extras  — toolkit 이 안 거는 권한만 boto3 inline policy 로 부착(Bedrock invoke + SES send).
                ★ aiops 의 OAuth2/Cognito 는 ① Gateway(v2)용 — v1 공개 RSS 엔 없음(더 단순).
  [5] wait    — bedrock-agentcore-control 로 READY polling.
  [6] save    — 루트 `.env` 에 `BRIEFING_RUNTIME_{NAME,ARN,ID}` writeback(invoke/teardown 이 읽는 seam).

DEBUG: 호스트 `DEBUG` 를 컨테이너로 forward(on→is_debug() on, trace=stderr→CloudWatch; off→zero overhead).

사용법: `[DEBUG=1] uv run python -m briefing.runtime.deploy_runtime`
사전: AWS 자격증명 · `bedrock-agentcore-starter-toolkit`(dev dep) · region=us-east-1.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import time
from pathlib import Path

import boto3

from ..shared.config import Settings, load_settings

PROJECT_ROOT = Path(__file__).resolve().parents[3]      # …/briefing-lane-b
PACKAGE_DIR = PROJECT_ROOT / "src" / "briefing"
BUILD_DIR = PROJECT_ROOT / ".agentcore_build"           # gitignore 됨 — toolkit 빌드 산출물 격리
ENV_FILE = PROJECT_ROOT / ".env"

AGENT_NAME = "briefing_agent"
ENTRYPOINT_REL = "briefing/runtime/agentcore_runtime.py"  # 빌드 컨텍스트 기준 → 모듈 briefing.runtime.agentcore_runtime
ENV_SECTION = "# ② Briefing Runtime (deploy_runtime.py)"
# 컨테이너는 비-root 유저(uid 1000)로 실행 → /app 하위(상대 ./.data) 쓰기 불가(Errno 13).
# v1 = ephemeral /tmp(invoke 간 비영속); ③ DB(S3/DDB) 백킹이 들어오면 그쪽이 정본 store.
CONTAINER_STORE_PATH = "/tmp/briefing/source_store"  # noqa: S108 — 비-root writable, 의도된 ephemeral

_G, _Y, _B, _R, _NC = "\033[0;32m", "\033[1;33m", "\033[0;34m", "\033[0;31m", "\033[0m"


# ───────────────────────── 순수 헬퍼 (테스트가능 — AWS 무관) ─────────────────────────

def runtime_env(settings: Settings) -> dict[str, str]:
    """컨테이너에 주입할 env (컨테이너는 `.env` 미독). ★ 호스트 `DEBUG` 를 그대로 forward(on/off).

    author=`claude -p` 의 Bedrock 라우팅 키도 포함 — ②b 에서 CLI 번들 시 그대로 사용.
    """
    return {
        "AWS_REGION": settings.region,
        "AWS_DEFAULT_REGION": settings.region,
        "AUTHOR_MODEL_ID": settings.author_model_id,
        "SUPERVISOR_MODEL_ID": settings.supervisor_model_id,
        "SES_SENDER": settings.ses_sender,
        # ★ ③ DB: 클라우드는 dynamo backend(영속 — microVM ephemeral FS 를 넘어 source/cache/ledger 공유).
        #   테이블명 default 가 CFN(briefing-*)과 일치하므로 그 외 env 불필요. region=settings.region(us-east-1) 일치 필수.
        "BACKEND": "dynamo",
        # SOURCE_STORE_PATH 는 local backend 폴백용(dynamo 경로는 미사용). 비-root writable 절대경로 유지.
        "SOURCE_STORE_PATH": CONTAINER_STORE_PATH,
        "USERS_DIR": settings.users_dir,
        "CLAUDE_CODE_USE_BEDROCK": "1",   # author=claude -p → Bedrock
        "ENABLE_TOOL_SEARCH": "false",    # Bedrock 가 tool def 선로드(Gateway MCP 사용 시 필수)
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",  # 컨테이너: 텔레메트리/업데이트 등 비필수 네트워크 차단
        "OTEL_RESOURCE_ATTRIBUTES": f"service.name={AGENT_NAME}",
        "AGENT_OBSERVABILITY_ENABLED": "true",
        # ★ 호스트 DEBUG forward — 미설정/빈값이면 컨테이너 is_debug()==False(zero overhead)
        "DEBUG": os.environ.get("DEBUG", ""),
    }


def _upsert_env_lines(text: str, updates: dict[str, str], *, section: str) -> str:
    """루트 `.env` writeback(순수 문자열 변환) — **idempotent**: 재배포해도 키/섹션 중복 0.

    기존의 같은 키 라인 + 섹션 마커를 제거하고, 신선한 섹션 블록을 끝에 append.
    """
    keys = set(updates)
    kept: list[str] = []
    for line in text.splitlines():
        if line.strip() == section:
            continue
        if "=" in line and line.split("=", 1)[0].strip() in keys:
            continue
        kept.append(line)
    while kept and not kept[-1].strip():   # 끝쪽 빈 줄 정리(블록 사이 단일 공백 보장)
        kept.pop()
    block = [section, *(f"{k}={v}" for k, v in updates.items())]
    return "\n".join([*kept, "", *block]) + "\n"


# ───────────────────────── [1] 빌드 컨텍스트 staging ─────────────────────────

def stage_build_context() -> Path:
    """`src/briefing` 패키지 + 컨테이너 requirements 를 self-contained 빌드 컨텍스트로 복사.

    ★ 우리 entrypoint 는 `from ..shared` 패키지 상대 import → 컨테이너에서 `briefing/` 패키지가
      통째로 있어야 resolve. toolkit 이 빌드 컨텍스트(= cwd)를 COPY 하므로 여기에 패키지를 둔다.
    """
    print(f"{_Y}[1/6] 빌드 컨텍스트 staging → {BUILD_DIR.relative_to(PROJECT_ROOT)}/{_NC}")
    if BUILD_DIR.exists():
        shutil.rmtree(BUILD_DIR)
    BUILD_DIR.mkdir(parents=True)
    # __pycache__/.venv 류 제외하고 패키지 복사
    shutil.copytree(
        PACKAGE_DIR, BUILD_DIR / "briefing",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".agentcore_build"),
    )
    # 빌드 컨텍스트 *루트*에 둬야 toolkit/Dockerfile 이 COPY 로 집는다:
    #   - Dockerfile        → toolkit 이 "기존 Dockerfile" 로 인식해 생성 대신 사용(②b 하니스 이미지)
    #   - requirements.txt  → uv pip install
    #   - {codex,claude} config → 컨테이너 ~/.codex/config.toml · ~/.claude.json 으로 굽기(비밀 0)
    rt = PACKAGE_DIR / "runtime"
    for fname in ("Dockerfile", "requirements.txt", "codex_config.toml", "claude_config.json"):
        shutil.copy2(rt / fname, BUILD_DIR / fname)
    # ⑤: users/ 도 컨테이너로 — mode=scheduled/real 이 실 사용자(send_hour/timezone/recipient) 로드(USERS_DIR=./users → /app/users).
    users_src = PROJECT_ROOT / "users"
    if users_src.exists():
        shutil.copytree(users_src, BUILD_DIR / "users", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    print(f"{_G}✅ briefing/ + Dockerfile + requirements + 하니스 config + users/ 복사{_NC}\n")
    return BUILD_DIR


# ───────────────────────── [2] configure ─────────────────────────

def configure_runtime(region: str):
    """toolkit `Runtime.configure()` — Dockerfile/ECR/IAM execution role 자동 생성(빌드/푸시는 launch)."""
    print(f"{_Y}[2/6] AgentCore Runtime 설정(configure){_NC}")
    try:
        from bedrock_agentcore_starter_toolkit import Runtime
    except ImportError:
        sys.exit(f"{_R}❌ bedrock-agentcore-starter-toolkit 미설치 — `uv sync`(dev dep){_NC}")
    runtime = Runtime()
    resp = runtime.configure(
        agent_name=AGENT_NAME,
        entrypoint=ENTRYPOINT_REL,
        requirements_file="requirements.txt",
        auto_create_execution_role=True,
        auto_create_ecr=True,
        region=region,
        non_interactive=True,
    )
    print(f"{_G}✅ configure 완료 — Dockerfile={getattr(resp, 'dockerfile_path', '?')}{_NC}\n")
    return runtime


# ───────────────────────── [3] launch (CodeBuild ARM64) ─────────────────────────

def launch_runtime(runtime, settings: Settings):
    """Docker(ARM64 via CodeBuild) 빌드 → ECR 푸시 → Runtime 생성. 컨테이너 env 주입(DEBUG forward)."""
    debug_on = bool(os.environ.get("DEBUG", "").strip())
    print(f"{_Y}[3/6] launch (CodeBuild ARM64 빌드→ECR→Runtime){_NC}")
    print(f"   DEBUG forward = {'on' if debug_on else 'off'}  ⏳ 첫 배포 ~5-10분")
    t0 = time.monotonic()
    result = runtime.launch(env_vars=runtime_env(settings), auto_update_on_conflict=True)
    print(f"{_G}✅ launch ({time.monotonic() - t0:.0f}s) — ARN={result.agent_arn}{_NC}\n")
    return result


# ───────────────────────── [4] IAM extras (Bedrock + SES) ─────────────────────────

def attach_runtime_extras(result, region: str) -> None:
    """toolkit 자동 role 에 *우리 워크로드* 권한만 inline 부착 — Bedrock invoke(author) + SES send(⑤).

    ★ 최소권한 TODO: Resource 를 실제 inference-profile/SES identity ARN 으로 좁히면 더 안전
      (지금은 global. 프로파일이 다중 리전 → foundation-model/inference-profile 와일드카드).
    """
    print(f"{_Y}[4/6] IAM extras inline policy 부착(Bedrock+SES){_NC}")
    control = boto3.client("bedrock-agentcore-control", region_name=region)
    role_arn = control.get_agent_runtime(agentRuntimeId=result.agent_id)["roleArn"]
    role_name = role_arn.split("/")[-1]
    account = role_arn.split(":")[4]
    policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "BedrockInvokeAuthor",   # author=claude(Sonnet 4.6) — 표준 Bedrock InvokeModel
                "Effect": "Allow",
                "Action": ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
                "Resource": [
                    "arn:aws:bedrock:*::foundation-model/*",
                    f"arn:aws:bedrock:*:{account}:inference-profile/*",
                ],
            },
            {
                # ★ certifier=codex(GPT-5.5)는 *별도 서비스* `bedrock-mantle`(OpenAI Responses API) 사용.
                #   진단으로 확인된 액션: bedrock-mantle:CreateInference (bedrock:InvokeModel 로는 401).
                "Sid": "BedrockMantleCertifier",
                "Effect": "Allow",
                "Action": ["bedrock-mantle:CreateInference"],
                "Resource": f"arn:aws:bedrock-mantle:*:{account}:project/*",
            },
            {
                "Sid": "SesTrialAndSend",        # ⑤ 전달 + v1.1a trial polling(identity 검증 상태 확인)
                "Effect": "Allow",
                "Action": ["ses:SendEmail", "ses:SendRawEmail", "ses:GetIdentityVerificationAttributes"],
                "Resource": "*",
            },
            {
                # ③ DB: dynamo backend(source/cache/ledger) — dynamo.py 가 쓰는 3작업만(최소권한).
                # ledger 시간-쿼리는 GSI 사용 → index/* 포함. 테이블 prefix=briefing-(CFN infra/ddb.yaml).
                "Sid": "DynamoStores",
                "Effect": "Allow",
                "Action": ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:Query"],
                "Resource": [
                    f"arn:aws:dynamodb:*:{account}:table/briefing-*",
                    f"arn:aws:dynamodb:*:{account}:table/briefing-*/index/*",
                ],
            },
        ],
    }
    boto3.client("iam").put_role_policy(
        RoleName=role_name, PolicyName="BriefingRuntimeExtras", PolicyDocument=json.dumps(policy)
    )
    print(f"{_G}✅ {role_name}/BriefingRuntimeExtras 부착{_NC}\n")


# ───────────────────────── [5] READY 대기 ─────────────────────────

def wait_until_ready(result, region: str) -> None:
    """Runtime 상태 READY polling(최대 ~10분). terminal 비-READY 면 exit 1."""
    print(f"{_Y}[5/6] READY 대기(최대 10분){_NC}")
    control = boto3.client("bedrock-agentcore-control", region_name=region)
    terminal = {"READY", "CREATE_FAILED", "UPDATE_FAILED", "DELETE_FAILED"}
    status = "CREATING"
    for i in range(1, 61):
        time.sleep(10)
        status = control.get_agent_runtime(agentRuntimeId=result.agent_id)["status"]
        print(f"   [{i}/60] {status}")
        if status in terminal:
            break
    if status != "READY":
        # ★ agent_id 가 이미 '{AGENT_NAME}-<suffix>' → log group = '{agent_id}-DEFAULT' (prefix 중복 금지)
        sys.exit(f"{_R}❌ Runtime 실패(status={status}) — `aws logs tail "
                 f"/aws/bedrock-agentcore/runtimes/{result.agent_id}-DEFAULT`{_NC}")
    print(f"{_G}✅ READY{_NC}\n")


# ───────────────────────── [6] .env writeback ─────────────────────────

def save_runtime_metadata(result) -> None:
    """루트 `.env` 에 `BRIEFING_RUNTIME_{NAME,ARN,ID}` writeback(invoke/teardown 의 seam)."""
    print(f"{_Y}[6/6] 루트 .env writeback(BRIEFING_RUNTIME_*){_NC}")
    text = ENV_FILE.read_text(encoding="utf-8") if ENV_FILE.exists() else ""
    text = _upsert_env_lines(
        text,
        {
            "BRIEFING_RUNTIME_NAME": AGENT_NAME,
            "BRIEFING_RUNTIME_ARN": result.agent_arn,
            "BRIEFING_RUNTIME_ID": result.agent_id,
        },
        section=ENV_SECTION,
    )
    ENV_FILE.write_text(text, encoding="utf-8")
    print(f"{_G}✅ {ENV_FILE.name} 갱신{_NC}\n")


def main() -> None:
    settings = load_settings()
    region = settings.region
    debug_on = bool(os.environ.get("DEBUG", "").strip())
    print(f"\n{_B}{'=' * 60}\n  ② Briefing Runtime 배포 — region={region} · DEBUG={'on' if debug_on else 'off'}\n{'=' * 60}{_NC}\n")

    cwd0 = Path.cwd()
    stage_build_context()
    os.chdir(BUILD_DIR)                      # toolkit build_dir = cwd
    try:
        runtime = configure_runtime(region)
        result = launch_runtime(runtime, settings)
    finally:
        os.chdir(cwd0)                       # cwd 복원(이후 .env 등 상대경로 안전)
    attach_runtime_extras(result, region)
    wait_until_ready(result, region)
    save_runtime_metadata(result)

    print(f"{_B}{'=' * 60}{_NC}\n{_G}  배포 완료{_NC}")
    print(f"   ARN: {result.agent_arn}")
    print("   invoke:   uv run python -m briefing.runtime.invoke_runtime --mode smoke")
    print("   teardown: bash src/briefing/runtime/teardown.sh")
    if debug_on:
        print(f"   logs:     aws logs tail /aws/bedrock-agentcore/runtimes/{result.agent_id}-DEFAULT --follow --region {region}")
    print()


if __name__ == "__main__":
    main()
