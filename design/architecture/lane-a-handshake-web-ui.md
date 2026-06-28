# LANE-A 핸드셰이크 요청 — ④ Web UI 의존성 (2026-06-28, LANE B 발신)

> ④ Web UI(public-first 전환 깔때기) 구현 스펙: `docs/superpowers/specs/2026-06-28-web-ui-design.md`.
> 아래 4건은 ④ 가 *직접 만들 수 없는* 크로스-레인 의존성. 각 항목을 **얼린 계약**으로 고정하면
> LANE A·B 가 mock/seam 으로 **병렬 build** 가능(이 저장소의 DI-seam 토폴로지 — `decision-work-split`).
> **롱리드(H1·H3·H4)는 day-0 시작 권장** — ④ 의 체험·구독 단계가 여기에 게이트됨.

## 우선순위 한눈에

| | 항목 | 소유 | ④ 의 어느 단계를 막나 | 긴급도 |
|---|---|---|---|---|
| **H1** | SES production access + 검증 도메인 | **공유/ops(내가 신청)** | 모든 public 실발송(체험·구독) | 🔴 day-0 (~24h AWS 리뷰) |
| **H2** | `Source.category` 필드 + catalog 값 | **LANE A**(retrieval) | req#2 분야 그룹핑(폴백 있음) | 🟡 v1.0 폼 |
| **H3** | Cognito public app client + hosted-UI | **LANE A**(Gateway pool) | 구독(v1.2) | 🔴 day-0 (구독 게이트) |
| **H4** | `load_user`/`list_users` → DDB seam | **LANE A/③**(config·stores) | 구독→실발송(v1.2) | 🔴 day-0 (구독의 핵심) |

★ **v1.0 public 무지출 슬라이스(랜딩+폼+카탈로그+샘플)는 H2 만**(그것도 폴백 있음) — 즉시 착수 가능, 나머지는 후속 증분.

---

## H1 — SES production access + 검증 도메인 (공유/ops)

- **무엇**: 현재 SES sandbox → *검증된 주소(moongons)에만* 발송. public 개방엔 (a) production access 승인,
  (b) 검증 발신 **도메인**(DKIM) 필요. amazon.com 발신은 DMARC 경고 배너(현 ⑤ 운영 메모).
- **왜 ④ 를 막나**: 체험·구독 *둘 다* 임의 수신자에게 못 감 → public 깔때기 전체의 진짜 게이트(auth 아님).
- **누가**: 계정 레벨 요청이라 LANE-A 코드 아님 — **내가(LANE B) 신청 착수**. 도메인 선택만 합의 필요.
- **계약**: 검증 도메인명(예 `briefing.<도메인>`) 확정 → `SES_SENDER` 갱신. 그 전까진 ④ 는 dry-run/검증주소로 배선 검증.

## H2 — `Source.category` 필드 (LANE A · retrieval)

- **무엇**: `shared/retrieval/sources.py` 의 `Source` 데이터클래스에 `category: str` 추가 + `catalog.yaml`
  각 엔트리에 `category:` 값. ④ 의 `GET /catalog` 가 이걸로 체크박스를 **분야별 그룹**으로 묶음(req#2).
- **왜 ④ 가 못 하나**: 카탈로그 큐레이션은 LANE-A 소유(스펙: "임의 URL 금지·큐레이션"). ④ 가 category 를
  하드코딩하면 카탈로그 소유권 이중화 = 안티패턴.
- **얼린 계약**:
  ```python
  @dataclass(frozen=True)
  class Source:
      ...
      category: str          # 비어있지 않음. 예: "AI" | "Cloud/ML" | ...
  ```
  - 분류 택소노미(몇 개·이름)는 **LANE A 결정**. 제안 출발점: `AI` / `Cloud·ML` (현 6 출처면 2~3개로 충분).
  - 선택: `catalog_categories() -> list[str]`(정렬된 유니크) 헬퍼 — 없으면 ④ 가 sources 에서 유도.
- **폴백(블로킹 회피)**: category 가 아직 없으면 ④ 의 `GET /catalog` 는 **단일 "전체" 그룹**으로 응답 →
  v1.0 은 H2 없이도 ship 가능, H2 도착 시 그룹만 갈림.

## H3 — Cognito public app client + hosted-UI (LANE A · Gateway pool)

- **무엇**: LANE-A Gateway 의 기존 **M2M(machine) app client** 와 *별개로*, **인간 로그인용 public app client**
  추가. ④ 의 구독(`/profile`)이 이 client 로 JWT 발급.
- **왜 ④ 가 못 하나**: pool 은 LANE-A 가 소유·배포. M2M pool 은 보통 인간 가입 스키마/hosted-UI 가 없음.
- **LANE A 가 제공/설정할 것**(④ 가 손 못 댐):
  1. **hosted-UI 도메인** 부착(M2M pool 엔 보통 없음).
  2. **self sign-up** 활성 + email(또는 username) 스키마 + 검증메일(SES) + 비번/복구 정책.
  3. pool 이 ④ API 와 **동일 region/account**(us-east-1 / 057716757052) 확인.
  4. HTTP API JWT authorizer 의 `audience` = **public client id**(M2M 토큰을 `/profile` 에서 받을지 결정).
- **얼린 핸드셰이크(LANE A → B 전달 값)**:
  ```
  COGNITO_USER_POOL_ID  = us-east-1_xxxxxxxxx
  COGNITO_REGION        = us-east-1
  COGNITO_HOSTED_UI     = https://<domain>.auth.us-east-1.amazoncognito.com
  COGNITO_PUBLIC_CLIENT_ID = xxxxxxxxxxxxxxxxxxxx
  JWT_AUDIENCE          = <public client id>   # HTTP API authorizer
  ```
  → ④ 가 HTTP API JWT authorizer + 프론트 amplify/auth 설정에 그대로 사용.

## H4 — `load_user`/`list_users` → DDB seam (LANE A/③ · config·stores)

- **무엇**: 현재 라이브 파이프라인은 사용자를 **컨테이너에 baked 된 `users/*.yaml`** 에서 읽음
  (`load_user`/`list_users`, config.py). ④ 의 구독은 `briefing-users` DDB 에 프로필을 쓰는데,
  **load_user 가 DDB 를 읽도록 바뀌기 전엔 매일 발송에 0 반영** → 구독이 무의미.
- **왜 ④ 가 못 하나**: `shared/config.py`·`shared/stores/` 는 LANE-A/③ 소유(진실의 원천). ④ 가 거길 바꾸면
  trust 경계·소유권 침범.
- **얼린 계약(둘이 같은 store 를 쓰는 seam)**:
  - **테이블**: `briefing-users`(prefix `briefing-` = runtime/API IAM 와 일치 — 신규 권한 0).
  - **PK**: `user_id`(문자열). v1.2 데모 시드=`gonsoo`, public=Cognito `sub`.
  - **아이템 스키마**(C4 9필드 중 web-writable 7 + 경계):
    ```
    user_id (PK) · recipient · type · sources(StringSet|List) · depth · lens · send_hour(N) · timezone
    # skill_md 는 DDB 에 두되 web 입력 금지(trust 경계) — 기본 "" 또는 LANE-A 관리
    ```
  - **읽기측**(LANE A): `load_user(uid)`·`list_users()` 가 BACKEND=dynamo 일 때 `briefing-users` 를 read
    (`DynamoUserStore` in `shared/stores/`). **쓰기측**(LANE B): ④ API `PUT /profile` 가 같은 테이블·스키마로 write.
  - ⚠️ **seam 적용 후 runtime 재배포 필요**(load_user 코드 변경분 반영).
- **폴백/스코프**: H4 미준비면 ④ 의 v1.2 **구독은 보류**(또는 "행 저장만, 발송 미배선"으로 명시 ship). v1.0/v1.1 은 무관.

---

## 제안 진행

1. **H1** — 내가 SES production 신청 착수(도메인명만 합의). 🔴 지금.
2. **H3·H4** — LANE-A 가 day-0 착수(구독 게이트). 얼린 핸드셰이크 값/스키마 위 그대로면 ④ 병렬 진행 가능.
3. **H2** — v1.0 폼 전까지. 폴백 있어 블로킹 아님.
4. ④ 는 **v1.0 public 무지출 슬라이스(블로커 0)부터 즉시 구현** → 체험(H1) → 구독(H3·H4) 순.

질문/조정은 이 문서에 코멘트로. — LANE B
