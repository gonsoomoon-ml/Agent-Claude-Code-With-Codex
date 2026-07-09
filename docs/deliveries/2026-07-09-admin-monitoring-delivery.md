# Admin 발송 모니터링 대시보드 (Phase 1) — 전달 기록

- **날짜:** 2026-07-09
- **상태:** SHIPPED·LIVE (프로덕션 배포 완료 · **첫 실발송 데이터 확인 대기**)
- **스펙:** [`docs/superpowers/specs/2026-07-08-admin-monitoring-design.md`](../superpowers/specs/2026-07-08-admin-monitoring-design.md)
- **플랜:** [`docs/superpowers/plans/2026-07-08-admin-monitoring.md`](../superpowers/plans/2026-07-08-admin-monitoring.md)
- **PRD:** [`design/prd/prd_admin.md`](../../design/prd/prd_admin.md)
- **신뢰경계 가드:** [`src/briefing/webapi/CLAUDE.md`](../../src/briefing/webapi/CLAUDE.md)

## 무엇을 배포했나 (as-built)

발송된 이메일마다 **기사 수·작업 소요시간·발송 시각·실제 비용**을 durable 하게 계측하고, admin 이 로그인해 `GET /admin/emails` 로 조회하는 **React `/admin` 대시보드**. 세 조각(신뢰경계 보존):

1. **role-blind 계측** (`core/`·`scheduler/`·`stores/`) — `UsageRecorder`(author `claude -p` 봉투 `total_cost_usd` 정확 + gate.`verify_card` 의 certify 추정) → `run_briefing` 사용자별 델타/타이머 → `UserBriefing.cost_usd`·`duration_ms` → `dispatch` 가 SES 응답(MessageId) 캡처 후 `briefing-sent-log` 에 audit row 기록(비용은 `Decimal`).
2. **admin-gated 읽기** (`webapi/authz.py` claims 추출 + `webapi/admin.py`) — `GET /admin/emails`: `require_admin` 아니면 **403**, Scan → `Decimal`→`float` → 합계.
3. **UI** (`web/src/pages/Admin.tsx`) — 발송 테이블 + 합계 줄, `isAdmin()` UX 게이팅(실집행은 backend).

**핵심 불변식:** role/is_admin 은 `webapi/authz` 한 곳에만 — `core`/gate/certifier/pipeline 은 role 을 모른다(grep 확인). 계측은 전 사용자 role-blind.

## 머지

- `feat/admin-monitoring` → `main` (머지 커밋 `ee51d6a`). 분기돼 있던 병렬 작업(card-title·The Decoder)은 branch 가 content-superset 이라 `-X theirs` 로 충돌 없이 통합.
- 머지 결과 검증: `uv run pytest` **232 passed / 3 skipped** · `ruff` clean.

## 배포 (프로덕션 057716757052 / us-east-1)

| 명령 | 결과 |
|---|---|
| `uv run python -m briefing.webapi.deploy_api` | webapi Lambda 갱신 + IAM statement `SentLogTableRead`(Scan/GetItem/Query on `briefing-sent-log`) 부여. HTTP API `k1y2gmk6nj` $default 프록시로 `/admin/emails` 노출 |
| `uv run python -m briefing.webapi.deploy_web` | SPA 빌드(VITE_API_BASE=…k1y2gmk6nj) → S3/CloudFront `dqizh0gi9cp2q` push + invalidation |
| `uv run python -m briefing.runtime.deploy_runtime` | 계측 코드로 런타임 재빌드(ECR `…:20260709-132634-550`) → **READY**, ARN 불변 `briefing_agent-b9uh7rDAqL` |

**⚠️ footgun 회피:** `deploy_scheduler` 는 실행하지 않았다 — 그 스크립트는 `BRIEFING_DRY_RUN=1` 로 리셋해 실발송을 멈춘다(그러면 audit 도 안 쌓임). 런타임 재배포는 dry-run 미변경·ARN 불변이라 안전.

## 엔드투엔드 배선 확인 (config-level)

```
EventBridge Scheduler  briefing-hourly-tick  → ENABLED
  → briefing-scheduler-dispatch  (BRIEFING_DRY_RUN=0=실발송 · RUNTIME_ARN=briefing_agent-b9uh7rDAqL 일치)
     → 런타임(계측)  → briefing-sent-log audit row
        → GET /admin/emails (no-auth 스모크 = 401, 라우트+게이트 라이브·404 아님)
           → CloudFront /admin
```

- `/health` = 200, `/admin/emails`(무인증) = **401**.
- 스케줄러 dry-run=0(실발송), 런타임 ARN 일치, tick ENABLED 확인.

## 접속

- **`https://dqizh0gi9cp2q.cloudfront.net/admin`** (CloudFront 전파 ~15분 후 안정).
- 로그인: Cognito 웹 풀 `us-east-1_ANfcEK61A` 의 **`admins` 그룹** 사용자만(아니면 "관리자 전용"). 그룹 추가: `aws cognito-idp admin-add-user-to-group --user-pool-id us-east-1_ANfcEK61A --username <email> --group-name admins` 후 재로그인.

## 운영 유의점 (경계·한계)

- **첫 실발송 전까지 표는 비어 있음이 정상** — 계측을 지금 켰으므로 **배포 이후의 실발송**부터 행이 생긴다. 과거 발송은 **백필 불가**.
- **dry-run 은 audit 미기록** — 프로덕션이 실발송(`BRIEFING_DRY_RUN=0`)이어야 쌓인다.
- **trial 발송은 audit 미기록** — 별도 status store(`briefing-trials`). 대시보드는 daily 구독 발송만 본다.
- `status` 는 v1 에서 `"sent"` 리터럴(SES 하드에러는 레코드 전 예외 → 미감사). Phase 1.1 후보.
- 합계(totals)는 `?limit`(기본 200) 적용 후 표시분 기준 — 소규모 v1 엔 무해.

## 검증 요약

- 백엔드 `uv run pytest` 232 passed / 3 skipped · `ruff` clean(제어자 재확인).
- 프론트 `npm test`(vitest) 41 green · `tsc -b && vite build` OK.
- 리뷰: 11 태스크 per-task 리뷰 + T4/T7/T10 수정 루프 + **opus 최종 whole-branch 리뷰 = "Ready to merge: YES"**(5개 데이터흐름 seam 추적·신뢰 불변식 grep 확인).

## 비차단 후속 (open)

- **실-DI recorder pass-through 가드 단위테스트** — `_process → produce_card/interpret_card(recorder=)` 의 partial 배선이 현재 e2e 로만 커버(주입 fake 가 우회). 리팩토링 시 `recorder=` 누락을 잡을 단위테스트 권장(opus 도 acceptable·후속 권장 판정).
- Phase 2(별도 스펙): Deep Insight식 자연어 분석 에이전트(`src/briefing/admin/` + Gateway read-tool + certifier 를 citation-integrity 로 재사용) · 강제 재발송·프로비저닝 UI.

## 배포 재현 (요약)

```bash
uv run python -m briefing.webapi.deploy_api      # /admin/emails + sent-log IAM
uv run python -m briefing.webapi.deploy_web      # /admin SPA → CloudFront
uv run python -m briefing.runtime.deploy_runtime # 런타임 계측(audit row 기록)
# deploy_scheduler 금지 — dry-run 리셋 footgun
```
