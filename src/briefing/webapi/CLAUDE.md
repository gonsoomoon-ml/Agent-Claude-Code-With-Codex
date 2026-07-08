# CLAUDE.md — webapi (admin/role 신뢰 경계)

이 파일은 `src/briefing/webapi/` 트리를 편집할 때 자동 로드된다. 목적: **admin/role
불변식(trust boundary)이 부주의한 수정으로 *조용히* 깨지지 않도록** 한곳에 못 박는다.
루트 [`/CLAUDE.md`](../../../CLAUDE.md) 를 대체하지 않는다 — 여기 없는 모든 것(듀얼 하니스·
decorrelation·clean-dir 격리·빌드/테스트 전반·inclusion test·언어 규칙)은 루트를 따른다.

> ⚠️ 이 트리와 프론트엔드 `web/src/` 는 **형제(sibling)** 다. 이 파일은 `web/src/` 편집 시
> 로드되지 않는다 — 프론트 admin 규약은 아래 "프론트엔드" 절 + `web/src/pages/Form.admin.test.tsx`.

## 불변식 — role 은 webapi 밖으로 나가지 않는다 (비협상)

`판별(discern) → 능력 매핑(map) → 집행(enforce)` 3분리. role 은 이 세 지점에만 존재한다.

- **판별** = `authz.py:claims_from_request` 가 Cognito id-token 의 `cognito:groups` 에서 `is_admin` 계산.
  그룹 파싱은 **반드시** `authz.py:_parse_groups` 경유 — HTTP API v2 authorizer 가 배열 claim 을
  `"[admins]"` 문자열로 평탄화하므로 `str(claim) == "admins"` 같은 직접 비교는 금지.
- **능력 매핑** = `policy.py` **단 한 곳**. role → 능력은 여기서만 값이 된다.
  새 관리 능력은 **`policy.py` 에 함수 하나씩** 추가 (예: `max_sources(is_admin)`).
- **집행** = route(`app.py` / 신규 `admin.py`). route 는 claim 만 읽고, 능력값을 순수 검증기
  (`profile.py:validate_profile`)에 **평범한 값으로** 주입한다.
- `is_admin`/role 은 runtime payload·ledger·profile 레코드·`core/`·gate·certifier 에 **절대 넣지
  않는다.** core/gate/certifier 는 role 의 존재를 몰라야 한다(decorrelation).
  회귀 테스트: `tests/test_webapi_trial_route.py` — admins claim 이어도 `/trial` 은 5 상한 유지.

**계측 코드 주의:** admin 대시보드용 비용/소요시간 계측(`core/`·`scheduler/`·`stores/`)은
**role-blind** 여야 한다 — 전 사용자에 대해 기록하고, "admin 이라 이걸 본다"는 판단은 오직
`webapi` 의 읽기 라우트에서만 일어난다. 계측에 `is_admin` 을 끌어들이면 위 불변식이 깨진다.

## 인증·role 출처

- role = Cognito 웹 풀 `us-east-1_ANfcEK61A` 의 `admins` 그룹. 그룹 관리는 배포 스크립트 밖 CLI
  런북(`infra/README.md`).
- **함정:** `admin-create-user` 는 반드시 `Name=email_verified,Value=true` — 아니면
  `authz.py:claims_from_request` 가 401('email not verified'). self-signup 은 의도적 차단.
- 그룹 변경은 **재로그인(새 토큰)** 후 반영. admin 회수는 기존 저장된 프로필을 축소하지 않음
  (다음 `PUT /profile` 에서 5 상한 재검증).
- Cognito 풀 id / client id 는 `deploy_api.py:_ensure_http_api` 와 `web/src/auth/config.ts`
  **양쪽**에 하드코딩 — 풀 변경 시 둘 다 수정.

## 프론트엔드 (형제 트리 — 여기서 자동 로드 안 됨)

- SPA 라우트 `web/src/App.tsx`(`/`, `/setup`, 신규 `/admin`). id_token 은 **메모리 전용**
  (`web/src/auth/session.ts`, XSS 방어), `authedFetch` 가 `Authorization: Bearer` 부착.
- SPA 는 오늘 토큰의 groups 를 디코드하지 않는다 — admin 은 backend 가 내려주는 값으로만 표면화.
  admin 페이지 게이팅은 클라이언트 group 디코드(UX) + **API 이중 집행**(방어심도).
- 새 admin 화면/능력은 기존 seam: `policy.py` 함수 + `app.py`/`admin.py` JWT-authorized route
  + SPA `authedFetch`.

## 검증

- 백엔드: `uv run pytest` · `uv run ruff check src tests`
  (admin: `tests/test_webapi_{policy,profile_route,trial_route,admin_route}.py`).
- 프론트: `web/` 에서 `npm test`(admin: `Form.admin.test.tsx`·`pages/Admin.test.tsx`·`auth/session.test.ts`), 빌드 `npm run build`.
- 배포: `deploy_api` → `deploy_web` (순서·조건·IAM 은 [`./README.md`](./README.md)).

## 포인터 (여기서 재서술 금지)

- 루트 [`/CLAUDE.md`](../../../CLAUDE.md) — 듀얼 하니스·decorrelation·clean-dir 격리·언어 규칙.
- [`docs/README.md`](../../../docs/README.md) — admin 기능 색인 + 스펙/플랜 스트림(상태).
- 진행 중 스펙: [`docs/superpowers/specs/2026-07-08-admin-monitoring-design.md`](../../../docs/superpowers/specs/2026-07-08-admin-monitoring-design.md) — admin 모니터링 대시보드(Phase 1).
- 이전 admin 작업: `docs/superpowers/specs/2026-07-04-admin-roles-design.md`.
