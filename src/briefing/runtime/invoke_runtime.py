#!/usr/bin/env python3
"""invoke_runtime.py — 배포된 ② Runtime 1회 호출 + SSE 스트림 출력(배포 검증).

done-when(②): 실 AgentCore 에 invoke → 사용자별 결과 SSE. 기본 `--mode smoke`(결정론 plumbing 검증),
`--mode real` 은 진짜 파이프라인(②b 에서 컨테이너에 claude+codex 번들 후).

우리 entrypoint SSE 스키마: `{"type":"stage"|"user"|"workflow_complete", ...}`
  - stage : {stage, users}             — run_briefing 시작
  - user  : {user, recipient, published, quarantined, bytes}  — 사용자별 결과(per-user 팬아웃)

사용법: `[DEBUG=1] uv run python -m briefing.runtime.invoke_runtime [--mode smoke|real]`
사전: deploy_runtime.py 완료(루트 `.env` 에 `BRIEFING_RUNTIME_ARN`).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from pathlib import Path

import boto3
from botocore.config import Config

from ..core.config import load_settings

PROJECT_ROOT = Path(__file__).resolve().parents[3]
ENV_FILE = PROJECT_ROOT / ".env"

_G, _B, _R, _DIM, _NC = "\033[0;32m", "\033[0;34m", "\033[0;31m", "\033[2m", "\033[0m"


def parse_sse_event(line: bytes) -> dict | None:
    """SSE `data: {...}` 한 줄 → dict. 빈 줄·비-JSON·비-dict 는 None(노이즈 견고)."""
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


def _runtime_arn() -> str:
    """루트 `.env` 의 `BRIEFING_RUNTIME_ARN`(deploy_runtime.py writeback). dotenv 가 load_settings 에서 로드."""
    load_settings()  # .env 를 os.environ 으로 로드(dotenv override)
    arn = os.getenv("BRIEFING_RUNTIME_ARN", "")
    if not arn and ENV_FILE.exists():  # dotenv 미설치 폴백 — 직접 파싱
        for ln in ENV_FILE.read_text(encoding="utf-8").splitlines():
            if ln.startswith("BRIEFING_RUNTIME_ARN="):
                arn = ln.split("=", 1)[1].strip()
    return arn


def _print_event(ev: dict) -> None:
    """우리 entrypoint SSE 이벤트 1건을 사람 친화적으로 출력."""
    etype = ev.get("type")
    if etype == "stage":
        print(f"{_B}▶ stage={ev.get('stage')} users={ev.get('users')}{_NC}")
    elif etype == "user":
        flag = f"{_R}QUARANTINE{_NC}" if ev.get("quarantined") else f"{_G}PUBLISH{_NC}"
        print(f"  · {ev.get('user')} → {ev.get('recipient')} | {flag} "
              f"published={ev.get('published')} quarantined={ev.get('quarantined')} bytes={ev.get('bytes')}")
    elif etype == "workflow_complete":
        print(f"{_B}■ workflow_complete{_NC}")
    elif etype == "accepted":   # scheduled/trial — 즉시 ack(브리핑은 백그라운드 → CloudWatch 로 확인)
        ev_mode = ev.get("mode", "scheduled")
        if ev_mode == "trial":
            print(f"{_B}▶ accepted (trial async){_NC} email={ev.get('email')} task_id={ev.get('task_id')} dry_run={ev.get('dry_run')}")
        else:
            print(f"{_B}▶ accepted (scheduled async){_NC} users={ev.get('users')} now={ev.get('now_utc')} dry_run={ev.get('dry_run')}")
    else:
        print(f"{_DIM}{json.dumps(ev, ensure_ascii=False)}{_NC}")


def main() -> None:
    ap = argparse.ArgumentParser(description="② Runtime 1회 invoke + SSE 출력")
    ap.add_argument("--mode", choices=["smoke", "harness", "real", "scheduled", "trial"], default="smoke",
                    help="smoke|harness|real | scheduled=⑤ async(즉시 accepted) | trial=체험(email polling → brief → SES)")
    ap.add_argument("--window-hours", type=int, default=24)
    ap.add_argument("--now-utc", default=None, help="scheduled: now_utc override(ISO, 예 2026-06-27T22:00 → KST 07:00)")
    ap.add_argument("--users", default=None, help="콤마구분 user id override (예 gonsoo)")
    ap.add_argument("--dry-run", action="store_true", help="scheduled/trial: 발송 안 함(due+brief 만)")
    # trial 전용 인자
    ap.add_argument("--email", default=None, help="trial: 체험 수신 이메일(SES 검증 완료 주소)")
    ap.add_argument("--sources", default=None, help="trial: 콤마구분 소스 슬러그 (예 aitimes,aws-ml)")
    args = ap.parse_args()

    if args.mode == "trial" and not args.email:
        ap.error("--mode trial 은 --email 이 필요합니다")

    region = load_settings().region
    arn = _runtime_arn()
    if not arn:
        sys.exit(f"{_R}❌ BRIEFING_RUNTIME_ARN 미설정 — deploy_runtime.py 먼저 실행{_NC}")

    debug_on = bool(os.environ.get("DEBUG", "").strip())
    print(f"{_B}{'=' * 60}\n  invoke mode={args.mode} · region={region} · DEBUG={'on' if debug_on else 'off'}\n  {arn}\n{'=' * 60}{_NC}")
    if debug_on:
        print(f"{_DIM}  trace 는 컨테이너 stderr→CloudWatch (SSE 와 분리). logs tail 로 확인.{_NC}")

    cfg = Config(connect_timeout=60, read_timeout=900, retries={"max_attempts": 0})
    client = boto3.client("bedrock-agentcore", region_name=region, config=cfg)
    payload = {"mode": args.mode, "window_hours": args.window_hours}
    if args.now_utc:
        payload["now_utc"] = args.now_utc
    if args.users:
        payload["users"] = args.users.split(",")
    if args.dry_run:
        payload["dry_run"] = True
    # trial 전용 필드
    if args.mode == "trial":
        payload["email"] = args.email
        if args.sources:
            payload["sources"] = args.sources.split(",")

    resp = client.invoke_agent_runtime(
        agentRuntimeArn=arn,
        qualifier="DEFAULT",
        runtimeSessionId=uuid.uuid4().hex + uuid.uuid4().hex[:1],  # ≥33자(AgentCore 제약)
        payload=json.dumps(payload),
    )

    if "text/event-stream" in resp.get("contentType", ""):
        for line in resp["response"].iter_lines(chunk_size=1):
            ev = parse_sse_event(line)
            if ev is not None:
                _print_event(ev)
    else:  # 비-스트리밍 폴백
        print(resp["response"].read().decode("utf-8"))
    print(f"\n{_G}✅ invoke 완료{_NC}\n")


if __name__ == "__main__":
    main()
