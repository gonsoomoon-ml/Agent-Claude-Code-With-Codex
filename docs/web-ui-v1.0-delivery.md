# ④ Web UI — v1.0 전달 기록 (Delivery Record)

> 상태: **SHIPPED + LIVE** · 날짜: 2026-06-28 · 레인: LANE B (Delivery & UX) · main 머지: `8ed4b34`
> 관련 문서: 스펙 [`docs/superpowers/specs/2026-06-28-web-ui-design.md`] · 플랜 [`docs/superpowers/plans/2026-06-28-web-ui-v1.0-public-slice.md`] · LANE-A 핸드셰이크 [`design/architecture/lane-a-handshake-web-ui.md`]

## 1. 무엇을 전달했나 (Scope)

verify-before-publish 데일리 브리핑(②runtime·③DDB·⑤Scheduler·SES)의 **public-first 전환 깔때기**의 첫 증분 —
**인증·LLM·SES·DDB 없는 무지출(no-spend) public 슬라이스**:

- **랜딩**: 서비스 소개 + 정적 샘플 브리핑 미리보기(iframe).
- **폼(`/setup`)**: 분야별 미디어 선택(체크박스, **최대 5개**) · 발송 시각(**6/7/8 KST** 라디오) · 이메일 입력.
- **읽기 전용 API**: `GET /catalog`(폼 데이터) · `GET /sample`(샘플 HTML) · `GET /health`.
- 체험하기·구독하기 버튼은 v1.0 에선 **비활성("곧 제공")** — v1.1/v1.2 에서 활성화.

목표: **SPA ↔ API ↔ CORS 배관을 실제 배포로 de-risk** (체험·구독의 토대). 달성 확인됨(§5).

## 2. 라이브 엔드포인트 · AWS 리소스

| | 값 |
|---|---|
| 웹 (S3+CloudFront) | `https://dqizh0gi9cp2q.cloudfront.net` |
| API (Lambda+HTTP API) | `https://k1y2gmk6nj.execute-api.us-east-1.amazonaws.com` |
| 리전 / 계정 | `us-east-1` / `057716757052` |

| 리소스 | 이름/ID |
|---|---|
| Lambda (FastAPI/Mangum) | `briefing-webapi` (x86_64, BasicExecution role only) |
| Lambda IAM role | `briefing-webapi-lambda-role` |
| API Gateway HTTP API | `briefing-webapi-http` (`k1y2gmk6nj`), `$default` AWS_PROXY 라우트 |
| S3 버킷 (비공개) | `briefing-web-057716757052-us-east-1` |
| CloudFront 배포 | `E2CUZ0XOLVJ7YL` (OAC, 403/404→`/index.html`) |

> `.env`(gitignored)에 `BRIEFING_API_URL`·`BRIEFING_WEB_URL`·`BRIEFING_WEB_BUCKET`·`BRIEFING_CF_DIST_ID` 등 기록.

## 3. 아키텍처

```
[React 19 SPA]  (S3 비공개 + CloudFront OAC)
   │ public GET: /catalog · /sample · /health
   ▼  CORS = FastAPI CORSMiddleware (앱 레벨, 배포+로컬 공통)
[API Gateway HTTP API] ── $default AWS_PROXY ──> [FastAPI Lambda (Mangum 어댑터)]
                                                     └─ briefing.shared (CATALOG·LENS_LIBRARY) 재사용
```

- **카탈로그 단일 소유**: `GET /catalog` 는 `briefing.shared.retrieval.sources.CATALOG` 를 읽음(하드코딩 금지).
- **category forward-compat**: `getattr(s,"category","")` → LANE-A 가 `Source.category`(H2) 추가 전엔 단일 "전체" 그룹, 추가 시 코드 변경 0.
- **무지출 불변식**: Lambda IAM = BasicExecution 만(bedrock/ses/dynamodb 권한 0).

## 4. 코드 구조

```
src/briefing/webapi/         # 스펙의 "api/" (scheduler/ 미러)
  catalog.py                 # build_catalog() — 폼 JSON (전체 폴백)
  app.py                     # FastAPI: /catalog /sample /health + CORSMiddleware
  sample_briefing.html       # 정적 샘플 (랜딩 iframe)
  lambda_main.py             # handler = Mangum(app)
  run.py                     # 로컬 uvicorn
  deploy_api.py              # boto3: Lambda + HTTP API + CORS
  deploy_web.py              # boto3: S3 + CloudFront OAC + 빌드 동기화
  teardown_webui.sh          # 역순 정리 (CloudFront 는 수동 disable→delete)
web/                         # Vite + React 19 + TS SPA
  src/lib/selection.ts       # toggleSource(MAX-5) 순수 로직
  src/components/SourcePicker.tsx
  src/pages/{Landing,Form}.tsx · App.tsx (라우터) · api.ts · types.ts
tests/test_webapi_{catalog,app,lambda}.py · web/src/**/*.test.{ts,tsx}
```

## 5. 검증 증거

- **단위/통합**: pytest(webapi) + vitest(web) — TDD(RED→GREEN)로 작성. 결합 main 트리에서 **pytest 101 passed** + **vitest 11 passed**.
- **HTTP·보안 (curl)**: 랜딩/`/setup`/없는경로 = 200(SPA 폴백) · HTTP→HTTPS 301 · **S3 직접 접근 403**(OAC 격리) · CORS `*` · `x-cache: Hit from cloudfront`.
- **실 브라우저 (Playwright headless)**: 랜딩 iframe 이 `/sample` cross-origin 로드 · `/setup` 폼이 라이브 `GET /catalog→[200]` 으로 채워짐(콘솔 에러 0) · **MAX-5 라이브**(5선택 → 카운터 5/5 → 6번째 disabled) · 체험/구독 버튼 disabled.
- 최종 전체-브랜치 리뷰(opus): **Ready to merge = YES** (0 Critical / 0 Important).

## 6. 비자명했던 수정 4건 (systematic debugging)

1. **arm64 → x86_64**: Lambda zip 의 `pydantic_core` 네이티브 휠은 `uv pip install --target` 호스트(x86_64) 빌드 아키와 일치해야 함 — arm64 는 `Runtime.ImportModuleError`. (⑤ scheduler 는 boto3-only 순수 파이썬 zip 이라 arm64 OK 였던 것과 대비.)
2. **tsconfig `types` 에 `vite/client`**: `import.meta.env` 는 Vite 주입 타입이라 순수 `tsc -b` 가 모름 → 추가해야 빌드.
3. **`_ensure_http_api` integration check-before-create**: `create_integration` 무조건 호출 시 재배포마다 integration 누수(고아) → URI 매칭 재사용으로 멱등화.
4. **S3 `BlockPublicPolicy=true`**: OAC 정책은 service-principal+SourceArn 이라 비-public → True 여도 수락되며 미래 실수 방어(defense-in-depth).

## 7. 배포 / 운영

```bash
# API 배포 (Lambda + HTTP API)
uv run python -m briefing.webapi.deploy_api
# Web 배포 (S3 + CloudFront + 빌드 동기화; 선행: deploy_api 의 BRIEFING_API_URL)
uv run python -m briefing.webapi.deploy_web
# 로컬 개발: API
uv run python -m briefing.webapi.run        # :8000
# 로컬 개발: Web (Vite 프록시로 /catalog·/sample → :8000)
cd web && npm install && npm run dev
# 정리 (CloudFront 는 ~15분 disable→delete 라 수동 단계 안내 포함)
bash src/briefing/webapi/teardown_webui.sh
```

- **재배포 멱등**: role/API/Lambda/bucket/OAC/distribution 모두 check-before-create. CloudFront 전파 ~15분.
- **CORS 좁히기(v1.1)**: Lambda env `WEB_ORIGIN` 을 CloudFront 도메인으로 설정.

## 8. Git

- `lane-b/delivery` → **main `8ed4b34`** 머지(`--no-ff`). 머지 시 **LANE-A 의 ① Gateway 작업과 결합**(서로소 파일, 충돌 0) → origin push 완료.
- `lane-b/delivery` worktree/브랜치는 harness 소유라 보존(삭제/제거 안 함).

## 9. LANE-A 의존 + 다음 증분

| 핸드셰이크 | 게이트 |
|---|---|
| **H1** SES production access + 검증 도메인 | 모든 public 실발송(체험·구독) — ~24h 롱리드 |
| **H2** `Source.category` 필드 + catalog 값 | 분야 그룹핑(현재 "전체" 폴백) |
| **H3** Cognito public app client + hosted-UI | 구독(v1.2) |
| **H4** `load_user`/`list_users` → `briefing-users` DDB seam | 구독→실발송(v1.2) |

- **v1.1 체험하기**: 더블옵트인("확인 후 1통") · runtime `mode=trial`(재배포) · 남용 예산 kill-switch · `POST /trial`+`/verify`. 의존: H1.
- **v1.2 구독하기**: Cognito 인증 · `GET/PUT /profile`(JWT). 의존: H3·H4.
- **최종 리뷰 권고(비차단, v1.1 때 흡수)**: HTTP API 스로틀(무인증 표면 비용 cap, `/trial` 예산과 함께) · Form a11y(이메일 `aria-label`·라디오 label/aria 중복) · `_build_web` `npm ci` · deploy_web list 페이지네이션 주석 · `/trial` 가 AWS 호출 추가 시 **boto3 번들 필수**.
