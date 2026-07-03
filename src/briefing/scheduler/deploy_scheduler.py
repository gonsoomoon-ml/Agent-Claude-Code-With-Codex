#!/usr/bin/env python3
"""deploy_scheduler.py — ⑤ EventBridge Scheduler → Lambda → AgentCore Runtime 배선 배포 (boto3).

deploy_runtime.py 스타일(색 단계·idempotent create-or-update·`.env` writeback). 순서:
  [1] Lambda 실행 role(InvokeAgentRuntime) · [2] sent-log DDB 테이블 · [3] Lambda(boto3 번들 zip) ·
  [4] Scheduler 실행 role(InvokeFunction) · [5] EventBridge Scheduler schedule(시간당 cron) · [6] .env writeback.

★ 기본 `BRIEFING_DRY_RUN=1`(발송 안 함, 안전) — 실발송은 SES verify 후 명시적으로 0 으로 flip.
사용법: `uv run python -m briefing.scheduler.deploy_scheduler`  (사전: deploy_runtime 완료 = .env 의 BRIEFING_RUNTIME_ARN)
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

from ..runtime.deploy_runtime import _upsert_env_lines  # 순수 .env writeback 재사용
from ..core.config import load_settings

PROJECT_ROOT = Path(__file__).resolve().parents[3]
ENV_FILE = PROJECT_ROOT / ".env"
HANDLER_SRC = Path(__file__).resolve().parent / "lambda_handler.py"

LAMBDA_NAME = "briefing-scheduler-dispatch"
LAMBDA_ROLE = "briefing-scheduler-lambda-role"
SCHED_ROLE = "briefing-scheduler-eventbridge-role"
SCHEDULE_NAME = "briefing-hourly-tick"
SENT_LOG_TABLE = "briefing-sent-log"
ENV_SECTION = "# ⑤ Briefing Scheduler (deploy_scheduler.py)"
_MANAGED_BASIC = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"

_G, _Y, _B, _R, _NC = "\033[0;32m", "\033[1;33m", "\033[0;34m", "\033[0;31m", "\033[0m"


# ───────────────────────── IAM ─────────────────────────

def _ensure_role(iam, name, trust, inline_name, inline_policy, *, managed=None) -> str:
    try:
        iam.create_role(RoleName=name, AssumeRolePolicyDocument=json.dumps(trust))
        print(f"   role 생성: {name}")
    except iam.exceptions.EntityAlreadyExistsException:
        print(f"   role 존재(재사용): {name}")
    if managed:
        iam.attach_role_policy(RoleName=name, PolicyArn=managed)
    iam.put_role_policy(RoleName=name, PolicyName=inline_name, PolicyDocument=json.dumps(inline_policy))
    return iam.get_role(RoleName=name)["Role"]["Arn"]


# ───────────────────────── Lambda zip (boto3 번들) ─────────────────────────

def _build_lambda_zip() -> bytes:
    """handler(flat) + boto3 번들 → zip. Lambda 기본 boto3 에 bedrock-agentcore data-plane 누락 가능 → 번들."""
    build = Path(tempfile.mkdtemp(prefix="sched-lambda-"))
    try:
        subprocess.run(
            ["uv", "pip", "install", "--target", str(build), "boto3", "botocore"],
            check=True, capture_output=True, text=True,
        )
        shutil.copy2(HANDLER_SRC, build / "lambda_handler.py")  # flat 모듈(상대 import 없음)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for p in sorted(build.rglob("*")):
                if p.is_file():
                    z.write(p, p.relative_to(build))
        return buf.getvalue()
    finally:
        shutil.rmtree(build, ignore_errors=True)


def _deploy_lambda(lam, role_arn, zip_bytes, runtime_arn) -> str:
    env = {"Variables": {  # ★ AWS_REGION 은 예약키라 넣지 않음(Lambda 가 자동 설정)
        "BRIEFING_RUNTIME_ARN": runtime_arn,
        "BRIEFING_DRY_RUN": os.environ.get("BRIEFING_DRY_RUN", "1"),  # 기본 dry-run(안전)
    }}
    try:
        lam.create_function(
            FunctionName=LAMBDA_NAME, Runtime="python3.12", Architectures=["arm64"],
            Role=role_arn, Handler="lambda_handler.handler", Code={"ZipFile": zip_bytes},
            Timeout=120, MemorySize=256, Environment=env,
        )
        print("   Lambda 생성")
    except lam.exceptions.ResourceConflictException:
        lam.update_function_code(FunctionName=LAMBDA_NAME, ZipFile=zip_bytes)
        lam.get_waiter("function_updated").wait(FunctionName=LAMBDA_NAME)
        lam.update_function_configuration(
            FunctionName=LAMBDA_NAME, Role=role_arn, Timeout=120, Environment=env)
        print("   Lambda 업데이트")
    lam.get_waiter("function_active_v2").wait(FunctionName=LAMBDA_NAME)
    return lam.get_function(FunctionName=LAMBDA_NAME)["Configuration"]["FunctionArn"]


# ───────────────────────── DDB sent-log + Schedule ─────────────────────────

def _ensure_sent_log_table(ddb) -> None:
    try:
        ddb.create_table(
            TableName=SENT_LOG_TABLE, BillingMode="PAY_PER_REQUEST",
            AttributeDefinitions=[
                {"AttributeName": "user_id", "AttributeType": "S"},
                {"AttributeName": "run_date", "AttributeType": "S"},
            ],
            KeySchema=[
                {"AttributeName": "user_id", "KeyType": "HASH"},
                {"AttributeName": "run_date", "KeyType": "RANGE"},
            ],
        )
        ddb.get_waiter("table_exists").wait(TableName=SENT_LOG_TABLE)
        print(f"   DDB 테이블 생성: {SENT_LOG_TABLE}")
    except ddb.exceptions.ResourceInUseException:
        print(f"   DDB 테이블 존재(재사용): {SENT_LOG_TABLE}")


def _ensure_schedule(sched, lambda_arn, sched_role_arn) -> None:
    args = dict(
        Name=SCHEDULE_NAME, ScheduleExpression="cron(0 * * * ? *)",  # 매시 정각(UTC)
        ScheduleExpressionTimezone="UTC", FlexibleTimeWindow={"Mode": "OFF"}, State="ENABLED",
        Target={
            "Arn": lambda_arn, "RoleArn": sched_role_arn,
            "Input": json.dumps({"source": SCHEDULE_NAME}),
            "RetryPolicy": {"MaximumRetryAttempts": 0},  # 중복 fire 최소화(dedup 은 sent-log 보강)
        },
    )
    try:
        sched.create_schedule(**args)
        print(f"   schedule 생성: {SCHEDULE_NAME}")
    except sched.exceptions.ConflictException:
        sched.update_schedule(**args)
        print(f"   schedule 업데이트: {SCHEDULE_NAME}")


# ───────────────────────── main ─────────────────────────

def main() -> None:
    settings = load_settings()
    region = settings.region
    runtime_arn = os.getenv("BRIEFING_RUNTIME_ARN", "")
    if not runtime_arn:
        sys.exit(f"{_R}❌ BRIEFING_RUNTIME_ARN 미설정 — deploy_runtime.py 먼저{_NC}")
    acct = boto3.client("sts").get_caller_identity()["Account"]
    dry = os.environ.get("BRIEFING_DRY_RUN", "1")
    print(f"\n{_B}{'=' * 60}\n  ⑤ Scheduler 배포 — region={region} · DRY_RUN={dry}\n{'=' * 60}{_NC}\n")

    iam = boto3.client("iam")
    lam = boto3.client("lambda", region_name=region)
    sched = boto3.client("scheduler", region_name=region)
    ddb = boto3.client("dynamodb", region_name=region)

    print(f"{_Y}[1/6] Lambda 실행 role{_NC}")
    lambda_trust = {"Version": "2012-10-17", "Statement": [
        {"Effect": "Allow", "Principal": {"Service": "lambda.amazonaws.com"}, "Action": "sts:AssumeRole"}]}
    lambda_perm = {"Version": "2012-10-17", "Statement": [{
        "Sid": "InvokeBriefingRuntime", "Effect": "Allow", "Action": "bedrock-agentcore:InvokeAgentRuntime",
        "Resource": [runtime_arn, runtime_arn + "/*"]}]}  # runtime + endpoint 서브리소스
    lambda_role_arn = _ensure_role(iam, LAMBDA_ROLE, lambda_trust, "BriefingSchedulerInvokeRuntime",
                                   lambda_perm, managed=_MANAGED_BASIC)
    time.sleep(10)  # IAM 전파

    print(f"{_Y}[2/6] sent-log DDB 테이블{_NC}")
    _ensure_sent_log_table(ddb)

    print(f"{_Y}[3/6] Lambda 함수(boto3 번들 zip){_NC}")
    lambda_arn = _deploy_lambda(lam, lambda_role_arn, _build_lambda_zip(), runtime_arn)

    print(f"{_Y}[4/6] Scheduler 실행 role{_NC}")
    sched_trust = {"Version": "2012-10-17", "Statement": [{
        "Effect": "Allow", "Principal": {"Service": "scheduler.amazonaws.com"}, "Action": "sts:AssumeRole",
        "Condition": {"StringEquals": {"aws:SourceAccount": acct}}}]}  # confused-deputy 가드
    sched_perm = {"Version": "2012-10-17", "Statement": [{
        "Sid": "InvokeDispatchLambda", "Effect": "Allow", "Action": "lambda:InvokeFunction",
        "Resource": [lambda_arn, lambda_arn + ":*"]}]}
    sched_role_arn = _ensure_role(iam, SCHED_ROLE, sched_trust, "BriefingSchedulerInvokeLambda", sched_perm)
    time.sleep(10)

    print(f"{_Y}[5/6] EventBridge Scheduler schedule{_NC}")
    _ensure_schedule(sched, lambda_arn, sched_role_arn)

    print(f"{_Y}[6/6] 루트 .env writeback{_NC}")
    text = ENV_FILE.read_text(encoding="utf-8") if ENV_FILE.exists() else ""
    ENV_FILE.write_text(_upsert_env_lines(text, {
        "BRIEFING_SCHEDULER_LAMBDA_NAME": LAMBDA_NAME,
        "BRIEFING_SCHEDULER_LAMBDA_ARN": lambda_arn,
        "BRIEFING_SCHEDULER_SCHEDULE_NAME": SCHEDULE_NAME,
        "BRIEFING_SCHEDULER_LAMBDA_ROLE": LAMBDA_ROLE,
        "BRIEFING_SCHEDULER_EVENTBRIDGE_ROLE": SCHED_ROLE,
        "BRIEFING_SENT_LOG_TABLE": SENT_LOG_TABLE,
    }, section=ENV_SECTION), encoding="utf-8")

    print(f"\n{_B}{'=' * 60}{_NC}\n{_G}  ⑤ 배포 완료 (DRY_RUN={dry}){_NC}")
    print(f"   수동 테스트: aws lambda invoke --function-name {LAMBDA_NAME} --payload '{{}}' /dev/stdout --region {region}")
    print("   실발송 전환: SES verify 후 BRIEFING_DRY_RUN=0 으로 update-function-configuration")
    print("   정리:        bash src/briefing/scheduler/teardown_scheduler.sh\n")


if __name__ == "__main__":
    main()
