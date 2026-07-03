# 시스템 재설치 계획 (one-command install / reinstall)

> **상태: 계획(PLAN) — 아직 미구현.** "거의 끝난" 시스템을 *낯선 사람도 자기 AWS 계정에 한 명령으로 세울 수 있게* 만드는 부트스트랩 설계. 데모 → 제품의 경계.
> 발단: 컴포넌트별 재현 번들은 다 있으나 **실행 순서(DAG)와 컴포넌트 간 값 전달**을 사람이 머리로 꿰어야 함.

## 문제 — 조각은 있는데 "지휘자"가 없다

각 컴포넌트는 이미 멱등 재현 번들(CFN + 셸/orchestrator)을 가짐. 빠진 건 **위상정렬된 실행 순서**와 **`.env` 를 통한 값 전달의 표준화**.

## 핵심 통찰 — `.env` 가 이미 통합 버스(integration bus)

각 deploy 가 출력(테이블명·GATEWAY_URL·COGNITO_*·RUNTIME_ARN)을 내고 하류가 그걸 읽는다. → **새 도구가 아니라, 기존 번들을 DAG 순서로 엮는 얇은 지휘자(conductor)** 만 있으면 된다. 리라이트 0.

## 의존 DAG (실행 순서)

```
  preflight ─ aws creds · uv sync · region · .env(.env.example 복사) 편집
      │
      ▼
  [1] DDB stack (infra/deploy_ddb.sh, SEED=1) ──▶ CACHE/LEDGER/SOURCE/USERS_TABLE ─┐
      │                                            + users/*.yaml 시드(H4)          │
      ├───────────────┬───────────────────┐                                        │ .env
      ▼               ▼                     ▼                                       │ (버스)
  [2a] Gateway①   [2b] Auth H3        (seed 는 [1] 에 포함)                          │
   gateway.py      deploy_users.sh                                                 │
   cognito+Lambda  cognito-users                                                   │
   +gw+provider    hosted-UI/signup                                               │
      │GATEWAY_URL   │COGNITO_* (5값) ──────────────────────────────────────────▶ │
      │OAUTH_*       │                                                             │
      └──────┬───────┘                                                             │
             ▼                                                                     │
  [3] Runtime② (deploy_runtime.py) ◀── BACKEND·tables·gateway·models·SES 읽기 ──────┘
      │  build→ECR→Runtime + IAM(Bedrock·SES·DDB Scan)
      │  BRIEFING_RUNTIME_ARN ───────────────────────────────────────────────▶ .env
      ▼
  [4] Scheduler⑤ (deploy_scheduler.py)  EventBridge→Lambda→invoke runtime(scheduled)
      ▼
  [5] Web UI④ (webapi/deploy_api.py + deploy_web.py)   ◀ optional(full)
      ▼
  [verify] invoke_runtime --mode smoke · scripts/e2e_gateway.py · curl /health
```

## 컴포넌트 manifest (지휘자가 호출할 순서·입출력)

| 단계 | 번들 | 입력(.env/env) | 출력 | 출력 방식 ⚠️ | 멱등 |
|---|---|---|---|---|---|
| [1] DDB③ | `infra/deploy_ddb.sh` (SEED=1) | region·prefix | CACHE/LEDGER/SOURCE/USERS_TABLE | **print** | ✓ |
| [2a] Gateway① | `gateway/deploy_gateway.py` | region·DDB tables | GATEWAY_URL·GATEWAY_TARGET·COGNITO_SCOPE/CLIENT_ID/TOKEN_URL·OAUTH_PROVIDER_NAME | **print** | ✓ |
| [2b] Auth H3 | `infra/auth/deploy_users.sh` | region·CALLBACK_URLS | COGNITO_USER_POOL_ID·HOSTED_UI·PUBLIC_CLIENT_ID·JWT_AUDIENCE | **print** | ✓ |
| [3] Runtime② | `runtime/deploy_runtime.py` | region·BACKEND·tables·models·SES_SENDER·gateway | BRIEFING_RUNTIME_{NAME,ARN,ID} | **writeback** | ✓(auto_update) |
| [4] Scheduler⑤ | `scheduler/deploy_scheduler.py` | RUNTIME_ARN·schedule | (EventBridge rule) | — | ✓ |
| [5] Web④ | `webapi/deploy_api.py` + `deploy_web.py` | COGNITO_*·api | API URL·CloudFront domain | — | ✓ |
| [manual] SES H1 | *(AWS 콘솔/CLI 신청 — 스크립트 불가)* | — | SES_SENDER | 수동 | ✗ |

## 견고하게 만드는 3가지

1. **계층(profile)** — `install.sh --profile core|full`.
   - *core* = [1]DDB+seed → [3]runtime → [4]scheduler. **매일 브리핑이 동작**(claude+codex, SES verified-주소).
   - *full* = core + [2a]Gateway①(off-by-default 역량) + [2b]auth + [5]Web UI④.
   - 안 쓰는 건 안 깐다. Gateway 는 어차피 `GATEWAY_ENABLED` 로 런타임 opt-in.
2. **멱등·재개(resumable)** — 거의 모든 번들이 멱등(`--no-fail-on-empty-changeset`·reuse-if-exists·`auto_update_on_conflict`). N단계 실패 → 고치고 재실행하면 이어짐.
3. **수동 한 칸 명시** — **SES production(H1)** 은 AWS 리뷰(~24h)라 스크립트 불가. 설치기가 그 지점에서 *멈추고 안내*("SES production 승인 후 `SES_SENDER` 갱신 → 재실행"). 정직한 게이트(silent failure 금지).

## 어려운 부분 (정직한 리스크)

- **`.env` 출력 방식 불일치** — `deploy_runtime` 만 writeback, 나머지는 print. 지휘자가 **stdout 캡처→`.env` 갱신**으로 통일하거나, 각 번들에 writeback 헬퍼를 추가해 표준화해야 함. (가장 큰 작업.)
- **순서 정확성** — [3]runtime 은 [1]tables + (full 시)[2a]gateway 값을 *읽어* 빌드. **seed([1]에 포함)는 runtime 재배포 전**이라야 함(H4 — 빈 DDB→발송 0). DAG 위반 시 조용히 깨짐.
- **비밀 취급** — `COGNITO_CLIENT_SECRET`(Gateway M2M)은 로컬 전용. 설치기가 `describe-user-pool-client` 로 *조회*만, 절대 커밋·로그 금지(.env gitignore).
- **계정 횡단성** — 템플릿은 이미 `${AccountId}`·`${DemoUser}` 파라미터화됨(타 계정 OK). `.env.example` 가 모든 노브를 담는지 *완전성* 점검 필요.
- **docker 불필요** — 전 컴포넌트가 zip(manylinux wheel) 또는 CodeBuild 빌드라, 설치 호스트에 docker 없어도 됨(이 환경에서 검증된 제약).

## 재설치(reinstall) = teardown + install

짝꿍 **`teardown.sh`** — 스택을 **역순 삭제**([5]→[1]; runtime delete → scheduler rule → cognito/gateway → DDB stack). 멱등 install 과 합치면 *깨끗한 재설치*. (주의: DDB 삭제 = 데이터 소실 — `--keep-data` 플래그로 테이블 보존 옵션.)

## 산출물 (구현 시)

1. `scripts/install.sh` — preflight + DAG 지휘자(profile·resume·stdout→.env 통일).
2. `scripts/teardown.sh` — 역순 삭제(`--keep-data`).
3. (선택) `scripts/stacks.manifest` 또는 install.sh 내 배열 — 위 manifest 를 코드화(단계·번들·.env 키).
4. `.env.example` 완전성 보강(누락 노브 채움).
5. `INSTALL.md` — `git clone → .env 편집 → bash scripts/install.sh --profile … → verify` 절차 + SES 수동 단계.
6. 각 print-방식 번들에 `.env` writeback 표준화(또는 지휘자가 캡처).

## 검증 (install 끝 자동)

- `core`: `invoke_runtime --mode smoke`(plumbing) → `--mode scheduled --dry-run`(실 load_user/DDB).
- `full`: + `scripts/e2e_gateway.py`(Gateway 3도구 byte-identical) + `curl <API>/health` + hosted-UI `302→login`.

## 왜 지금 (PRD 정합)

PRD 의 aiops 레퍼런스(`Project Setting Environment: UV·.env·folder structure·재현`)가 지향하는 바와 정확히 같음 — **"거의 끝남"을 "낯선 사람도 한 명령으로 선다"로** 바꿔 데모→제품 경계를 넘는다. 관련: `work-split-interfaces.md`(레인 토폴로지) · `lane-a-handshake-web-ui.md`(컴포넌트 의존).
