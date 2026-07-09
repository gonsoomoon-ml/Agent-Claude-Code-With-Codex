# Admin 모니터링 대시보드 — 설계 스펙 (Phase 1)

- **상태:** DRAFT
- **날짜:** 2026-07-08
- **PRD:** [`design/prd/prd_admin.md`](../../../design/prd/prd_admin.md)
- **참조 코드(Phase 2 북극성):** Deep Insight — `https://github.com/aws-samples/sample-deep-insight` (Data Analysis · AgentCore Gateway · Strands · AgentCore Runtime · Prompt)
- **신뢰 경계 가드:** [`src/briefing/webapi/CLAUDE.md`](../../../src/briefing/webapi/CLAUDE.md)

## 1. 목표 (Goal)

이 서비스가 잘 동작하는지 **모니터링**하고 운영 액션을 수행하는 admin 기능. **Phase 1 = "발송된
이메일 리스트" 대시보드**: 로그인한 admin 이 발송된 전체 이메일을 보고, 각 항목의 *기본 통계 · 포함
기사 수 · 작업 소요시간 · 발송 시각 · 소요 비용* 을 확인한다.

Phase 2+(Deep Insight식 자연어 데이터분석 에이전트)는 **본 스펙 범위 밖** — 별도 스펙에서 다룬다.

## 2. 사전 조사 결과 (PRD "만들기 전 비용·시간 조사" 이행)

두 개의 리서치로 코드베이스를 실측했다(요약; 전체 근거는 조사 당시 에이전트 리포트).

**비용 — 이메일 1건:**
- 배포된 모델: **author = Claude Sonnet 4.6**(`core/config.py` 기본값이 런타임에 그대로 통과 —
  Opus 아님), **certifier = OpenAI GPT-5.5**(`~/.codex/config.toml`, Bedrock).
- base ≈ **$1.10/이메일**(범위 $0.15~$5.5). **~99% 가 LLM 토큰** — SES+Lambda+AgentCore+DDB
  합쳐 < $0.05(반올림 오차).
- **1위 비용 동인 = GPT-5.5 certifier** — `entailment` 주장마다 1콜($5/$30, reasoning 출력).
  숫자 주장은 `gate.reroute_claim_types` 로 **무료 결정론 산술 경로**라 억제됨.
- **총비용 ≠ 한계비용:** 사실층은 콘텐츠주소·전 사용자 공유(캐시) → 같은 소스 2번째 수신자
  이메일의 한계비용 ≈ **$0.02~0.12**. (그래서 대시보드의 "비용" = 실제 발생 비용이면 캐시히트가
  자연히 $0 근처로 뜬다.)

**소요시간 — 이메일 1건:** 콜드 **~9~13분**(관측된 658s 앵커) / 웜 **~20초**(카드캐시 히트).
완전 순차 · 콜드 CLI 서브프로세스 체인(author draft → 주장별 `codex exec` → interp). Lambda
15분 하드캡 때문에 스케줄러는 fire-and-return, 실작업은 런타임 백그라운드 스레드(≤8h).

**데이터 현실(핵심):** **지속되는 per-send 감사 레코드가 없다.** 유일한 발송 흔적
`briefing-sent-log` 은 `(user_id, run_date)` **중복방지 불리언**뿐(`scheduler/sent_log.py:41-43`).
비용은 `claude -p --output-format json` 봉투에 `total_cost_usd`·`usage`·`duration_ms` 로 이미
오는데 `author.py:254-262 _extract_claude_result` 가 `.result` 만 남기고 폐기. 소요시간은
호출별 ms 를 재지만 DEBUG stderr 로만. SES 응답(MessageId)은 `deliver.py:33` 에서 버려짐.
→ **결론: Phase 1 = "읽기 UI" 가 아니라 "계측 + UI".** 계측 대부분은 새 측정이 아니라
*버리던 값을 durable 하게 한 줄 더 쓰기*.

## 3. 확정된 결정 (사용자 승인)

- **C1 · "비용" 의 의미 = 실제 발생 비용.** 캐시히트 카드는 실제로 LLM 콜이 없으므로 $0 근처.
  대시보드가 곧 원가 관측기가 된다("소요된 비용" 의 문자 그대로 해석).
- **C2 · 정밀도 = v1 은 author-정확 + certifier-추정 + 인프라-무시.** author 비용은 봉투에서
  정확히 나온다. certifier(codex)는 usage 파싱이 번거로워 v1 은 **콜 수 × 단가 추정**(`≈` 표기),
  정밀 파싱은 v1.1.
- **C3 · 저장 = `briefing-sent-log` 필드 확장**(`sent_at·recipient·published·quarantined·
  duration_ms·cost_usd·status·message_id`). 구독자 수십 명 규모 → v1 은 **Scan**(GSI 불필요),
  규모 커지면 `run_date` GSI.

## 4. 아키텍처 — 세 조각 (신뢰 경계 보존)

```
[core/·scheduler/·stores/]        [webapi/admin.py]            [web/src/pages/Admin.tsx]
 role-blind 계측                    admin-gated 읽기 API           React /admin 테이블
 (전 사용자 기록)          ──▶      GET /admin/emails    ──▶      authedFetch 렌더
 UsageRecorder + 타이머              require_admin(403)
 widened sent-log audit row
```

**불변식(비협상):** 계측은 **role 을 전혀 모른다** — 전 사용자에 대해 비용/시간/카운트를 기록할
뿐. "admin 이라 이걸 본다"는 판단은 오직 `webapi` 의 읽기 라우트에서만 일어난다. 이로써
`role 은 webapi 밖으로 안 나간다`(루트 CLAUDE.md, decorrelation) 가 자연히 지켜진다.

## 5. 데이터 모델

### 5.1 감사 레코드 (widened `briefing-sent-log`)

DynamoDB 는 스키마리스 — 키(`PK=user_id`, `SK=run_date`)는 불변, 아래 속성만 추가로 기록.

| 속성 | 타입 | 출처 |
|---|---|---|
| `user_id`, `run_date` | S, S | 기존 키(중복방지) — 그대로 |
| `sent_at` | S (ISO-8601 UTC) | 발송 순간 dispatch 루프에서 스탬프 |
| `recipient` | S | `UserBriefing.recipient` |
| `published` | N | `UserBriefing.published` (= "포함 기사 수") |
| `quarantined` | N | `UserBriefing.quarantined` |
| `duration_ms` | N | `UserBriefing.duration_ms` (신규 carrier) |
| `cost_usd` | N | `UserBriefing.cost_usd` (신규 carrier; author-정확+certify-추정) |
| `status` | S | `"sent"` (v1). skipped/quarantined-only 는 Phase 1.1 |
| `message_id` | S | SES 응답 `MessageId` (deliver 반환값) |

**멱등:** 같은 `(user_id, run_date)` 재발송 시 덮어씀(기존 `mark_sent` 계약 유지). `already_sent`
게이트가 앞단에서 순차 재실행을 막으므로 실제 덮어쓰기는 강제 재발송 시에만.

### 5.2 `UserBriefing` carrier 필드 (`core/pipeline.py:34-42`)

frozen dataclass 에 **기본값 있는 필드 2개 추가**(기존 keyword 생성·208 테스트 무영향):

```python
@dataclass(frozen=True)
class UserBriefing:
    ...
    cost_usd: float = 0.0      # 이 사용자 iteration 에서 실제 발생한 비용(캐시히트=0)
    duration_ms: int = 0       # 이 사용자 iteration 벽시계 시간
```

### 5.3 UsageRecorder (신규, 선택 주입 — `ledger`/`card_cache` 와 동일 패턴)

- `core/stores/` 에 경량 mutable sink. `add(cost_usd: float, ms: int)` + 스냅샷.
- author `_extract_claude_result` 가 봉투의 `total_cost_usd`(정확)를 record.
- certifier 콜 지점이 콜 수를 record → v1 은 콜 수 × 추정 단가.
- `run_briefing` 이 **사용자 iteration 전후 델타를 스냅샷** → `UserBriefing.cost_usd`.
  (사실층 memo/cache 로 인해 첫 사용자만 실제 콜 비용을 "지불", 나머지는 0 — C1 의도와 일치.)
- pure 테스트(recorder 미주입)에서는 `cost_usd=0.0` — 결정론 유지.

## 6. 통합 지점 (구현이 손댈 정확한 위치)

| # | 파일:함수 | 변경 |
|---|---|---|
| 1 | `core/authoring/author.py:254 _extract_claude_result` | 봉투의 `total_cost_usd`/`usage`/`duration_ms` 를 recorder 에 기록(결과 텍스트 반환은 불변) |
| 2 | `core/verification/certifier.py` (entailment 콜 지점) | 콜 수를 recorder 에 기록(v1 추정 단가) |
| 3 | `core/pipeline.py:44 run_briefing` / `UserBriefing` | recorder 선택 인자 + 사용자별 `time.monotonic()` 타이머 → `cost_usd`·`duration_ms` carrier 채움 |
| 4 | `scheduler/deliver.py:21 make_ses_deliver` | `deliver` 가 SES 응답을 **반환**(현재 `None` 폐기). `DeliverFn` 타입을 `Callable[[Any], dict | None]` 로 |
| 5 | `scheduler/dispatch.py:47-56` 루프 | `resp = deliver_fn(b)` 캡처 → `sent_at` 스탬프 + audit 레코드 구성 → 확장된 `mark_sent` 호출 |
| 6 | `scheduler/sent_log.py:41 mark_sent` | 시그니처 `mark_sent(user_id, run_date, *, record: dict | None = None)` — record 있으면 병합 기록(기본 None=기존 동작, 하위호환) |
| 7 | `webapi/admin.py` (신규) | `APIRouter` — `GET /admin/emails`; `require_admin(req)`(=`_claims` 재사용 + `is_admin` 아니면 403) |
| 8 | `webapi/app.py` | `app.include_router(admin_router)` |
| 9 | `webapi/deploy_api.py` (Lambda IAM) | webapi Lambda 역할에 `briefing-sent-log` **읽기(Scan/GetItem/Query)** 추가 — 현재 users+trials 만 있음 |
| 10 | `web/src/pages/Admin.tsx` + `web/src/App.tsx` | 신규 `/admin` 라우트 + 발송 이메일 테이블; `auth/session.ts` 에 id_token group 디코드 헬퍼(게이팅 UX) |

## 7. API 계약 — `GET /admin/emails`

- **인증:** JWT id-token(기존 authorizer) + `require_admin` → admin 아니면 **403**.
- **쿼리(선택):** `?date=YYYY-MM-DD`(주면 그 `run_date` 만 필터; 생략 시 전체), `?limit`(기본 200).
- **200 응답:**
```json
{
  "emails": [
    {"user_id":"…","recipient":"a@x.com","run_date":"2026-07-08",
     "sent_at":"2026-07-08T07:00:12Z","published":5,"quarantined":0,
     "duration_ms":662000,"cost_usd":1.08,"status":"sent","message_id":"01000..."}
  ],
  "totals": {"count":3,"cost_usd":2.41,"avg_duration_ms":420000}
}
```
- **소싱:** v1 = `briefing-sent-log` **Scan**(작은 테이블), `sent_at` desc 정렬, `cost_usd` 근사(`≈`).

## 8. 프론트엔드

- 신규 라우트 `/admin`(`App.tsx`). 게이팅: `auth/session.ts` 가 id_token payload 의
  `cognito:groups` 를 디코드해 admin 에게만 `/admin` 노출(UX) — **API 가 최종 집행**(방어심도).
- 발송 이메일 테이블(수신자·발송시각·기사수·소요시간·비용·상태) + 합계 줄. 기존 다크 테마 토큰
  (`:root`) 재사용. 비용은 `≈$1.08` 표기(certify 추정 반영).

## 9. 오류 처리·엣지 케이스

- **dry-run 은 audit 를 안 남긴다** — `mark_sent` 는 실제 발송(`should_deliver`+`!already_sent`)
  경로에서만 호출. 스케줄러 `BRIEFING_DRY_RUN` 기본값 footgun(재배포 시 리셋) 주의 — 프로덕션은
  실발송이어야 audit 가 쌓인다.
- **백필 없음** — 계측 이전 발송은 데이터가 없다. 대시보드는 계측 배포 이후 발송부터 채워진다.
- **skipped/quarantined 가시성 = Phase 1.1** — 이들은 `mark_sent` 를 안 타므로 v1 audit 에
  없다(별도 write 경로 필요). v1 은 PRD 문자 그대로 "발송된 이메일" 만.
- **certify 비용 = 추정** — codex usage 미파싱. `cost_usd` 는 author-정확 + certify-추정 합.
- **비admin 접근 = 403**(API), 프론트는 `/admin` 미노출.

## 10. 테스트 (TDD)

- **pytest:** UsageRecorder 누적·스냅샷; `mark_sent(record=…)` 확장 기록 + 하위호환(record=None);
  `make_ses_deliver` 반환값·`dispatch` audit 구성; `run_briefing` 이 carrier 채움(recorder 주입)
  + pure 경로 `cost_usd=0.0`; `GET /admin/emails` admin 200 / 비admin 403(`tests/test_webapi_
  trial_route.py` 의 is_admin 격리 회귀 패턴 재사용).
- **vitest:** `Admin.test.tsx` — authedFetch 모킹, 테이블·합계 렌더, 비admin 게이팅.
- **불변식 회귀:** 계측이 `is_admin`/role 을 core 로 들이지 않음(기존 trial 격리 테스트 유지).

## 11. 범위 밖 (명시적)

- Phase 1.1: skipped/quarantined 행, certify 정밀 비용(codex usage 파싱), `run_date` GSI.
- Phase 2(별도 스펙): Deep Insight식 자연어 분석 에이전트(`src/briefing/admin/` 모듈 + Gateway
  read-tool + **certifier 를 citation-integrity 로 재사용**). 강제 재발송·사용자 프로비저닝 UI.
- AgentCore 컴퓨트 per-email 정밀 배분(배치 과금 — 무시 가능).

## 12. 폴더 결정

Phase 1 은 새 모듈 폴더가 아니다 — 계측은 `core/`·`scheduler/`·`stores/` 확장, 읽기는
`webapi/admin.py`(라우터 파일 1개), UI 는 `web/src/pages/Admin.tsx`. 새 코드 모듈 폴더
`src/briefing/admin/` 은 Phase 2(에이전트 서브시스템)에서 정당화된다(`gateway/`·`scheduler/`·
`webapi/` 와 동급 형제). 태스크용 별도 docs 폴더는 없음 — 본 스펙/플랜 날짜 쌍 + `docs/README.md`
색인이 관습.
