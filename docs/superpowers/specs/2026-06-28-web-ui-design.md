# ④ Web UI — 설계 스펙 (2026-06-28, LANE B) · rev2 (red-team 반영)

## 컨텍스트 (왜)

verify-before-publish 데일리 브리핑(②runtime · ③DDB · ⑤Scheduler·SES)은 라이브지만 설정은 손으로
`users/<id>/profile.yaml` 편집해야 한다. ④ 는 **public-first 전환 깔때기**의 웹 UI:
**랜딩(소개) → 폼(출처·시각·이메일) → 체험하기(확인 후 1통) → 구독하기(인증, 매일 자동)**.
검증·저장은 Python/DDB 소유(C4 불변), 프론트는 얇은 층. 스택: React+Vite+TS SPA · FastAPI Lambda · API Gateway HTTP API.

## ⚠️ 솔직한 v1 현실 (red-team 확정)

- **라이브 파이프라인은 컨테이너에 baked 된 `users/*.yaml` 에서 사용자를 읽는다**(DDB 아님). 따라서 `briefing-users`
  DDB 에 써도 **LANE-A 가 `load_user`/`list_users` 를 file→DDB 로 바꾸기 전엔(H4) 매일 발송에 반영 0**. (Lambda 가
  컨테이너 RO FS 에 못 쓰니 파일 폴백 비현실적.) → **구독→발송 배선은 H4 이후**.
- **SES sandbox** 라 v1 은 *검증된 주소(예 moongons)에만* 실제 발송(체험·구독 둘 다). public 의 진짜 게이트 = **SES
  production 승인(H1, ~24h) + 검증 도메인**, auth 아님.
- 따라서 **v1 = 데모**: 무지출 public 슬라이스는 즉시 가치, 체험/구독의 *실발송*은 SES·seam 게이트.

## 목표 (증분 v1.0→v1.2) / 비목표

| 증분 | 내용 | 크로스-레인 블로커 |
|---|---|---|
| **v1.0 public 무지출 슬라이스** | 랜딩(소개+정적 샘플) · 폼(분야→미디어 MAX5 · 시각 6/7/8 KST · 이메일) · `GET /catalog` | **없음** (먼저 ship) |
| **v1.1 체험하기** | 더블옵트인(확인 후 1통) · runtime `mode=trial` · `POST /trial` · 남용 예산 | H1(SES) · Plan A 재배포 |
| **v1.2 구독하기** | Cognito 인증 · `PUT/GET /profile` · 매일 자동 | H1 · H3(Cognito) · H4(load_user→DDB) |

**비목표(v2)**: lens·depth UI 노출(v1=기본 general/full 숨김) · 결과뷰(`GET /briefings`) · 대규모 rate-limit/captcha.

## 아키텍처 (정정: API Lambda 가 invoke, 브라우저 아님)

```
[React SPA] ──(S3 비공개 + CloudFront OAC)
   │ public: catalog/sample/trial(+verify)   구독: Cognito 로그인(LANE A pool) → JWT
   ▼  (CORS: allow-origin = CloudFront 도메인)
[API Gateway HTTP API] ──(라우트별 인증)──> [FastAPI Lambda (Web Adapter)]
   │ public: GET /catalog·GET /sample·POST /trial·GET /trial/verify     │
   │ 🔒JWT : GET /profile·PUT /profile                                   │
   ▼                                          ┌──────────────┬──────────┘
[DynamoDB: briefing-users(PK=user_id) · briefing-trials(cap/status)]    │
   └─ ⑤·파이프라인 read (H4 이후)        체험: API Lambda 가 invoke_agent_runtime(mode=trial) → SES
[Cognito User Pool] = LANE A Gateway pool 재사용(+ Web UI public app client)
```
★ **브라우저는 runtime 을 직접 invoke 하지 않는다**(SigV4/IAM + ARN 노출 + 무인증 spend 트리거 = 금지). 항상 API Lambda 경유.

## 컴포넌트

| 디렉토리 | 책임 |
|---|---|
| `web/` | Vite + React + **TS** SPA(Landing·Form·Confirm·TrialSent). React Router · **Zod**(C4 UX 미러, 서버 authoritative) · aws-amplify/auth(구독). |
| `api/` | **FastAPI + Lambda Web Adapter**. **C4 검증기 신규 작성**(config.py:93 TODO — `catalog_keys()`·`lens_keys()` *재사용*하되 email/≤5/send_hour/depth-enum 은 **새로**). trial 시 `invoke_agent_runtime` (⑤ `lambda_handler` 패턴 복사). |
| `infra/` | `ddb.yaml` 에 `briefing-users` + `briefing-trials` 추가(**이름 prefix `briefing-` = runtime/API IAM 와 일치**). `api/deploy_api.py`(boto3, ②⑤ 미러). |
| `runtime/` | `agentcore_runtime.py` 에 **`mode=trial`** 추가(② lane, **재배포 필요**). |

## 데이터 모델

- **`briefing-users`(DDB, PK=`user_id`)**: C4 9필드 중 web 입력분(recipient·type·sources[]·depth·lens·send_hour·timezone).
  **`skill_md` 미수신**(trust 경계). 이메일=PII→DDB 만. PK: v1.2 데모=`gonsoo`(시드), public=Cognito `sub`
  (★ 키 모양 바뀜 = "마이그레이션 0" 아님, 단지 *데모 데이터 폐기*).
- **`briefing-trials`(DDB)**: trial 상태/cap. item = `{trial_id, email, sources, status(pending_verify|sent|failed), date}` + TTL 24h.
- **★ H4 의존**: `load_user`/`list_users` 가 `briefing-users` 를 읽도록 LANE-A/③ 가 `DynamoUserStore` seam 구현해야
  구독이 발송에 닿음(+ runtime 재배포). 미준비면 v1.2 보류.

## API 계약 (HTTP API · 혼합 인증 · CORS 필수)

| 메서드/라우트 | 인증 | 요청 → 응답 | 검증 |
|---|---|---|---|
| `GET /catalog` | public | → `{categories:[{name, sources:[{key,name,lang}]}], lenses, depths, send_hours:[6,7,8], max_sources:5}` | — (category 없으면 단일 "전체" 그룹 폴백) |
| `GET /sample` | public | → **커밋된 정적** 샘플 브리핑 HTML | — |
| `POST /trial` | public(throttle+budget) | `{sources[], email, lens?, depth?}` → `{trial_id, status:"pending_verify"}` | email 형식·sources⊆catalog∧≤5·**전역 일일 예산** |
| `GET /trial/verify?token` | public | 확인 클릭 → 발송 트리거 → `{status:"sending"}` | token 유효·미사용 |
| `GET /profile` | 🔒 JWT | → 내 C4 설정 | — |
| `PUT /profile` | 🔒 JWT | `{sources[], email, send_hour, lens?, depth?}` → `{status:"saved"}` | 전체 C4 검증(email·sources⊆catalog≤5·send_hour∈{6,7,8}·lens∈lens_keys·depth∈enum) |

**검증 = Python 신규 작성**(config.py TODO 구현). 프론트 Zod 는 UX 미러. **CORS**: `deploy_api.py` 가 HTTP API
CorsConfiguration(allow-origin=CloudFront 도메인, methods, `Authorization`/`Content-Type`) 설정.

## 화면 플로우 (체험하기 = 더블옵트인)

1. **Landing**(public): 소개 + 정적 샘플.
2. **Form**(public): `GET /catalog` 분야별 체크박스 · **라이브 MAX-5 카운터**(5개 도달 시 나머지 비활성) · 시각 라디오(6/7/8 KST) · 이메일. 버튼: **체험하기 · 구독하기**.
3. **체험하기** → `POST /trial`(검증·예산) → **확인 메일 발송** → "확인 메일을 보냈어요. 클릭하면 브리핑이 도착합니다."
   → 사용자 클릭 → `GET /trial/verify` → API Lambda 가 `invoke_agent_runtime(mode=trial)` → 브리핑 SES 발송.
4. **구독하기** → Cognito hosted UI → 복귀 후 `PUT /profile`(인증) → "구독 완료".

## runtime `mode=trial` (② lane · 정정)

payload `{mode:"trial", sources[], recipient(email), lens?, depth?}` → **9필드 전부**로
`UserConfig(id="trial", recipient=email, type="ai-news", sources=tuple, depth=depth or "full", lens=lens or
"general", send_hour=0, timezone="Asia/Seoul", skill_md="")` 조립 → `add_async_task` → 백그라운드:
`store, card_cache, _ = make_stores(settings)` → `run_briefing(settings, store, [trial_user], card_cache=card_cache,
ledger=None)`(★ store **필수** 통과·card_cache 재사용·ledger=None 으로 원장 오염 회피) → `make_ses_deliver` 발송
→ trial-status DDB 갱신 → complete. accepted 즉시 반환.
**실패 피드백**(red-team P1-2): SES 거부·**QUARANTINE-only(`should_deliver`=false→무발송)**·LLM 에러를 status 에
기록 → UI 가 표시, 또는 "오늘 새 소식 없음" 폴백 메일로 *항상 무언가* 도착.

## 인증 (Cognito — LANE A pool 재사용 · H3 핸드셰이크)

LANE A Gateway pool 의 M2M client 와 **별개의 public app client** 추가. **LANE-A 가 제공할 것**(④ 가 못 만듦):
(a) hosted-UI 도메인, (b) self sign-up + email schema + 검증메일 + 비번/복구 정책, (c) **동일 region/account**,
(d) HTTP API JWT authorizer `audience` = public client id. **얼린 핸드셰이크**(pool id·region·domain·client id·audience).
구독 시점 게이트(랜딩 아님): JWT 가 `/profile` 보호, public 라우트 무인증.

## 체험하기 더블옵트인 + 남용 모델 (구체 수치)

- **확인-후-발송**: 봇이 임의 이메일을 돌려도 *받은편지함을 소유해야 클릭* → 무인증 spend 차단. v1 sandbox 에선
  옵트인 = **SES email-identity verification**(주소 검증 = 발송 가능 + 소유 증명 동시 해결); v2 production 에선 우리 확인메일.
- **전역 일일 예산 kill-switch**: 단일 DDB 카운터, 초과 시 `POST /trial` → 503(이메일 회전 무관 무한 spend 차단).
- **수치(기본값, 배포 시 조정)**: 이메일당 2통/일 · API GW route rate=2/s burst=5 · **전역 trial 예산 ≈ 50통/일**(초과 시 503).
- ③ card cache = 반복 `(source,lens)` LLM 0회(단 `curate` 는 매번 최대 5 fetch+trafilatura — 예산 산정에 반영).

## 크로스-레인 핸드셰이크 (day-0 롱리드)

| | 내용 | 게이트 |
|---|---|---|
| **H1** | SES production 승인 + 검증 도메인(AWS 리뷰 ~24h) | 모든 public 발송(체험·구독) |
| **H2** | LANE-A: `Source.category` 필드 + `catalog.yaml` 값(제안 AI/Cloud·ML) | req#2 분야 그룹핑(없으면 "전체" 폴백) |
| **H3** | LANE-A: Cognito public app client + hosted-UI + self-signup + 핸드셰이크 | 구독(v1.2) |
| **H4** | LANE-A/③: `load_user`/`list_users` → `briefing-users` DDB seam(+ runtime 재배포) | 구독→발송 |

## 분해 + 빌드 순서 (4 plans)

- **Plan A — runtime `mode=trial`**(② Python): 분기 추가(9필드·store 수정) → 로컬 fake 테스트 → **컨테이너 재배포**(선행).
- **Plan B — `api/`**(Python/FastAPI/pytest): (1) **C4 검증기 + `GET /catalog`(H2)+`GET /sample`** — 무지출·무클라우드 → (2) `POST /trial`+`/verify`(Plan A live·H1·예산·InvokeAgentRuntime IAM·boto3 번들) → (3) `GET/PUT /profile`+JWT(H3·H4).
- **Plan C — `web/`**(React+Vite+TS/vitest): (1) Landing+Form(MAX5) → (2) 체험하기(확인·실패 UX) → (3) 구독(amplify/auth·H3).
- **Plan D — infra/deploy**(`deploy_api.py` boto3 ②⑤ 미러): (1) `ddb.yaml`+테이블 → (2) Lambda+HTTP API+**CORS**+public 라우트+API role IAM(InvokeAgentRuntime+DDB+logs) → (3) S3+CloudFront/OAC+web 빌드 → (4) JWT authorizer(H3) → (5) `teardown_api.sh`(CloudFront ~15분·S3 비우기 선행).

**임계 경로:** H1/H3/H4 ‖ Plan A(재배포) → Plan B.1+D.1-2(무지출 public) → Plan C.1 → Plan B.2+D wiring(체험) → Plan C.2 → [H3·H4] → Plan B.3+D.4+C.3(구독). **무지출 public 슬라이스 먼저 ship**(블로커 0, SPA↔API↔CORS 배관 de-risk).

## 배포 / 패키징 / 테스트

- API Lambda zip: FastAPI + Web Adapter + `briefing` 패키지(`catalog.yaml`·`pyyaml` 포함, import 시 `_load_catalog()`) + **boto3 번들**(⑤가 겪은 bedrock-agentcore data-plane 누락 회피).
- 테스트: api pytest(검증기·catalog 그룹핑·trial 예산·payload, fake DDB) · web vitest(MAX5·payload) · e2e(dry-run trial + 검증주소 실 trial).

## v2 / 보류
결과뷰 · lens·depth UI · public 개방(H1 완료) · 본격 rate-limit/captcha · `GET /sample` 동적화.
