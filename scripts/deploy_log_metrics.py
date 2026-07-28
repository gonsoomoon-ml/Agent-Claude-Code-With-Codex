#!/usr/bin/env python
"""deploy_log_metrics — 런타임 warn 로그를 CloudWatch **메트릭 필터**로 집계(멱등).

**왜 필요한가.** `_debug.warn` 은 드문 실패를 가시화하려고 있는데, 로그 줄로만 남으면
30분짜리 런의 수십 줄 사이에 묻힌다. 특히 **해석층 폴백**(gate.interpret_card 가 lint 실패·예외 시
사실층 why 로 강등)은 카드가 정상 발행되므로 **아무도 눈치채지 못한 채** lens 해석만 조용히 사라진다.
집계 지표가 없으면 "가드가 잘 동작해서 폴백이 0" 인지 "관측이 안 돼서 0으로 보이는" 지 구분할 수 없다.

**왜 코드가 아니라 메트릭 필터인가.** 런타임 코드·IAM·지연에 손대지 않는다(비용 ~0). 이미 나가는
로그를 CloudWatch 가 세 준다.

★ 중복 계수 함정(실측): 같은 logging 레코드가 이 로그그룹에 **두 형식으로 기록**된다 —
  ① OTEL JSON(`"scope":{"name":...}`, `"body":...`) ② stdout JSON(`"logger":..., "message":...`).
  따라서 `"사실층 why 폴백"` 같은 **텍스트 패턴은 1회 폴백을 2로 센다**. JSON 패턴으로 ②만 잡는다.
  (`aws logs test-metric-filter` 로 두 형식 모두에 대해 검증했다 — 아래 `_SAMPLES` 가 그 회귀셋.)

usage: uv run python scripts/deploy_log_metrics.py [--dry-run]
사전: AWS 자격 · `.env` 의 BRIEFING_RUNTIME_ID (deploy_runtime 이 writeback).
"""
from __future__ import annotations

import sys
from pathlib import Path

import boto3

REGION = "us-east-1"
NAMESPACE = "Briefing"
_REPO = Path(__file__).resolve().parent.parent


def _runtime_id() -> str:
    """`.env` 의 BRIEFING_RUNTIME_ID — deploy_runtime 이 써 두는 seam(하드코딩 금지)."""
    for line in (_REPO / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith("BRIEFING_RUNTIME_ID="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("BRIEFING_RUNTIME_ID 를 .env 에서 못 찾음 — deploy_runtime 을 먼저 실행하라")


# 필터 정의. logger="briefing" = `_debug._LOG` 의 이름(core/_debug.py) — 서드파티 로그와 분리된다.
FILTERS = [
    {
        "name": "briefing-interp-fallback",
        "metric": "InterpFallback",
        "pattern": '{ $.logger = "briefing" && $.message = "*사실층 why 폴백*" }',
        "why": "해석층 폴백(lint 실패·예외) — lens 해석이 조용히 사라진 건수",
    },
    {
        "name": "briefing-relevance-fallback",
        "metric": "RelevanceFallback",
        "pattern": '{ $.logger = "briefing" && $.message = "*키워드 폴백*" }',
        "why": "Haiku 관련성 판정자 실패 → 동결 키워드로 퇴화한 건수(비-AI 기사 유입 경로)",
    },
    {
        "name": "briefing-curate-skip",
        "metric": "CurateSkip",
        "pattern": '{ $.logger = "briefing" && $.message = "*curate skip*" }',
        "why": "출처 1개 페치 실패로 통째 건너뛴 건수",
    },
    {
        "name": "briefing-warn-total",
        "metric": "WarnTotal",
        "pattern": '{ $.logger = "briefing" && $.level = "WARNING" }',
        "why": "우리 warn 전체 — 위 3종에 안 잡히는 새 실패 유형의 조기 신호",
    },
]

# 회귀셋: 패턴이 무엇을 잡고 무엇을 안 잡는지 배포 전에 고정한다(형식 가정이 깨지면 여기서 터진다).
_SAMPLES: list[tuple[str, str, set[str]]] = [
    ("interp 폴백(lint)", '{"level":"WARNING","message":"[gate interp] 0a341ab: lint 실패(미검증 수치 밀수) → 사실층 why 폴백","logger":"briefing"}',
     {"InterpFallback", "WarnTotal"}),
    ("interp 폴백(예외)", '{"level":"WARNING","message":"[gate interp] 0a341ab: TimeoutError: x → 사실층 why 폴백","logger":"briefing"}',
     {"InterpFallback", "WarnTotal"}),
    ("relevance 폴백", '{"level":"WARNING","message":"[relevance llm] ThrottlingException → 키워드 폴백","logger":"briefing"}',
     {"RelevanceFallback", "WarnTotal"}),
    ("curate skip", '{"level":"WARNING","message":"[curate skip] aitimes: TimeoutError","logger":"briefing"}',
     {"CurateSkip", "WarnTotal"}),
    ("OTEL 중복본(계수 금지)", '{"scope":{"name":"briefing"},"severityText":"WARN","body":"[gate interp] x → 사실층 why 폴백"}',
     set()),
    ("서드파티 INFO", '{"level":"INFO","message":"Async task started","logger":"bedrock_agentcore.app"}', set()),
]


def _verify_patterns(cw) -> None:
    """배포 전 자체 검증 — 각 샘플이 정확히 기대한 메트릭에만 매치하는지."""
    print("── 패턴 회귀 검증 ──")
    bad = 0
    for label, msg, expect in _SAMPLES:
        got = {f["metric"] for f in FILTERS
               if cw.test_metric_filter(filterPattern=f["pattern"], logEventMessages=[msg])["matches"]}
        ok = got == expect
        bad += 0 if ok else 1
        print(f"  {'OK ' if ok else 'FAIL'} {label:<22} 매치={sorted(got) or '없음'}"
              + ("" if ok else f"  기대={sorted(expect) or '없음'}"))
    if bad:
        raise SystemExit(f"패턴 검증 실패 {bad}건 — 배포 중단(로그 형식 가정이 깨졌을 수 있다)")


def main() -> None:
    dry = "--dry-run" in sys.argv
    cw = boto3.client("logs", region_name=REGION)
    lg = f"/aws/bedrock-agentcore/runtimes/{_runtime_id()}-DEFAULT"
    print(f"로그그룹: {lg}\n네임스페이스: {NAMESPACE}\n")

    _verify_patterns(cw)

    print(f"\n── 메트릭 필터 {'(dry-run)' if dry else '배포'} ──")
    for f in FILTERS:
        if dry:
            print(f"  [skip] {f['name']} → {NAMESPACE}/{f['metric']}")
            continue
        cw.put_metric_filter(   # 멱등 — 같은 이름이면 덮어쓴다
            logGroupName=lg, filterName=f["name"], filterPattern=f["pattern"],
            metricTransformations=[{
                "metricName": f["metric"], "metricNamespace": NAMESPACE,
                "metricValue": "1", "defaultValue": 0.0,
            }],
        )
        print(f"  ✅ {f['name']:<30} → {NAMESPACE}/{f['metric']}  ({f['why']})")

    if not dry:
        got = cw.describe_metric_filters(logGroupName=lg)["metricFilters"]
        names = {m["filterName"] for m in got}
        missing = [f["name"] for f in FILTERS if f["name"] not in names]
        print(f"\n── 확인: 로그그룹에 등록된 필터 {len(got)}개 ──")
        for m in sorted(got, key=lambda x: x["filterName"]):
            print(f"  {m['filterName']:<30} {m['metricTransformations'][0]['metricName']}")
        if missing:
            raise SystemExit(f"등록 실패: {missing}")

    print("\n조회 예:")
    print(f"  aws cloudwatch get-metric-statistics --namespace {NAMESPACE} --metric-name InterpFallback \\")
    print("    --start-time $(date -u -d '1 day ago' +%FT%TZ) --end-time $(date -u +%FT%TZ) \\")
    print(f"    --period 3600 --statistics Sum --region {REGION}")
    print("\n※ 폴백'률'의 분모는 이 메트릭에 없다 — `briefing-sent-log` 의 published(카드 수)와 함께 봐라.")


if __name__ == "__main__":
    main()
