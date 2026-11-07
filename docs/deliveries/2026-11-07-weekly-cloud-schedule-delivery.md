# Field Experiment 1-B — 클라우드 자동 스케줄 전달 기록 (Delivery Record)

> 상태: **코드 완료 · 배포 대기** · 날짜: 2026-11-07 · main `9458626`(`feat/weekly-cloud-schedule` ff-merge: `255f5d8` 코드 + `9458626` invoke CLI·문서) · 계획: `field-experiment/delivery-plan.md` §4 · §7-4 · §8
> 승인: 11-07 "follow recommendation" — 계획과 다른 점 4개(①~④, 아래 §2)와 배포 순서까지.

## 1. 무엇을 전달했나 (Scope)

매주 토요일 **06:00 KST build → 07:00 KST send(관리자 1명)** 를 EventBridge Scheduler 가 자동으로 부른다.
데일리 시스템(같은 Lambda · 같은 AgentCore Runtime · 같은 stores/author/certifier/SES)을 그대로 타고, 데일리 동작은 바꾸지 않는다.

| 파일 | 변경 |
|---|---|
| `src/briefing/scheduler/lambda_handler.py` | payload `mode` 를 스케줄 Input 에서(없으면 `scheduled`) · 응답에 `mode` |
| `src/briefing/runtime/agentcore_runtime.py` | `weekly_build` · `weekly_send` 분기(fire-and-forget, scheduled 와 같은 모양) |
| `src/briefing/weekly/run.py` | `issue_date_kst`(★ 06:00 KST 토 = 21:00 UTC 금 — UTC 날짜를 쓰면 금요일 호) · `run_cloud`(로컬 CLI 와 같은 build · send) |
| `src/briefing/scheduler/deploy_scheduler.py` | `SCHEDULES` 3개(`briefing-hourly-tick` 무변경 + `briefing-weekly-build` `cron(0 6 ? * SAT *)` + `briefing-weekly-send` `cron(0 7 ? * SAT *)`, `Asia/Seoul`) · `_ensure_table` 일반화 + `briefing-weekly-issues`(PK `issue_date`) · `.env` writeback `BRIEFING_WEEKLY_ISSUES_TABLE` |
| `src/briefing/scheduler/teardown_scheduler.sh` | 스케줄 2개 · 표 1개 추가 |
| `src/briefing/runtime/deploy_runtime.py` | `runtime_env` 에 `WEEKLY_*` 전달(`WEEKLY_ENV_KEYS`, FIGURE 제외) · `runtime_extras_policy` 추출 + `bedrock:ListInferenceProfiles` |
| `src/briefing/runtime/invoke_runtime.py` | `--mode weekly_build\|weekly_send` + `--issue-date`(클라우드 수동 호출 · 검증) |
| tests | `test_scheduler.py` +2 · `test_runtime.py` +4 · `test_weekly_run.py` +2 · `test_deploy_scheduler.py` 신규 3 — 전부 RED → GREEN, 전체 suite 912 passed · ruff clean |

## 2. 계획(§7-4)과 다른 점 — 11-07 승인

1. **`deliver.py` `send_html` 분리 생략.** 주간은 `weekly/run.py` 의 자기 발송 함수(인라인 PNG 용 SendRawEmail)를 쓴다 → 데일리 `deliver.py` 무변경. §8 의 "`make_ses_deliver` 인자 불변" 회귀 테스트는 대상이 없다.
2. **IAM: 표 추가는 불필요, `bedrock:ListInferenceProfiles` 는 필수.** 표는 `table/briefing-*` 와일드카드가 덮는다. 게이트 `weekly/checks.check_models` 가 `list_inference_profiles` 를 부르는데 런타임 role 에 없어, 클라우드에선 ④절에 Claude 모델이 나올 때마다 조회 실패 FAIL(fail-closed) → 매주 격리됐을 것.
3. **`runtime_env` 에 `WEEKLY_FIGURE` 는 넘기지 않는다.** 컨테이너엔 playwright 가 없어 그림 스펙 작성(Opus 호출)만 치르고 `FigureUnavailable` 로 건너뛴다(`figure/render.py:58`). 나머지 `WEEKLY_*` 는 필수 — 빠지면 `WEEKLY_ADMIN_USER_ID` 가 비어 build 첫 줄에서 ValueError → 매주 `failed`(LABEL_MODEL_ID 함정과 같은 종류).
4. **스케줄 이름 `briefing-` 접두**(`weekly-build` → `briefing-weekly-build`), 기존 `briefing-hourly-tick` 과 같은 네임스페이스.

## 3. 배포 순서 (runbook)

순서가 중요하다: **runtime 먼저.** 구 런타임(v68)은 모르는 mode 를 `real` 로 흘려 전 사용자 브리핑을 돌린다(발송은 없지만 비용).

```bash
# 0) 체크아웃이 main(9458626 이상) 이고 다른 세션의 미커밋 변경이 없는지 — deploy 는 작업 트리 src 를 그대로 싣는다
git branch --show-current && git status --short
# 1) runtime v69 — src/briefing 작업 트리를 그대로 싣는다 (05:00 KST 앞뒤 회피)
uv run python -m briefing.runtime.deploy_runtime
# 2) scheduler — Lambda(mode) + 표 + 스케줄 3개. ★ BRIEFING_DRY_RUN 은 호스트 env 로 되돌아가므로 0 을 붙인다
BRIEFING_DRY_RUN=0 uv run python -m briefing.scheduler.deploy_scheduler
# 3) 확인
aws lambda get-function-configuration --function-name briefing-scheduler-dispatch --region us-east-1 --query 'Environment.Variables.BRIEFING_DRY_RUN'
aws scheduler get-schedule --name briefing-weekly-build --region us-east-1 --query '{expr:ScheduleExpression,tz:ScheduleExpressionTimezone,state:State,input:Target.Input}'
aws scheduler get-schedule --name briefing-weekly-send  --region us-east-1 --query '{expr:ScheduleExpression,tz:ScheduleExpressionTimezone,state:State,input:Target.Input}'
aws dynamodb describe-table --table-name briefing-weekly-issues --region us-east-1 --query 'Table.{status:TableStatus,keys:KeySchema}'
aws bedrock-agentcore-control get-agent-runtime --agent-runtime-id briefing_agent-b9uh7rDAqL --region us-east-1 --query 'environmentVariables' | grep -c WEEKLY_   # ≥5
# 4) 클라우드 검증 — build 는 표에만 쓴다(메일 없음, 약 $0.4~1). 발행일은 KST 토요일.
uv run python -m briefing.runtime.invoke_runtime --mode weekly_build --issue-date 2026-11-07
aws dynamodb get-item --table-name briefing-weekly-issues --region us-east-1 --key '{"issue_date":{"S":"2026-11-07"}}' --projection-expression '#s,attempts,cost_usd,notes' --expression-attribute-names '{"#s":"status"}'
uv run python -m briefing.runtime.invoke_runtime --mode weekly_send --issue-date 2026-11-07 --dry-run
```

## 4. 검증 체크리스트 (§8)

| 항목 | 기대 | 결과 |
|---|---|---|
| 전체 `uv run pytest` | 데일리 무변경 — 전부 통과 | ✅ 912 passed · 5 skipped (11-07) |
| 시간당 스케줄 Input(mode 없음) → payload | `{"mode":"scheduled", …}` 그대로 | ✅ `test_lambda_handler_hourly_input_without_mode_stays_scheduled` |
| runtime v69 READY · env `WEEKLY_*` 전달 | `get-agent-runtime` 에 `WEEKLY_ADMIN_USER_ID` 등 | ⏳ |
| `briefing-weekly-build` / `-send` | `cron(0 6 ? * SAT *)` / `cron(0 7 ? * SAT *)` · `Asia/Seoul` · ENABLED | ⏳ |
| Lambda `BRIEFING_DRY_RUN` | `0`(재배포 뒤에도) | ⏳ |
| 표 `briefing-weekly-issues` | ACTIVE · PK `issue_date` | ⏳ |
| 클라우드 `weekly_build 2026-11-07` | 표 상태 `ready`(또는 `quarantined` + 사유) · 게이트 `model` 항목 PASS(IAM) | ⏳ |
| 클라우드 `weekly_send --dry-run` | 수신자 = 관리자 · 제목 `[현장 실험] …` · 발송 0 | ⏳ |
| 1-B 첫 자동 발송 | 11-14(토) 07:00 KST 도착 · 표 `sent` · sent-log `weekly#<admin>` `2026-11-14` | ⏳ |

## 5. 11-07 호 처리 (사용자 결정 대기)

클라우드 `weekly_build 2026-11-07` 이 이번 주 호를 표에 만든다. (a) 클라우드 `weekly_send` 로 보내 로컬 1-A 를 대신하거나, (b) 계획대로 로컬 1-A(`uv run python -m briefing.weekly.run build` → `send`)를 돌리고 클라우드 호는 검증용 사본으로 둔다.
