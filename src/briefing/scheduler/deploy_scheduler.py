#!/usr/bin/env python3
"""deploy_scheduler.py — ⑤ EventBridge Scheduler → Lambda → AgentCore Runtime 배선 배포 (boto3).

deploy_runtime.py 스타일(색 단계·idempotent create-or-update·`.env` writeback). 순서:
  [1] Lambda 실행 role(InvokeAgentRuntime) · [2] DDB 테이블(sent-log · weekly-issues) · [3] Lambda(boto3 번들 zip) ·
  [4] Scheduler 실행 role(InvokeFunction) · [5] EventBridge Scheduler schedule 3개(SCHEDULES) · [6] .env writeback.
주간(1-B, field-experiment/delivery-plan.md §4): 토 06:00 build · 07:00 send(Asia/Seoul) — 같은 Lambda, Input 에 mode.

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
WEEKLY_ISSUES_TABLE = "briefing-weekly-issues"   # 주간 호(PK=issue_date) — weekly/issues.py DEFAULT_TABLE 과 같다
# 스케줄 명세 — Input 의 mode 를 Lambda 가 그대로 나른다(없으면 scheduled). 주간 2개는 KST 로 적는다(DST 없음).
SCHEDULES: tuple[dict, ...] = (
    {"name": SCHEDULE_NAME, "expr": "cron(0 * * * ? *)", "tz": "UTC", "input": {"source": SCHEDULE_NAME}},   # 데일리 매시 정각
    {"name": "briefing-weekly-build", "expr": "cron(0 6 ? * SAT *)", "tz": "Asia/Seoul",
     "input": {"source": "briefing-weekly-build", "mode": "weekly_build"}},
    {"name": "briefing-weekly-send", "expr": "cron(0 7 ? * SAT *)", "tz": "Asia/Seoul",
     "input": {"source": "briefing-weekly-send", "mode": "weekly_send"}},
)
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


# ───────────────────────── DDB 테이블 + Schedule ─────────────────────────

def _ensure_table(ddb, name: str, *, pk: str, sk: str | None = None) -> None:
    """PAY_PER_REQUEST 표 create-or-reuse — sent-log(PK+SK) · weekly-issues(PK 만)."""
    keys = [(pk, "HASH")] + ([(sk, "RANGE")] if sk else [])
    try:
        ddb.create_table(
            TableName=name, BillingMode="PAY_PER_REQUEST",
            AttributeDefinitions=[{"AttributeName": k, "AttributeType": "S"} for k, _ in keys],
            KeySchema=[{"AttributeName": k, "KeyType": t} for k, t in keys],
        )
        ddb.get_waiter("table_exists").wait(TableName=name)
        print(f"   DDB 테이블 생성: {name}")
    except ddb.exceptions.ResourceInUseException:
        print(f"   DDB 테이블 존재(재사용): {name}")


def _ensure_schedule(sched, spec: dict, lambda_arn, sched_role_arn) -> None:
    """SCHEDULES 한 항목 create-or-update. Input 은 명세 그대로(주간만 mode)."""
    args = dict(
        Name=spec["name"], ScheduleExpression=spec["expr"],
        ScheduleExpressionTimezone=spec["tz"], FlexibleTimeWindow={"Mode": "OFF"}, State="ENABLED",
        Target={
            "Arn": lambda_arn, "RoleArn": sched_role_arn,
            "Input": json.dumps(spec["input"]),
            "RetryPolicy": {"MaximumRetryAttempts": 0},  # 중복 fire 최소화(dedup 은 sent-log · 호 상태 전이가 보강)
        },
    )
    try:
        sched.create_schedule(**args)
        print(f"   schedule 생성: {spec['name']} ({spec['expr']} {spec['tz']})")
    except sched.exceptions.ConflictException:
        sched.update_schedule(**args)
        print(f"   schedule 업데이트: {spec['name']} ({spec['expr']} {spec['tz']})")


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

    print(f"{_Y}[2/6] DDB 테이블(sent-log · weekly-issues){_NC}")
    _ensure_table(ddb, SENT_LOG_TABLE, pk="user_id", sk="run_date")
    _ensure_table(ddb, WEEKLY_ISSUES_TABLE, pk="issue_date")

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

    print(f"{_Y}[5/6] EventBridge Scheduler schedule × {len(SCHEDULES)}{_NC}")
    for spec in SCHEDULES:
        _ensure_schedule(sched, spec, lambda_arn, sched_role_arn)

    print(f"{_Y}[6/6] 루트 .env writeback{_NC}")
    text = ENV_FILE.read_text(encoding="utf-8") if ENV_FILE.exists() else ""
    ENV_FILE.write_text(_upsert_env_lines(text, {
        "BRIEFING_SCHEDULER_LAMBDA_NAME": LAMBDA_NAME,
        "BRIEFING_SCHEDULER_LAMBDA_ARN": lambda_arn,
        "BRIEFING_SCHEDULER_SCHEDULE_NAME": SCHEDULE_NAME,
        "BRIEFING_SCHEDULER_LAMBDA_ROLE": LAMBDA_ROLE,
        "BRIEFING_SCHEDULER_EVENTBRIDGE_ROLE": SCHED_ROLE,
        "BRIEFING_SENT_LOG_TABLE": SENT_LOG_TABLE,
        "BRIEFING_WEEKLY_ISSUES_TABLE": WEEKLY_ISSUES_TABLE,
    }, section=ENV_SECTION), encoding="utf-8")

    print(f"\n{_B}{'=' * 60}{_NC}\n{_G}  ⑤ 배포 완료 (DRY_RUN={dry}){_NC}")
    print(f"   수동 테스트: aws lambda invoke --function-name {LAMBDA_NAME} --payload '{{}}' /dev/stdout --region {region}")
    print("   실발송 전환: SES verify 후 BRIEFING_DRY_RUN=0 으로 update-function-configuration")
    print("   ★ 재실행 시 BRIEFING_DRY_RUN 은 호스트 env 값(기본 1)으로 되돌아간다 — 운영은 BRIEFING_DRY_RUN=0 을 붙여 실행")
    print("   정리:        bash src/briefing/scheduler/teardown_scheduler.sh\n")


if __name__ == "__main__":
    main()
