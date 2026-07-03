# 폴더 구조 리팩토링 v3 — 설계 스펙 (2026-07-03)

## 0. 목표와 배경

- **동기:** AI 코딩 도구가 생성한 코드베이스를 사람이 이해하기 쉽게(structure = architecture map), 이후 기능 확장이 앉을 자리가 명확하게.
- **핵심 방향:** `shared/` → `core/` 리네임 + 하니스 스테이지 분리(authoring/verification), Gateway 어댑터 승격, 컨테이너 자산 분리, 문서 정리. **import 루트 `briefing.`은 불변.**
- **검증 이력:** 이 스펙의 모든 판단은 3차 검증을 통과했다 —
  1. 원안 적대 검증 (9 에이전트: 6 리더 + 구조/마이그레이션/반박 비평) → 블로커 2건·허위 주장 3건 발견, 원안 수정
  2. AgentCore 컨테이너 빌드 체인 전수 추적 → **PROVEN WORKING** (신규 블로커 0)
  3. 하위 그룹핑 설계↔반박 대결 → `runtime/container/`·`gateway/` 합류만 생존, 나머지 기각
- **머지 자체는 프로덕션 무영향:** 배포된 아티팩트 4개(AgentCore 컨테이너·gateway/webapi/scheduler Lambda)는 옛 레이아웃의 동결 사본. 위험은 각 아티팩트의 **첫 재배포**에 있다 (§8 사다리 필수).

## 1. 최종 트리 (v3)

```
src/briefing/
├── core/                          ← shared/ 리네임
│   ├── __init__.py · pipeline.py · gate.py · config.py · render.py
│   ├── lenses.py + lenses.yaml    # 쌍으로 루트 (import-time 로드, webapi도 소비)
│   ├── _debug.py
│   ├── prompts/                   # template.py + author_system.md + supervisor.md 통째로 유지
│   │                              # (template.py:14 가 자기 디렉토리에서만 .md 로드 — 분리 금지)
│   ├── authoring/                 # __init__.py(신규) + author.py       (claude -p 하니스)
│   ├── verification/              # __init__.py(신규) + certifier.py    (codex exec 하니스)
│   ├── retrieval/                 # 무변경: sources·curation·relevance·catalog.yaml·gateway_client
│   └── stores/                    # 파일 무변경, cache.py import 만 재작성
│
├── runtime/                       ← 이름 유지 (agentcore 리네임 기각)
│   ├── __init__.py · agentcore_runtime.py · supervisor.py · _trial.py · _smoke.py
│   ├── deploy_runtime.py · invoke_runtime.py · teardown.sh    # flat 잔류 (deploy/ 폴더 기각)
│   └── container/                 # Dockerfile · requirements.txt · claude_config.json · codex_config.toml
│
├── gateway/                       ← 신설 어댑터 (⑤번째 배포 단위 = .gw_build.zip)
│   └── __init__.py(신규) + gateway_handler.py + deploy_gateway.py
│
├── scheduler/ · webapi/ · local/  # flat, 무변경
│
infra/                             # 유지 (ops/ 신설 기각) + README.md 인덱스 추가
scripts/ · users/ · web/           # 무변경
tests/                             # flat 유지 (미러링 기각)
design/
├── prd/ · research/ · architecture/ (make_slide.py·pptx 는 docs/deck/ 으로)
└── ux/                            ← 신설: email-ux-mockup.md + email_ui.png (쌍으로)
docs/
├── superpowers/ · deliveries 문서  # 무변경 (역사 기록은 stale 로 둔다)
├── deck/                          # 기존 + make_slide.py + solution-architecture.pptx 합류
└── assets/                        ← 신설: v1.0-setup-form-max5.png (참조 0건 확인됨)
```

**폴더별 README.md (5~15줄) 신설 7곳:** `src/briefing/core/`, `runtime/`, `gateway/`, `scheduler/`, `webapi/`, `local/`, `infra/`(배포 단위 → deploy/teardown 스크립트 + CFN 인덱스).

## 2. 결정 대장 (무엇이 채택/기각됐고 왜)

| # | 결정 | 판정 | 근거 요약 |
|---|---|---|---|
| D1a | `shared/` → `core/` 리네임 | **채택** | 패키징은 디렉토리 단위(hatch `packages=["src/briefing"]`) — 빌드 설정 무변경. 단 sed 금지, §4 모듈별 매핑 필수 |
| D1b | harness/ 해체 → authoring/ + verification/ | **채택(근거 수정)** | 기계적으로 깨끗(빈 `__init__`, 공유 코드 0, `_last_json_object` 의도적 중복). **주의: decorrelation 의 실제 메커니즘은 폴더가 아니라** 4필드 Envelope 화이트리스트(gate.py:41-48) + clean-dir subprocess(certifier.py:122-134)다. 폴더는 가독성 + 향후 import-lint 훅 |
| D1c | lenses.py+yaml, prompts/ 는 core 루트 | **채택** | lenses 는 webapi/catalog.py 도 소비(authoring 소속 아님); prompts 는 로더 제약(§5-7) |
| D1d | core/delivery/ (render.py 단독) | **기각** | 단일 모듈 패키지 + `scheduler/deliver.py`(진짜 SES 발송)와 이름 충돌 |
| D2 | runtime/ → agentcore/ 리네임 | **기각** | `briefing.agentcore.agentcore_runtime` 말더듬 + CMD·ENTRYPOINT_REL·스테이징 앵커 3곳 변경 + 컨테이너 재배포 강제. 이득은 동의어 |
| D3 | gateway_handler.py → `gateway/` 승격 + deploy_gateway.py 동반 | **채택** | 자체 Lambda 배포 단위가 남의 패키지에 숨어 있던 유일한 진짜 결함. deploy_gateway 는 runtime 에서 import 0, `parents[3]` 깊이 불변, 단일 파일 폴더 규칙도 해소. **블로커 수정 §5-1 동반 필수** |
| D4 | deploy 스크립트 → ops/ 집결 | **기각(연기)** | 6개 스크립트가 3방향 동시 파손(패키지 밖 상대 import 불법·`parents[3]` 산술·옆자리 데이터 경로) + tests/test_runtime.py 가 deploy 헬퍼 10여 개 직접 import + **루트 산술은 테스트 미커버, 실패는 조용함**. install.sh 페이즈에서 배포단위별 재검토. 지금은 infra/README.md 인덱스로 대체 |
| D5 | tests/ 미러링 | **기각** | flat 31파일 + 전역 유일 basename + conftest/`__init__` 없음 = pytest 기본 모드에 정확히 안전한 형태. 접두어가 곧 미러 |
| D6 | 문서·자산 정리 | **채택** | §7. 비용 ≈ 0, 라이브 무접촉 |
| S1 | runtime/container/ (자산 4종) | **채택** | 코드 변경 **1줄**(deploy_runtime.py:118), 실수 시 배포 전 FileNotFoundError 로 크게 터짐(loud-early) |
| S2 | runtime/·webapi/·scheduler/ 에 deploy/ 폴더 | **기각** | `deploy_*` 파일명 접두어가 이미 균일 컨벤션(grep 이득 0). `parents[N]` 실수는 조용히 실패 — `load_dotenv()` 가 루트 .env 를 어차피 찾아 배포는 "성공"하고 writeback 만 유령 `src/.env` 에 낙하(7/2 인시던트와 같은 silent-failure 계열) |
| S3 | core 루트 8파일 | **flat 확정** | 혼잡이 아니라 의도된 척추. config·gate·render 는 어댑터 전역이 소비 — 더 파면 import churn 만 증폭 |

## 3. 이동 맵 (파일 단위)

| 현재 | 이동 후 | 비고 |
|---|---|---|
| `src/briefing/shared/**` | `src/briefing/core/**` | git mv; 내부는 아래 3건만 재배치 |
| `shared/harness/author.py` | `core/authoring/author.py` | + 빈 `__init__.py` 신규 |
| `shared/harness/certifier.py` | `core/verification/certifier.py` | + 빈 `__init__.py` 신규. **author/certifier 자체는 import 수정 0줄** (한 단계 위 상대 import, 깊이 불변) |
| `shared/harness/__init__.py` | 삭제 | 빈 파일 확인됨 |
| `runtime/gateway_handler.py` | `gateway/gateway_handler.py` | + 빈 `__init__.py` 신규 |
| `runtime/deploy_gateway.py` | `gateway/deploy_gateway.py` | `ROOT=parents[3]` 깊이 불변 — 수정 불요 |
| `runtime/{Dockerfile,requirements.txt,claude_config.json,codex_config.toml}` | `runtime/container/` | 4종 한 세트 — 일부만 옮기면 스테이징 crash |
| `v1.0-setup-form-max5.png` | `docs/assets/` | 참조 0건 확인 — git mv 만 |
| `design/email-ux-mockup.md` + `design/email_ui.png` | `design/ux/` | **쌍으로** (mockup:3 이 png 참조) |
| `design/architecture/make_slide.py` | `docs/deck/` | 출력 경로 `__file__`-상대(:210) — 무수정 생존; docstring 갱신 |
| `design/architecture/solution-architecture.pptx` | `docs/deck/` | untracked(gitignore `*.pptx`) — fs 이동만 |

**.gw_build.zip / .agentcore_build/ / .gw_build/ / `__pycache__`:** 리팩토링 시작 전 삭제 (옛 레이아웃 사본이 grep 을 오염시키고 stale bytecode 가 missing-module 에러를 가릴 수 있음; 다음 배포에서 재생성).

## 4. import 재작성 — 모듈별 매핑 (sed 금지)

| 옛 경로 | 새 경로 |
|---|---|
| `briefing.shared.harness.author` | `briefing.core.authoring.author` |
| `briefing.shared.harness.certifier` | `briefing.core.verification.certifier` |
| `briefing.shared.<그 외 전부>` (config·gate·pipeline·render·lenses·_debug·prompts·retrieval.*·stores.*) | `briefing.core.<동일>` |
| `briefing.runtime.gateway_handler` | `briefing.gateway.gateway_handler` |
| `briefing.runtime.deploy_gateway` | `briefing.gateway.deploy_gateway` |
| 상대형 `..shared.*` / `.harness.*` | 같은 매핑을 상대형으로 적용 (깊이는 전부 불변 — dot 수 변화 없음) |

**규모(검증된 수치):** tests 22개 파일 79줄 + scripts 5개 파일 17줄 + 어댑터 상대 import (runtime 4파일·scheduler 3·webapi 4·local 1) + core 내부 (gate.py:23-25,92-94 · stores/cache.py:17-19 · pipeline 등).

**매핑이 반드시 덮어야 하는 지뢰 (grep-for-imports 가 놓치는 것들):**

1. **문자열형 monkeypatch 3곳:** `tests/test_config.py:48,57,65` — `"briefing.shared.stores.dynamo.user_store_from_settings"` (import 재작성 도구에 안 보임)
2. **함수 안 lazy import — 아침 발송 경로 포함:**
   - `scheduler/dispatch.py:16` (`..shared.pipeline`) — mode=scheduled 분기에서만 로드. **놓치면 빌드·기동·스모크 전부 통과 후 07:00 발송에서만 죽음**
   - `scheduler/due.py:30` (`..shared._debug`) — 타임존 예외 핸들러 안
   - `runtime/_trial.py:11` (`..shared.config`) — trial 분기에서만
   - `runtime/agentcore_runtime.py:136` (`..shared.retrieval.gateway_client`) — GATEWAY_ENABLED 분기
   - `webapi/app.py:79-80` — /profile 요청 시에만 로드 → 놓치면 배포 후 500
3. **private 이름 유지:** `curation._default_fetch`, `gateway_client._token` — `gateway/gateway_handler.py`와 `scripts/e2e_gateway.py:29-30` 이 import. 92개 테스트 밖이라 깨져도 조용함
4. **오탐 제외:** DDB 테이블명 `briefing-source-store` 등 `briefing-*` 리소스 문자열, PyPI 명 `briefing-agent` — 절대 건드리지 말 것

## 5. 코드 수정 (이동 외 실변경)

1. **[블로커] `deploy_gateway.py`** — 같은 커밋에서: ① `:128` Handler → `briefing.gateway.gateway_handler.lambda_handler` ② 기존-Lambda 업데이트 경로(`:134-135`, 현재 `update_function_code` 만 호출)에 **`update_function_configuration(Handler=...)` + `function_updated_v2` waiter 추가**. 빠뜨리면 첫 재배포에서 라이브 Lambda 가 죽은 handler 문자열을 물고 벽돌
2. **`deploy_runtime.py:118`** — `rt = PACKAGE_DIR / "runtime"` → `PACKAGE_DIR / "runtime" / "container"` (S1 의 유일한 코드 변경)
3. **`gate.py:23-25, 92-94`** — harness import → authoring/verification (모듈 레벨 import + DI 키워드 기본값 둘 다)
4. **`stores/cache.py:17-19`** — `..harness.author`→`..authoring.author`, `..harness.certifier`→`..verification.certifier`
5. **빈 `__init__.py` 3개 신규** — `core/authoring/`, `core/verification/`, `gateway/` (잊으면 컨테이너 기동 시 전 import 실패)
6. **Dockerfile:5 주석** — 스테이징 파일 목록 언급 갱신 (cosmetic)

## 6. 변경 금지 목록 (must-not-change — 검증으로 확정)

- `runtime/container/Dockerfile:45` **CMD `-m briefing.runtime.agentcore_runtime`** — 컨테이너의 실제 entrypoint
- `deploy_runtime.py:40` **`ENTRYPOINT_REL = "briefing/runtime/agentcore_runtime.py"`**
- `deploy_runtime.py:41` **`ENV_SECTION = "# ② Briefing Runtime (deploy_runtime.py)"`** — teardown.sh:105 의 sed 매치 + `.env` writeback 멱등성이 바이트 단위로 키잉
- `deploy_runtime.py:110-113` copytree ignore 패턴 (`__pycache__`·`*.pyc`·`.agentcore_build` 만) — **이게 core/ 밑의 .md/.yaml 을 이미지로 실어 나르는 메커니즘.** `*.md`/`*.yaml` 제외 패턴 추가 금지
- `deploy_runtime.py:122-124` users/ 스테이징 — skill.md 신뢰 경계 오버레이가 `/app/users` 에 의존
- `runtime_env()` 키·값 (BACKEND=dynamo, `USERS_DIR='./users'` cwd-상대, CLAUDE_CODE_USE_BEDROCK=1 등)
- `template.py:14` 앵커 + **author_system.md·supervisor.md 는 template.py 와 같은 디렉토리** (분리 = supervisor 경로 FileNotFoundError, pytest 미검출)
- `lenses.yaml`↔`lenses.py`, `catalog.yaml`↔`sources.py` **동일 디렉토리** (둘 다 import-time 로드 — 분리 = 컨테이너 기동 crash)
- `config.py:100,139` 의 **lazy** `from .stores.dynamo import ...` — hoisting 금지 (config→dynamo→cache→gate→config 순환 발생)
- `scheduler/lambda_handler.py` 의 boto3-only 성질 + `Handler="lambda_handler.handler"` (flat zip — briefing import 넣지 말 것; invoke_runtime 의 SSE 파서와 "중복 제거" 금지, 의도적 복사)
- `deploy_gateway.py:102` 의 전체 패키지 copytree — zip 을 `briefing/gateway/` 로 슬림화 금지 (handler 가 core config/retrieval/stores 를 import-time 에 로드)
- `AGENT_NAME="briefing_agent"` — ECR·로그 그룹·CodeBuild·teardown 이름이 전부 파생
- author.py/certifier.py 의 subprocess 구성 (clean tmpdir cwd, $HOME 설정 소비) — 레이아웃 독립, 수정 불요

## 7. 문서·주석·설정 갱신 목록

**같은 커밋에서 (load-bearing):**
- `CLAUDE.md` — "저장소 현황" 구조 서술(:10-11) 전면 갱신 (auto-load 되는 프로젝트 진실 — stale 이면 모든 미래 세션을 오도)
- `README.md` — :23, :33-35, :43-53(구조 블록), :69, :80
- `infra/gateway/README.md` — :17,:24 의 gateway_handler 경로, deploy_gateway 모듈 경로 (파일 자체는 infra/ 잔류)
- `design/architecture/system-install-plan.md:48` — `runtime/deploy_gateway.py` → `gateway/deploy_gateway.py` (차기 페이즈 실행 계획 — 경로가 실행됨)
- `users/gonsoo/skill.md:4` — `shared/prompts/author_system.md` → `core/prompts/author_system.md` (커밋된 파일)
- `design/prd/prd_news.md` :20,:22,:45 — catalog.yaml/lenses.yaml 경로
- `design/architecture/four-component-analysis.md:172` — supervisor 경로

**스테일 주석 일괄 청소 (일부는 지금도 이미 틀림):**
- `scripts/claude-author.sh:4` (현재도 오류: `shared/author.py`), `lenses.yaml:1`·`catalog.yaml:1` 자기 경로 헤더, `render.py:3` (→ `design/ux/`), `.gitignore:33` 주석 (→ `docs/deck/make_slide.py`), `webapi/__init__.py:3` docstring

**건드리지 않기:** `docs/superpowers/plans|specs/*` 의 옛 경로 ~25곳 — 역사 기록. 필요시 "2026-07 리팩토링 이전 경로" 한 줄 주석만.

**정책 결정:** `*.pptx` gitignore 유지 (make_slide.py 로 재생성 가능 — deck 커밋 안 함). `docs/deck/prd.md`(기존 untracked)는 이번 범위 밖.

**저장소 밖:** auto-memory 의 강제 재발송 런북·프로젝트 메모리가 `src/briefing/runtime`·`shared` 경로를 인용 — 머지 후 메모리 갱신 (별도 액션).

## 8. 검증 사다리 & 재배포 순서

**VERIFY-0 (로컬, 머지 전):**
`rm -rf` 스테일 빌드 산출물 → `uv run ruff check src tests` → `uv run pytest` (**92개 동수 수집** 확인) → `uv run python -m briefing.local.run` (catalog/lenses 동거 + 절대 import 증명) → `DEBUG=1 uv run python scripts/e2e_smoke.py` (라이브: 하니스 분리 + prompts 로딩 증명)

**REDEPLOY-1 — Gateway Lambda (가장 먼저, 최저 위험):** GATEWAY_ENABLED 는 프로덕션 미설정 확인됨(runtime_env 가 안 실음) — 아침 발송 경로 밖. `deploy_gateway.py` 실행(§5-1 수정 포함) → `scripts/e2e_gateway.py` byte-identical + `aws lambda get-function-configuration` 으로 Handler 문자열 실변경 확인. *(단, 라이브 runtime 에 콘솔 수동 env 오버라이드가 없는지 사전 확인.)*

**REDEPLOY-2 — AgentCore 컨테이너 (발송 크리티컬):** **06:00–08:00 KST 창 밖에서**, 강제 재발송 런북 대기 상태로 `deploy_runtime.py` 실행. 검증: trial invoke (CMD·author_system.md·lenses.yaml 증명) + **`mode=scheduled` dry_run invoke** (lazy 한 dispatch/due import 증명 — trial 만으론 발송 경로가 검증 안 됨) + supervisor 경로를 쓸 거면 `scripts/supervisor_smoke.py` (supervisor.md 로딩을 검증하는 유일한 수단 — pytest 는 못 잡음). launch 가 기존 runtime 에 재부착되는지(신규 생성 아님) 확인.

**REDEPLOY-3 — webapi Lambda (runtime 다음):** `deploy_api.py` → 전 라우트 스모크: GET /catalog · GET /sample · **POST /profile (lazy import — 이 curl 이 진짜 테스트)** · POST /trial (재배포된 runtime 을 ARN 호출 — 그래서 runtime 뒤).

**REDEPLOY-4 (선택) — scheduler Lambda:** flat zip(briefing import 0)이라 필수 아님. 멱등 재실행으로 스크립트 건재만 증명.

**VERIFY-FINAL:** 다음 날 07:00 KST 발송을 **능동 확인** (받은편지함 + runtime CloudWatch) — silent-failure 통지 미구현(7/2 인시던트 OPEN 항목)이라 깨져도 에러 신호가 없다.

**롤백:** 모든 deploy 스크립트가 트리에서 전체 재스테이징(copytree)하므로 롤백 = `git revert` + 같은 스크립트 재실행. 유일한 부분 상태는 gateway Handler 설정 — REDEPLOY-1 이 반만 진행됐으면 `update_function_configuration` 으로 원복.

## 9. 범위 제외 (기각 확정 — 재제안 방지)

`runtime→agentcore` 리네임 · ops/ 집결(→ install.sh 페이즈에서 배포단위별 재검토; 그때는 `_upsert_env_lines`·`runtime_env`·`parse_sse_event` 헬퍼를 먼저 briefing 패키지 안으로 옮긴 뒤) · tests/ 미러링 · core/delivery/ · webapi·scheduler 의 deploy/ 폴더 · supervisor.md 이동 · lenses 의 authoring 소속 · deploy zip 슬림화.

## 10. 후속 (선택, 이번 범위 밖)

- import-linter 규칙: "verification/ 은 gate·stores.cache(타입만)·runtime/_smoke 외 import 금지" — 폴더 경계를 장식이 아니라 집행으로
- `_upsert_env_lines` 등 deploy 공용 헬퍼의 core 추출 (ops/ 재검토의 선행 작업)
- silent-failure 통지 (7/2 인시던트 OPEN — 이 리팩토링의 VERIFY-FINAL 이 수동인 이유)
