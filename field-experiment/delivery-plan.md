# Field Experiment 발행 계획 (delivery plan)

> **상태:** 2026-11-03 계획 승인. 구현은 §7 단계마다 별도 승인(파일마다 before → after).
> **2026-11-07:** §7-4 코드 완료(`feat/weekly-cloud-schedule` `255f5d8`, suite 912 passed) — 배포·클라우드 검증은 `docs/deliveries/2026-11-07-weekly-cloud-schedule-delivery.md`. 계획과 다른 점 3개는 §7-4 에 적었다.
> **원칙:** 데일리 코드를 재사용하고, 데일리 동작은 바꾸지 않는다. 이 원칙에 맞춰 바꿀 줄 — `README.md` §2 · §3, 루트 `CLAUDE.md` 의 "src/briefing 무변경" — 은 따로 승인받아 고쳤다(2026-11-03 적용).
> 브랜드 규칙의 진실은 `README.md`. 이 문서는 발송 경로와 구현 순서만 다룬다.

## 요약
- **1단계 = 관리자(admin) 1명, 매주 토 07:00 KST 자동 발송.** 06:00 에 생성하고 07:00 에 발송한다. 데일리 05:00 run 뒤라 금요일 기사까지 들어간다.
- **데일리 시스템을 그대로 탄다.**
  - 같은 scheduler Lambda, 같은 AgentCore Runtime(같은 컨테이너 · role)을 쓴다.
  - 같은 author(`claude -p`) · certifier(`codex exec`) · stores · fetch · SES · sent-log 를 쓴다.
  - 새로 만드는 것은 세 가지뿐이다: 주간 모드 2개, 스케줄 2개, 표 1개.
- **주간 코드는 `src/briefing/weekly/` 에 둔다.** 데일리 패키지 안에 있으니 기존 `deploy_runtime` 이 컨테이너에 함께 싣는다.
- **데일리 쪽 변경은 이음매(seam) 4곳뿐이다.**
  - 기본값은 지금 동작 그대로다. 기존 테스트가 전부 통과해야 한다.
  - 런타임 재배포는 05:00 KST 앞뒤를 피한다.
- **2단계 = 동료 opt-in.** 관리자가 승인해야만 나간다. 구독 칸은 데일리 구독 폼에 추가한다.
- **3단계 = 웹 공개.** 도메인 결정 뒤에 한다.

## 1. 단계

| 단계 | 수신 | 시각(KST, 토) | 들어가는 관문 | 다음 단계 조건 |
|---|---|---|---|---|
| 1 | 관리자 1명 | 06:00 생성 → 07:00 발송 | 주간 모드 · 게이트 | 3호 연속: 정시 · 게이트 PASS · "그대로 보낼 만함" |
| 2 | 동료 opt-in | 07:00 관리자 → 승인하면 동료 | 법적 고칠 것 3개 · 발신 주소 사내 정책 · 구독 칸 · 해지 | 동료 피드백 · 소유자 결정 |
| 3 | 공개(웹 + 구독) | 승인 뒤 게시 | 도메인 · SES DKIM/DMARC · 프로덕션 접근 · 변호사 검토 | — |

- 1-A(11-07 호): 주간 모드를 로컬 CLI 로 돌린다(`uv run python -m briefing.weekly.run build|send`). 같은 코드다.
- 1-B(11-14 호부터): 클라우드 스케줄로 07:00 에 자동 발송한다.
- 2단계 승인은 `briefing.weekly.run approve YYYY-MM-DD` 한 줄이다. 토 12:00 까지 승인이 없으면 동료에게 나가지 않는다.

## 2. 토요일 타임라인

```
05:00  mode=scheduled   (daily)        데일리, 약 10~15분
 |
06:00  mode=weekly_build               주간 생성
 |       collect -> select -> write
 |       -> gate (lint + numeric + codex)
 |       -> briefing-weekly-issues
 |
07:00  mode=weekly_send -> admin       1단계
 |       (생성 실패 -> 실패 통지)
 |
~12:00 approve -> subscribers          2단계
```

## 3. 개념 아키텍처

```
[Daily: Verified Dispatch]
 ledger / card-cache / source-store     검증된 카드(사실층)
 |
 | read-only (한 주 = run_date 토~금)
 v
[Weekly mode]  (같은 runtime)
 |
 +-- select  (Claude)                   §5 하드 게이트 3
 +-- write   (Claude author)            §4 기사 규칙
 +-- gate    (deterministic)            lint · 숫자 · 링크 · 모델
 +-- verify  (Codex certifier)          ② 문장 <-> 카드 claims
 |
 v
[Deliver]
 +-- admin                              1단계
 +-- subscribers (approve)              2단계
 +-- web archive + RSS                  3단계
```
- **신뢰 경계는 데일리와 같다.**
  - Codex 는 `Envelope` 4필드만 받는다. `claim_text` 는 ② 문장 하나, `source_excerpt` 는 인용한 PUBLISH 카드 claims 다.
  - 작성자의 추론은 Codex 에 전달하지 않는다.
  - ③ · ④ 는 제안이라 대조하지 않는다.
- 씨앗이 없는 주에는 "이번 주 아이디어 없음"을 보낸다(README §5).

## 4. 시스템 아키텍처 (AWS us-east-1)

```
EventBridge Scheduler
 +-- briefing-hourly-tick    (existing)  데일리 매시
 +-- briefing-weekly-build   SAT 06:00 Asia/Seoul  NEW (이름은 기존 `briefing-` 접두 따름, 11-07)
 +-- briefing-weekly-send    SAT 07:00 Asia/Seoul  NEW
 |     Input = {"source": <이름>, "mode": "weekly_build" | "weekly_send"}  (dry_run 은 Lambda env BRIEFING_DRY_RUN)
 v
scheduler Lambda (existing)             mode 를 input 에서
 v
AgentCore Runtime (existing container)
 +-- scheduled     -> dispatch          데일리, 무변경
 +-- trial         -> run_trial         무변경
 +-- weekly_build  -> weekly.run.build  NEW
 +-- weekly_send   -> weekly.run.send   NEW
       |
       +-- core/stores        읽기: ledger.query
       +-- core/retrieval     원문 재수집
       +-- core/authoring     _run_author
       +-- core/verification  certify · numeric
       +-- scheduler/deliver  SES
       +-- scheduler/sent_log weekly#<user_id>
       +-- DDB briefing-weekly-issues   NEW
```

**재사용 지도 (무엇을 · 어디서)**
- **트리거:** `scheduler/lambda_handler.py:44` `handler`. 지금은 payload 를 `{"mode":"scheduled"}` 로 고정한다. 바꾸면 event 의 mode 를 읽고, 없으면 scheduled 로 둔다.
- **런타임 분기:** `runtime/agentcore_runtime.py`. trial 분기(`add_async_task` + thread)와 같은 모양으로 주간 분기 2개를 넣는다.
- **작성:** `core/authoring/author.py:302` `_run_author(system, user, settings, model_id=, effort=, recorder=)`. clean dir · Bedrock env · 비용 기록이 이미 들어 있다. 주간은 자기 프롬프트와 모델 id(`.env` `WEEKLY_AUTHOR_MODEL_ID`)만 넘긴다.
- **검증:**
  - `core/verification/certifier.py:65` `certify(claim_id, Envelope)`: 함의는 codex, 산술은 결정론으로 판정한다.
  - `numeric.scan`: ② 의 숫자가 인용한 claims 숫자 안에 들어 있는지 본다.
- **입력:**
  - `make_stores(settings)` 에서 ledger · card-cache · source-store 를 얻는다.
  - `dynamo.py:87` `query(user_id, since_date)` 로 관리자 원장의 한 주를 읽는다.
  - scratchpad `collect_week_cards.py` 의 boto3 직접 호출은 이 함수들로 바꾼다.
- **원문 재수집:** `core/retrieval` 의 fetch 를 쓴다. trafilatura 에 20s/180s 상한이 이미 있다.
- **발송:** ~~`scheduler/deliver.py:26` 에서 `send_html` 분리~~ → **11-07 생략.** 주간은 `weekly/run.py` 의 자기 발송 함수(`_ses_sender` — 인라인 PNG 용 SendRawEmail 포함)를 쓰므로 데일리 `deliver.py` 를 건드리지 않는 쪽이 "데일리 무변경"에 맞다. 표시 이름 `Field Experiment <SES_SENDER>` 는 그 함수가 넘긴다.
- **중복 방지 · 관리자 화면:**
  - `scheduler/sent_log.py` `DynamoSentLog` 에 user_id `weekly#<id>` 로 기록한다(데일리 키와 충돌하지 않는다).
  - `/admin/emails` 가 sent-log 를 Scan 하므로 주간 발송이 관리자 목록에 함께 보인다. 라벨 표시는 확인할 항목이다.
- **수신자:**
  - 1단계: `load_user(<admin user_id>)` 로 `briefing-users` 의 주소를 읽는다. `.env` 에는 user_id 만 두고 이메일은 두지 않는다.
  - 2단계: `briefing-users` 에 `weekly` opt-in 칸을 넣는다. `dynamo.py`(:30 · :226) · `config.py` · `profile.py` · `Form.tsx` 를 고친다.
- **배포:**
  - `runtime/deploy_runtime.py`: `stage_build_context` 가 `src/briefing` 을 통째로 싣는다. ~~IAM 에 새 표 하나만 더한다~~ → 표는 기존 `table/briefing-*` 와일드카드가 덮는다(불필요). **대신 `bedrock:ListInferenceProfiles` 가 필요하다**(11-07 발견): 게이트 `check_models` 가 이 API 를 부르는데 런타임 role 에 없어, 클라우드에선 ④절에 Claude 모델이 나올 때마다 조회 실패 FAIL(fail-closed) → 매주 격리. `runtime_env` 에 `WEEKLY_*` 전달도 필수(빠지면 `WEEKLY_ADMIN_USER_ID` 가 비어 매주 failed) — `WEEKLY_FIGURE` 만 제외(컨테이너엔 playwright 가 없어 그림 스펙 Opus 호출만 치르고 건너뛴다).
  - `scheduler/deploy_scheduler.py`: `SCHEDULES` 3개(시간당 무변경 + 주간 2개, `ScheduleExpressionTimezone=Asia/Seoul`)와 표 1개(`_ensure_table` 일반화).
  - ⚠ 함정: `deploy_scheduler` 를 다시 돌리면 `BRIEFING_DRY_RUN` 이 호스트 env 값(기본 1)으로 돌아간다 → 운영은 `BRIEFING_DRY_RUN=0 uv run python -m briefing.scheduler.deploy_scheduler` 로 실행하고 `get-function-configuration` 으로 확인.

## 5. 코드 폴더 구조

```
src/briefing/
+-- weekly/                  NEW 주간 모드
|   +-- collect.py   한 주 카드  <- core/stores
|   +-- select.py    씨앗        <- _run_author
|   +-- write.py     기사 + lint 재작성 루프
|   +-- lint.py      tools/lint_issue.py 이동
|   +-- terms.md     templates/terms.md 이동
|   +-- gate.py      lint · numeric · certify · 링크 · 모델
|   +-- render.py    md -> 메일 HTML (라이트)
|   +-- issues.py    briefing-weekly-issues 읽기/쓰기
|   +-- run.py       build | send | approve | pull
|   +-- prompts/     select_system.md · write_system.md
+-- runtime/agentcore_runtime.py   +weekly 분기 2
+-- scheduler/lambda_handler.py    mode = event
+-- scheduler/deliver.py           send_html 분리
+-- scheduler/deploy_scheduler.py  +스케줄 2 · 표 1
field-experiment/
+-- README.md · delivery-plan.md   브랜드 규칙 · 이 문서
+-- issues/                        pull 사본(공개 여부 결정)
+-- tools/lint_issue.py            CLI 껍데기 -> weekly.lint
tests/test_weekly_*.py             fake 주입(데일리 패턴)
```
- **표 `briefing-weekly-issues`:** PK 는 `run_date`, 항목은 `status`(building → ready · quarantined · failed → sent) · `issue_md` · `email_html` · `gate` · `seed` 다. 상태 전이는 조건부 update 로 한다. S3 는 쓰지 않는다(새 IAM 을 줄인다).

## 6. 실패 처리
- **데일리 run 지연:** 금요일 run_date 원장 행이 있는지 먼저 본다. 없으면 06:40 까지 5분 간격으로 다시 보고, 그래도 없으면 있는 카드로 만든다. 이 사실은 표 `gate` 에 기록한다.
- **lint FAIL:** 실패한 검사 번호만 주고 다시 쓰게 한다(최대 2회, 데일리 maker-checker 와 같은 모양). 그래도 FAIL 이면 `quarantined` 로 둔다.
  - 1단계: 표시를 달아 관리자에게 보낸다.
  - 2단계: 동료에게 보내지 않는다.
- **Codex FAIL(② 문장):** 그 문장을 빼고 다시 쓴다. 남으면 격리와 같이 처리한다.
- **생성 실패 · 시간 초과:** 07:00 send 가 `failed`/`building` 상태를 보면 관리자에게 "생성 실패: <단계>" 통지를 보낸다(조용한 실패를 두지 않는다).

## 7. 구현 순서 (각 단계 별도 승인 · 파일마다 before → after)
1. **(11-04~05) `weekly/` 패키지 + 테스트.** 로컬 backend 와 fake 를 주입한다. 데일리 파일은 아직 안 건드린다.
2. **(11-06) 로컬 dry-run.** 실제 원장 · 실제 author/codex 로 `build --dry-run` 을 돌린다. 발송은 하지 않는다.
   - ⚠ 호스트 로컬 `claude -p` 는 사용자 플러그인 훅이 실린다. 빈 HOME 으로 돌린다.
3. **(11-07, 토) 1-A.** 05:00 run 뒤 `build` → 관리자 확인 → `send`(관리자 1명). 손으로 쓴 1호와 품질 · 시간을 비교한다.
4. **(11-07 당김 — 코드 완료 `255f5d8`) 데일리 이음매 3곳 + 배포.**
   - lambda mode · 런타임 분기 · 스케줄/표 (+ `runtime_env` WEEKLY 전달 · IAM ListInferenceProfiles). `send_html` 은 생략(§4 발송).
   - 전체 `uv run pytest` 통과(912) → runtime(먼저 — 구 런타임은 모르는 mode 를 real 로 돌린다) · scheduler 재배포(05:00 KST 앞뒤 회피, `BRIEFING_DRY_RUN=0` 붙여서).
   - 클라우드에서 `weekly_build` 를 한 번 호출한다(build 에는 dry-run 이 없다 — 표에만 쓰고 메일을 안 보낸다) → 표 `ready` 확인 → `weekly_send` 를 dry_run 으로 호출해 수신자 · 제목만 본다. 발행일은 payload `issue_date` 로 준다(없으면 KST 오늘).
5. **(11-14, 토) 1-B 첫 자동 발송.** 07:00 도착과 표 상태 `sent` 를 확인한다.
6. **(3호 연속 통과 뒤) 2단계.** 법적 고칠 것 3개 · 사내 정책 → `weekly` 구독 칸 · approve · List-Unsubscribe(SESv2).

## 8. 검증
- **데일리 무변경:**
  - 기존 `uv run pytest` 가 전부 통과해야 한다.
  - 새 회귀 테스트: mode 가 없는 Lambda event(시간당 Input `{"source":…}`)는 `{"mode":"scheduled"}` 를 그대로 보낸다(`tests/test_scheduler.py`). ~~`make_ses_deliver` 인자 불변~~ 은 `send_html` 생략으로 대상이 없다(`deliver.py` 무변경).
- **주간:**
  - `uv run pytest tests/test_weekly_*`: fake 로 collect → send 와 상태 전이 · 중복 거부 · 실패 통지를 확인한다.
  - lint 이동 뒤 `field-experiment/issues/2026-10-31.md` 결과가 이동 전과 같아야 한다(PASS 2,996자).
- **배포 뒤:**
  - `aws scheduler get-schedule --name briefing-weekly-build` 로 시각 · 시간대를 확인한다.
  - 수동 호출 dry-run 이 `ready` 를 남기는지 본다.
  - 11-14 의 실제 수신과 sent-log `weekly#` 행을 확인한다.

## 9. 결정 필요
1. **공개 저장소의 `issues/`:** 1호 md 와 run 로그(발신 주소 포함)가 11-02 부터 공개되어 있다. 그대로 두고 기록할지, 공개 트리에서 뺄지 정한다(자동화 뒤 진실의 원천 = DDB 표).
2. ~~주간 작성 모델~~ → 2026-11-04 결정: 작성 · 선정 모두 Opus 5.5 high(`.env` `WEEKLY_AUTHOR_MODEL_ID` · `WEEKLY_SELECT_MODEL_ID`; README §10).
3. **2단계 승인 마감:** 기본안은 토 12:00 이다.
4. **도메인:** 3단계 전제이고, 사용자가 검토 중이다.
