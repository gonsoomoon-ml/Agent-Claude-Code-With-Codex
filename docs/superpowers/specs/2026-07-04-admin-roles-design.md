# Administrator 역할 v1 — 설계 스펙 (2026-07-04)

> 상태: **DRAFT** (승인 후 플랜 작성) · 관련: `docs/superpowers/specs/2026-06-28-web-ui-v1.2-subscribe.md`(PUT /profile) · `2026-06-28-web-ui-v1.1e-trial-cooldown-bypass.md`(TRIAL_TEST_EMAILS 선례)

## 0. 목표와 범위

- **목표:** admin 역할 도입 — v1 능력은 하나: **출처 선택 상한 해제** (일반 사용자 5개 → admin은 카탈로그 전체, 현재 6개).
- **왜 Cognito 그룹인가:** 사용자가 확인한 방향 — admin은 "자랄 씨앗"(향후 사용자 조회/관리·강제 재발송 API 등). env 허용목록(A안)이 아니라 처음부터 정식 authz 기반(C안)으로 시작해, 이후 능력 추가 시 판별부를 갈아탈 필요가 없게 한다.
- **v1 에서 만들지 않는 것(YAGNI):** `/admin/*` 라우트 일절, role 세분화(operator/viewer), DDB role 필드, admin UI 표시 이외의 프론트 변화.

## 1. 역할 모델 — source of truth = Cognito 그룹

- 웹 UI 풀 `us-east-1_ANfcEK61A`(briefing-users-gonsoo)에 그룹 **`admins`** 생성.
- 판별: 검증된 JWT 의 **`cognito:groups`** claim 에 `admins` 포함 여부 → `is_admin: bool`. Cognito 가 서명하므로 위조 불가.
- **DDB 에 role 을 저장하지 않는다** — `briefing-users` 아이템 무변경. 공개 API 로 자기 role 을 승격하는 mass-assignment 경로가 원천적으로 없다.
- **부트스트랩 런북** (풀이 현재 비어 있음 — 2026-07-04 확인):
  1. owner 가 웹 UI 에서 self-signup (풀에 Cognito 사용자 생성)
  2. `aws cognito-idp create-group --group-name admins --user-pool-id us-east-1_ANfcEK61A` (1회)
  3. `aws cognito-idp admin-add-user-to-group --user-pool-id us-east-1_ANfcEK61A --username <sub|email> --group-name admins`
  4. 재로그인 → 새 토큰에 그룹 claim 탑재
  - 이 런북은 `infra/README.md` 에 기록(회수 = `admin-remove-user-from-group`).

## 2. 정책 seam — role→능력 매핑의 단일 지점

```python
# src/briefing/webapi/policy.py (신규 — 순수 함수만)
DEFAULT_MAX_SOURCES = 5

def max_sources(is_admin: bool) -> int:
    """출처 선택 상한. admin 의 '무제한' = 카탈로그 전체(현재 6) — 실행 시간·비용의 자연 상한."""
    return len(CATALOG) if is_admin else DEFAULT_MAX_SOURCES
```

- 향후 관리 능력(사용자 조회, 강제 재발송 등)은 전부 이 파일에 함수 하나씩 추가된다 — 판별(claim)·능력(policy)·집행(route)의 3분리.
- `CATALOG` 는 `core/retrieval/sources.py` 의 기존 카탈로그(웹 catalog.py 가 이미 소비) — 카탈로그가 자라면 admin 상한도 자동으로 자란다.

## 3. 집행 지점 (전부 webapi 안)

| 위치 | 변경 |
|---|---|
| `webapi/app.py` | JWT 검증부에서 `cognito:groups` claim → `is_admin` 추출, 기존 DI 배선(claims→handler)으로 전달. **claim 이 없으면 항상 False** (기존 토큰·비로그인 안전) |
| `webapi/profile.py:14` | 하드코딩 `1 <= len(sources) <= 5` → `limit` **파라미터** (순수성 유지). 에러 메시지도 실제 limit 표기: `"출처를 1~{limit}개 선택하세요."` |
| `webapi/trial.py` | **무변경 — 전원 5 고정.** 체험은 비로그인·남용 표면이므로 role 무관 상한 유지 (승인된 결정) |
| `GET /profile` 응답 | `max_sources` 필드 추가 (로그인 사용자의 실효 상한) |
| `web/src/pages/Form.tsx` | `toggleSource(..., max)` 의 max 를 API 응답값으로 — `selection.ts` 는 이미 max 파라미터화돼 있어 로직 변경 0. 비로그인/응답 전 기본값 = 5 |

## 4. 불변식 (비협상)

1. **role 은 webapi 를 벗어나지 않는다** — core/pipeline/gate/certifier 는 role 의 존재를 모른다 (신뢰 경계·decorrelation 무접촉). 파이프라인은 이미 카드 격리로 N개 소스를 처리한다.
2. 서버 검증(`profile.py`)이 진실 — UI 의 max 는 UX 일 뿐.
3. `PUT /profile` 은 지금처럼 선호 필드만 쓴다 — role 관련 어떤 것도 쓰지 않는다.
4. role 회수 시: 이미 저장된 >5 프로필은 읽기·발송 유지(재검증 없음), **다음 쓰기부터** 5 제한. (아침 발송이 갑자기 죽는 일이 없어야 함)
5. trial 경로는 role 을 조회조차 하지 않는다.

## 5. 미래 로드맵 (v1 미구현 — seam 만 준비됨)

- `GET /admin/users` (전체 사용자 조회) · `POST /admin/resend` (강제 재발송 런북의 API 화 — runtime payload override invoke).
- 패턴 동일: `cognito:groups` 판별 → `policy.py` 능력 함수 → route 집행. **admin API 도 core 신뢰 경계는 불변.**

## 6. 테스트 (전부 fake DI — AWS 불요)

- `policy.py` 단위: `max_sources(False)==5`, `max_sources(True)==len(CATALOG)`
- `profile.py`: limit 파라미터 경계 (5개 초과 거부 @limit=5 · 6개 허용 @limit=6 · 카탈로그 밖 key 거부는 기존 유지)
- `app.py` 배선: fake claims 에 `cognito:groups=["admins"]` 유/무 → is_admin 전달 확인; claim 부재 시 False
- trial 회귀: admin 여부와 무관하게 5 초과 거부 (불변식 5)
- `web/`: Form 이 API 의 max_sources 를 toggleSource 에 전달 (기존 Form 테스트 패턴)

## 7. 검증 사다리

pytest(기존 176+신규 동과) → `webapi/run.py` 로컬 uvicorn 스모크 → `deploy_api.py` 재배포 → 부트스트랩 런북 실행(가입+그룹 추가) → **실제 로그인으로 6개 소스 저장 성공 + 일반 계정(그룹 미소속)으로 6개 저장 거부** 확인.

## 8. 구현 확인 항목 (플랜 단계에서 검증)

- `app.py` 의 JWT 검증이 ID token 과 access token 중 무엇을 받는지 — `cognito:groups` 는 양쪽에 다 실리지만 추출 코드는 실물 기준으로.
- `GET /profile` 이 프로필 미존재(신규 가입자) 때도 max_sources 를 돌려주는 응답 shape.
