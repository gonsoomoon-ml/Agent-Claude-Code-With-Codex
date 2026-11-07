# Field Experiment 1-B — 클라우드 자동 스케줄 전달 기록 (Delivery Record)

> 상태: **DEPLOYED · LIVE(runtime v70 · scheduler 00:31Z) · 클라우드 build/send-dry-run 검증 완료 · 11-07 호는 보내지 않음(§5 — (d) 전환)** · 날짜: 2026-11-07 · main `9458626`(`feat/weekly-cloud-schedule` ff-merge: `255f5d8` 코드 + `9458626` invoke CLI·문서) · 계획: `field-experiment/delivery-plan.md` §4 · §7-4 · §8
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
| 새 Lambda 의 첫 프로덕션 시간당 tick(01:00Z) | Lambda 정상 종료 · 런타임이 `scheduled_briefing` async task 수락 | ✅ Lambda 7.1s 정상(REPORT, 오류 0) · 런타임 `Async task started/completed: scheduled_briefing`(0.02s — 10:00 KST 는 due 사용자 0, 정상) |
| runtime v69 READY · env `WEEKLY_*` 전달 | `get-agent-runtime` 에 `WEEKLY_ADMIN_USER_ID` 등 | ✅ v69 READY(00:2xZ, launch 79s) · WEEKLY 키 5개(ADMIN_USER_ID·AUTHOR_EFFORT·AUTHOR_MODEL_ID·SELECT_MODEL_ID·STRICT; FIGURE 없음) · IAM `BedrockListProfilesWeeklyGate` 부착 확인 |
| `briefing-weekly-build` / `-send` | `cron(0 6 ? * SAT *)` / `cron(0 7 ? * SAT *)` · `Asia/Seoul` · ENABLED | ✅ 둘 다 생성·ENABLED·Input 에 mode · `briefing-hourly-tick` Input `{"source":…}` 불변 |
| Lambda `BRIEFING_DRY_RUN` | `0`(재배포 뒤에도) | ✅ `0` · LastModified 00:31:22Z · Active |
| 표 `briefing-weekly-issues` | ACTIVE · PK `issue_date` | ✅ 생성(00:31Z) · ACTIVE · HASH `issue_date` · `.env` `BRIEFING_WEEKLY_ISSUES_TABLE` writeback |
| 클라우드 `weekly_build 2026-11-07` | 표 상태 `ready`(또는 `quarantined` + 사유) · 게이트 `model` 항목 PASS(IAM) | ❌ **`failed` — `write: TimeoutExpired`**(00:31:57 accepted → 00:38:55, 418s; select 은 약 58초에 통과, 카드 113장) → §6 |
| runtime **v70**(상한 고침 `006620e`) | READY · env `WEEKLY_AUTHOR_TIMEOUT_S=1200` · `WEEKLY_MAX_REVISIONS=1` | ✅ v70 READY(사용자 재승인 뒤 배포 시작 00:54Z, READY 는 00:56Z 재실행 전) · 두 키 전달 확인 |
| 클라우드 `weekly_build 2026-11-07` **재실행(v70, timeout 1200)** | `ready`/`quarantined` · `calls_json` 에 호출별 turns·ms | ✅ **`ready`** 00:56:39 → 01:06:17(9.6분) · 게이트 PASS(WARN 3: 본문 2,832자 · ③ 코드 1줄 · ③ 1,096자) · 시도 2(MAX_REVISIONS=1 안) · $2.58 · `model` 검사 PASS(IAM 효력) → 호출별 표는 §7 |
| 클라우드 `weekly_send --dry-run` | 수신자 = 관리자 · 제목 `[현장 실험] …` · 발송 0 | ✅ 런타임 `weekly_send` task 0.13s 완료 · WARN 0 · 같은 코드의 로컬 dry-run(표=dynamo): to=관리자 · 제목 「닫힌 티켓 TODO 가 코딩 에이전트의 요청 밖 수정을 늘리는가」 · 9,585 bytes · 발송 0 |
| 1-B 첫 자동 발송 | 11-14(토) 07:00 KST 도착 · 표 `sent` · sent-log `weekly#<admin>` `2026-11-14` | ⏳ |

## 5. 11-07 호 처리 — 결정(11-07): 보내지 않음, (d) 로 전환

**결정.** (a)·(b) 어느 쪽도 택하지 않았다. 사용자가 그림이 필요하다고 했고, 그림을 매주 자동으로 넣는 영구 해법 (d)(컨테이너에 Chromium + PNG 를 표로)를 골라 **11-07 호는 건너뛴다**. 표의 11-07 항목은 `ready` 로 남는다 — 스케줄은 `issue_date_kst` 로 그 토요일 항목만 집으므로 다시 집히지 않는다. (d) 의 범위 · 호스트 플러그인 오버헤드 조사 · 11-14 체크리스트 = `2026-11-07-weekly-figure-container-delivery.md`, 흐름도 = `field-experiment/workflow.md`.

**검토했던 갈래(기록).** 
클라우드 `weekly_build 2026-11-07` 이 이번 주 호를 표에 만들었다(v70, `ready`, §7). (a) 클라우드 `weekly_send` 로 보내 로컬 1-A 를 대신한다 — 이미 만들어진 기사 그대로, **③ 그림 없음**(`WEEKLY_FIGURE` 는 컨테이너에 전달하지 않음 → `figure_png` 없음, 본문만), 추가 비용 $0. (b) 계획대로 로컬 1-A(`uv run python -m briefing.weekly.run build` → `send`)를 돌린다 — **다른 기사**(select/write 를 새로 돌려 비결정적), **그림 포함**, 약 $2.5 · 15분. ★ 한 경로만 보낸다: 두 저장소(DDB 표 · 로컬 `.data`)는 서로를 모르고, sent-log `weekly#<admin>/2026-11-07` 의 `mark_sent` 는 덮어쓰기라 중복 발송을 막지 못한다.

## 6. 클라우드 build 실패 진단 (2026-11-07 00:39Z) — 근본 원인

**증상.** `weekly_build --issue-date 2026-11-07` 이 `write` 단계에서 `subprocess.TimeoutExpired` 로 `failed`. 런타임 로그: async task 417.99s. select(씨앗 선정) 은 약 58초에 끝나고, write 가 정확히 **360초**에서 끊겼다.

**원인.** `core/authoring/author.py` `_run_author` 의 `_AUTHOR_TIMEOUT_S = 360` — 데일리 요약 AI(Sonnet 5.5 medium, 카드 1장 119~197초, 2026-07-18 재보정) 기준으로 잡은 **하드코딩 상한**을 주간 작성(Opus 5.5 high · 원문 3편 ≈ 180KB · 기사 전문)이 그대로 물려받는다. 호출자가 바꿀 길이 없다(`timeout=_AUTHOR_TIMEOUT_S` 고정).

**멈춤(hang)이 아니라 느림이라는 증거.** Bedrock CloudWatch(`AWS/Bedrock`, ModelId `global.anthropic.claude-opus-5-5`, 1분 버킷):

| UTC | Invocations | 최대 지연 | 출력 토큰 |
|---|---|---|---|
| 00:32 | 1 | 53s | 5,562 (= select) |
| 00:34 | 5 | 104s | 11,472 |
| 00:36 | 1 | 106s | 12,531 |
| 00:37 | 3 | 29s | 7,310 |
| 00:38 | 2 | 33s | 7,935 |

write 창(00:33~00:38:55) 동안 CLI 가 11회 호출 · 약 39K 출력 토큰을 **계속 생성 중**이었다(`claude -p` 의 다턴 루프 + high effort 사고 토큰). stdin 전달은 select 에서 이미 통과했으므로 전달 경로 문제가 아니다. 호스트(11-04 로컬 run, claude 2.1.319)는 전체 16.5분 · 시도 3 · 작성자 호출 약 7회로 완주했다 — 호출별 시간은 기록이 없어 write 가 로컬에서 몇 초였는지는 모른다(추정 금지). 컨테이너(2.1.301) 와의 차이는 CLI 버전과 다턴 루프(Dockerfile 의 2.1.301 메모) 뿐이다. 1분 버킷 안에 짧은 호출 여럿(00:34 5회)이 섞인 모양은 도구 호출 턴의 신호일 수 있으나 여기서는 확인 불가 — 다음 run 이 `num_turns` · `duration_ms` 를 남기게 해야 한다.

**영향.** 주간만. 데일리는 같은 상한으로 정상(별건 아님). 고치기 전엔 토 06:00 build 가 매주 `failed` → 07:00 "생성 실패" 통지.

**고침(11-07 승인 1·2·3 → main `006620e`, v70 배포 대기).** `_run_author(timeout_s=None)`(기본 360 불변) · `UsageRecorder.calls`(호출별 cost·num_turns·duration_ms) · 주간 4곳 `timeout_s` 전달 · 표 항목 `calls_json`(ready·failed) · `.env` `WEEKLY_AUTHOR_TIMEOUT_S=1200` + `WEEKLY_MAX_REVISIONS=1`(첫 자동 run 완화) · `WEEKLY_ENV_KEYS` 에 TIMEOUT 추가. 테스트 6개 RED→GREEN, suite 919. 검증 = v70 READY 뒤 `weekly_build --issue-date 2026-11-07` 재실행(`failed → building` 허용) → `calls_json` 의 turns·ms 를 이 표에 적는다.

**원래 고칠 방향(승인된 그대로).** ① `_run_author(timeout_s=None)` 인자 추가(기본 = 360 그대로 → 데일리 무변경) · 주간 호출 4곳(select · write · critique · revise)이 `.env` `WEEKLY_AUTHOR_TIMEOUT_S` 를 넘긴다(값은 사용자 결정 — 한 번은 실제 소요를 재야 하므로 넉넉히, 예 1200). ② 같은 변경에 `claude -p` 봉투의 `num_turns` · `duration_ms` 를 비용 옆에 기록해 11-14 run 이 턴 수를 남기게 한다 — 그 뒤에야 대안(턴/도구 제한 `--max-turns`·도구 비활성, 작성 품질이 바뀌는 변경)을 데이터로 판단한다. 예산 주의: 1200s × (write + critique + revise ≤ 2) 는 06:00→07:00 60분을 넘을 수 있다(§6 설계대로 07:00 send 는 실패 통지, 호는 뒤늦게 `ready`·미발송) — 첫 자동 run 은 `WEEKLY_MAX_REVISIONS=1` 로 줄이는 완화책이 있다. **고치기 전까지 11-14 06:00 build 도 같은 이유로 `failed` → 07:00 실패 통지**(조용하진 않지만 발행도 아니다).

## 7. v70 재실행 실측 — 호출별 턴 수 · 소요 (calls_json, 2026-11-07 00:56~01:06Z)

| 단계 | num_turns | 소요 | 비용 |
|---|---|---|---|
| select | 1 | 58.8s | $0.63 |
| **write** | **12** | **345.8s** | $1.34 |
| critique | 1 | 45.5s | $0.22 |
| revise(비평 6건) | 2 | 66.3s | $0.26 |
| revise(게이트 피드백) | 1 | 31.7s | $0.13 |

- write 가 **12턴 · 346초** — 첫 실행이 360초에 끊긴 이유가 그대로 보인다(상한 바로 아래/위를 오간다 — hang 아님). 상한 1200 은 여유가 크고, 전체 build 9.6분은 06:00→07:00 예산 안.
- 다른 단계는 1~2턴이라 **다턴 루프는 write 에만** 있다 → 턴/도구 제한(`--max-turns` · 도구 비활성) 검토는 write 한 곳에 국한하면 된다(작성 품질 영향은 별도 평가 — 재제안 전 이 수치가 근거).
- 사소한 발견: `ready` 전이가 이전 실패의 `error` 필드를 지우지 않아 항목에 옛 `write: TimeoutExpired` 문자열이 남아 있다(`pull` 로그에 "오류:" 로 보임). `building` 전이에서 `error` 를 비우는 게 맞다 — 별건(미수정).
