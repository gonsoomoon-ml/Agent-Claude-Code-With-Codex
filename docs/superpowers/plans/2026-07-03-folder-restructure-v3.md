# 폴더 구조 리팩토링 v3 — 구현 플랜

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
> **예외:** Task 7(재배포 사다리)은 라이브 AWS·비용·시간창(KST) 제약이 있어 **무감독 서브에이전트 실행 금지** — 사용자와 함께 인라인으로만 실행한다.

**Goal:** `docs/superpowers/specs/2026-07-03-folder-restructure-design.md`(스펙 v3)를 그대로 구현 — shared→core 리네임 + harness 해체, gateway/ 어댑터 승격, runtime/container/ 자산 분리, D6 문서 정리, 폴더 README, 그리고 검증된 재배포 사다리.

**Architecture:** 순수 재배치 리팩토링(동작 무변경). 각 Task 는 트리를 green(ruff+pytest 동수) 상태로 남기고 커밋한다. 머지 자체는 프로덕션 무영향 — 위험은 Task 7 의 첫 재배포에만 있다.

**Tech Stack:** Python 3.12 + UV · pytest · git mv · perl 일괄 치환 · boto3 배포 스크립트(기존).

## Global Constraints (스펙 §4·§6 발췌 — 모든 Task 에 암묵 적용)

- **sed 단순 치환 금지** — 반드시 아래 순서의 모듈별 매핑으로. `briefing-source-store` 등 `briefing-*` 리소스 문자열·PyPI 명 `briefing-agent` 는 절대 건드리지 않는다 (`briefing\.shared` 처럼 점(.)이 포함된 패턴만 사용하면 자동으로 안전).
- **테스트 베이스라인 = `176 passed, 3 skipped`** (2026-07-03 실측; CLAUDE.md 의 "92개"는 스테일). 모든 Task 후 동수여야 한다.
- **변경 금지 (byte-identical):** `deploy_runtime.py:40` `ENTRYPOINT_REL="briefing/runtime/agentcore_runtime.py"` · `:41` `ENV_SECTION="# ② Briefing Runtime (deploy_runtime.py)"` · Dockerfile `CMD [... "-m", "briefing.runtime.agentcore_runtime"]` · copytree ignore 패턴(`__pycache__`,`*.pyc`,`.agentcore_build`) · users/ 스테이징 블록 · `runtime_env()` 키/값 · `config.py:100,139` 의 lazy `from .stores.dynamo import ...`(hoisting 금지 — 순환) · `scheduler/lambda_handler.py`(briefing import 0 유지) · `deploy_gateway.py` 의 전체 패키지 copytree(zip 슬림화 금지) · `AGENT_NAME="briefing_agent"`.
- **동거 불변식:** `template.py`+`author_system.md`+`supervisor.md` 같은 디렉토리 / `lenses.py`+`lenses.yaml` / `sources.py`+`catalog.yaml` — 셋 다 import-time 로드라 분리 = 컨테이너 기동 crash.
- **private 이름 유지:** `curation._default_fetch` · `gateway_client._token` (gateway_handler + scripts/e2e_gateway.py 가 import; 테스트 밖이라 깨져도 조용함).
- 커밋 메시지 끝에 `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

---

### Task 1: 베이스라인 + D6 문서·자산 정리

**Files:**
- Move: `v1.0-setup-form-max5.png` → `docs/assets/`
- Move: `design/email-ux-mockup.md`, `design/email_ui.png` → `design/ux/`
- Move: `design/architecture/make_slide.py`, `design/architecture/solution-architecture.pptx`(untracked) → `docs/deck/`
- Modify: `design/ux/email-ux-mockup.md:3`, `src/briefing/shared/render.py:3`, `.gitignore:33`, `README.md:23,53,80`, `docs/deck/make_slide.py` docstring

**Interfaces:** Produces: 이후 Task 의 문서 경로 기준(`design/ux/`, `docs/deck/`, `docs/assets/`). 코드 동작 무변경.

- [ ] **Step 1: 스테일 빌드 산출물 청소 + 베이스라인 기록**

```bash
rm -rf .agentcore_build .gw_build .gw_build.zip
find src tests scripts -name __pycache__ -type d -exec rm -rf {} +
uv run ruff check src tests && uv run pytest -q | tail -1
```
Expected: ruff `All checks passed!`, pytest `176 passed, 3 skipped`. (다르면 그 수치를 이 플랜의 베이스라인으로 기록하고 진행.)

- [ ] **Step 2: 파일 이동**

```bash
mkdir -p docs/assets design/ux
git mv v1.0-setup-form-max5.png docs/assets/
git mv design/email-ux-mockup.md design/ux/
git mv design/email_ui.png design/ux/
git mv design/architecture/make_slide.py docs/deck/
mv design/architecture/solution-architecture.pptx docs/deck/   # untracked(gitignore *.pptx) — fs 이동만
```

- [ ] **Step 3: 참조 갱신 (5곳 — 전부 문자열 치환)**

| 파일 | 옛 문자열 | 새 문자열 |
|---|---|---|
| `design/ux/email-ux-mockup.md:3` | `design/email_ui.png` | `design/ux/email_ui.png` |
| `src/briefing/shared/render.py:3` | `design/email-ux-mockup.md` | `design/ux/email-ux-mockup.md` |
| `.gitignore:33` (주석) | `design/architecture/make_slide.py` | `docs/deck/make_slide.py` |
| `README.md` :23·:53·:80 (3곳) | `design/email-ux-mockup.md` 계열 | `design/ux/email-ux-mockup.md` 계열 |
| `docs/deck/make_slide.py` 첫 docstring | `design/architecture` 자기 언급 | `docs/deck` |

`*.pptx` gitignore 는 **유지**(스펙 결정: deck 은 재생성 가능, 미커밋). `docs/deck/prd.md`(기존 untracked)는 건드리지 않는다.

- [ ] **Step 4: 검증**

```bash
grep -rn 'design/email-ux-mockup\|design/email_ui\|design/architecture/make_slide' README.md src .gitignore design docs/deck | grep -v 'design/ux/'
uv run pytest -q | tail -1
```
Expected: grep 출력 0줄(옛 경로 잔존 없음) · pytest 베이스라인 동수.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "chore(docs): D6 자산 정리 — 루즈 파일을 docs/assets · design/ux · docs/deck 로"
```

---

### Task 2: shared→core 리네임 + harness 해체 (authoring/verification)

**Files:**
- Move: `src/briefing/shared/` → `src/briefing/core/`; `core/harness/author.py` → `core/authoring/author.py`; `core/harness/certifier.py` → `core/verification/certifier.py`
- Create: `core/verification/__init__.py` (빈 파일; `core/authoring/__init__.py` 는 빈 `harness/__init__.py` 재사용)
- Modify: `core/gate.py`, `core/stores/cache.py` (표적 수정) + src/tests/scripts 전반 (일괄 매핑) + `core/lenses.yaml:1`, `core/retrieval/catalog.yaml:1`, `scripts/claude-author.sh:4`, `src/briefing/webapi/__init__.py:3`, `CLAUDE.md`, `users/gonsoo/skill.md:4`, `design/prd/prd_news.md`, `design/architecture/four-component-analysis.md:172`

**Interfaces:** Produces: 새 모듈 경로 — `briefing.core.*`, `briefing.core.authoring.author`, `briefing.core.verification.certifier`. 이후 모든 Task 는 이 경로를 전제.

- [ ] **Step 1: git mv (히스토리 보존 순서)**

```bash
git mv src/briefing/shared src/briefing/core
mkdir -p src/briefing/core/authoring src/briefing/core/verification
git mv src/briefing/core/harness/author.py src/briefing/core/authoring/author.py
git mv src/briefing/core/harness/certifier.py src/briefing/core/verification/certifier.py
git mv src/briefing/core/harness/__init__.py src/briefing/core/authoring/__init__.py   # 빈 파일 재사용
touch src/briefing/core/verification/__init__.py
git add src/briefing/core/verification/__init__.py
rmdir src/briefing/core/harness
```

- [ ] **Step 2: 표적 수정 ① — `core/gate.py` (모듈 레벨 import 3줄; DI 기본값 `author.draft_card` 등은 모듈 객체명이 유지되므로 무수정)**

```python
# 옛 (gate.py:23-25)
from .harness import author
from .harness.author import Claim, DraftCard
from .harness.certifier import CertVerdict, Envelope, certify
# 새
from .authoring import author
from .authoring.author import Claim, DraftCard
from .verification.certifier import CertVerdict, Envelope, certify
```

- [ ] **Step 3: 표적 수정 ② — `core/stores/cache.py` (2줄; `from ..gate import GatedCard` 는 무수정)**

```python
# 옛 (cache.py:17-18)
from ..harness.author import Claim, DraftCard
from ..harness.certifier import CertVerdict
# 새
from ..authoring.author import Claim, DraftCard
from ..verification.certifier import CertVerdict
```

- [ ] **Step 4: 일괄 매핑 (순서 고정 — 구체형 먼저, 그다음 일반형)**

```bash
FILES=$(grep -rlE 'briefing\.shared|\.\.shared|briefing/shared' src tests scripts)
perl -pi -e '
  s/briefing\.shared\.harness\.author/briefing.core.authoring.author/g;
  s/briefing\.shared\.harness\.certifier/briefing.core.verification.certifier/g;
  s/\.\.shared\.harness\.author/..core.authoring.author/g;
  s/\.\.shared\.harness\.certifier/..core.verification.certifier/g;
  s/briefing\.shared/briefing.core/g;
  s/\.\.shared/..core/g;
  s{briefing/shared}{briefing/core}g;
' $FILES
```
이 매핑이 자동으로 덮는 지뢰들(스펙 §4): `tests/test_config.py:48,57,65` 문자열형 monkeypatch · lazy import 5곳(`scheduler/dispatch.py:16`·`due.py:30`·`runtime/_trial.py:11`·`agentcore_runtime.py:136`·`webapi/app.py:79-80`) · scripts 의 private-이름 import (`e2e_gateway.py:29-30` — 이름 자체는 불변이므로 경로만 바뀜).

- [ ] **Step 5: 주석·문서 경로 갱신 (이 Task 가 깨뜨리는 참조 전부)**

| 파일 | 수정 |
|---|---|
| `core/lenses.yaml:1` | 헤더 → `# src/briefing/core/lenses.yaml — …` |
| `core/retrieval/catalog.yaml:1` | 헤더 → `# src/briefing/core/retrieval/catalog.yaml — …` |
| `scripts/claude-author.sh:4` | (지금도 스테일) → `src/briefing/core/authoring/author.py:bedrock_author_env()` |
| `src/briefing/webapi/__init__.py:3` | `briefing.shared(sources·lenses)` → `briefing.core(sources·lenses)` |
| `users/gonsoo/skill.md:4` | `src/briefing/shared/prompts/author_system.md` → `src/briefing/core/prompts/author_system.md` |
| `design/prd/prd_news.md` (:20,:22,:45) | `catalog.yaml`/`lenses.yaml` 경로 앞부분 `shared/` → `core/`(retrieval 은 `core/retrieval/`, lenses 는 `core/`) |
| `design/architecture/four-component-analysis.md:172` | `shared/prompts/supervisor.md` → `core/prompts/supervisor.md` |
| `CLAUDE.md` (저장소 현황) | `shared/` → `core/`, `**\`harness/\`**(author·certifier)` → `**\`authoring/\`**(author)·**\`verification/\`**(certifier)` — 이 Task 가 바꾼 경로 문자열만; 구조 문장 전면 재작성은 Task 6 |

- [ ] **Step 6: 잔존 감사 (grep audit)**

```bash
grep -rnE 'briefing\.shared|\.\.shared|briefing/shared|from \.harness|from \.\.harness|\.harness\.' src tests scripts
grep -rn 'briefing-source-store' src   # 리소스 문자열 오염 안 됐는지 — 여전히 존재해야 함
```
Expected: 첫 grep 0줄 · 둘째 grep 은 기존과 동일하게 히트(치환 미오염 증명).

- [ ] **Step 7: 검증 (컴파일→린트→테스트→로컬 파이프라인)**

```bash
find src -name __pycache__ -type d -exec rm -rf {} +
uv run ruff check src tests
uv run pytest -q | tail -1
uv run python -m briefing.local.run
```
Expected: ruff 통과 · `176 passed, 3 skipped`(동수) · local.run 이 fake DI 파이프라인 완주(lenses.yaml·catalog.yaml 동거 + 절대 import 증명).

- [ ] **Step 8: Commit**

```bash
git add -A && git commit -m "refactor(core): shared→core 리네임 + harness 해체(authoring/verification) — 스펙 v3 §D1"
```

---

### Task 3: gateway/ 어댑터 승격 + deploy_gateway 블로커 수정

**Files:**
- Create: `src/briefing/gateway/__init__.py` (빈 파일)
- Move: `src/briefing/runtime/gateway_handler.py` → `src/briefing/gateway/`; `src/briefing/runtime/deploy_gateway.py` → `src/briefing/gateway/`
- Modify: `src/briefing/gateway/deploy_gateway.py` (Handler 문자열 + update 경로 + docstring), `tests/test_gateway.py:7`, `infra/gateway/README.md`, `design/architecture/system-install-plan.md:48`, `CLAUDE.md`

**Interfaces:**
- Consumes: Task 2 의 `briefing.core.*` 경로 (gateway_handler 의 `..core.*` 상대 import 는 gateway/ 아래에서 깊이 불변 — 추가 수정 0줄)
- Produces: Lambda Handler 문자열 `briefing.gateway.gateway_handler.lambda_handler` · 모듈 `briefing.gateway.deploy_gateway`

- [ ] **Step 1: 이동**

```bash
mkdir -p src/briefing/gateway
touch src/briefing/gateway/__init__.py && git add src/briefing/gateway/__init__.py
git mv src/briefing/runtime/gateway_handler.py src/briefing/gateway/
git mv src/briefing/runtime/deploy_gateway.py src/briefing/gateway/
```
`deploy_gateway.py` 의 `ROOT = Path(__file__).resolve().parents[3]` 은 깊이 불변(둘 다 `src/briefing/<pkg>/`) — 수정 금지.

- [ ] **Step 2: `deploy_gateway.py` 수정 (블로커 — 스펙 §5-1)**

`common` dict 의 Handler:
```python
# 옛
Handler="briefing.runtime.gateway_handler.lambda_handler",
# 새
Handler="briefing.gateway.gateway_handler.lambda_handler",
```

`_lambda()` 의 기존-함수 업데이트 분기 (현재는 `update_function_code` 만 — 이대로면 첫 재배포에서 라이브 Lambda 가 죽은 handler 를 물고 벽돌):
```python
# 옛
    except lam.exceptions.ResourceConflictException:
        lam.update_function_code(FunctionName=LAMBDA_NAME, S3Bucket=bucket, S3Key=key)
        print(f"♻ Lambda update(zip): {LAMBDA_NAME}")
# 새
    except lam.exceptions.ResourceConflictException:
        lam.update_function_code(FunctionName=LAMBDA_NAME, S3Bucket=bucket, S3Key=key)
        lam.get_waiter("function_updated_v2").wait(FunctionName=LAMBDA_NAME)
        # Handler 는 create 시에만 설정됨 — 모듈 이동(briefing.gateway) 을 기존 Lambda 에도 밀어넣는다
        lam.update_function_configuration(FunctionName=LAMBDA_NAME, Handler=common["Handler"])
        print(f"♻ Lambda update(zip+handler): {LAMBDA_NAME}")
```

파일 상단 docstring 의 실행 예시 `python -m briefing.runtime.deploy_gateway` → `python -m briefing.gateway.deploy_gateway`.

- [ ] **Step 3: 참조 갱신**

| 파일 | 수정 |
|---|---|
| `tests/test_gateway.py:7` | `from briefing.runtime import gateway_handler as h` → `from briefing.gateway import gateway_handler as h` |
| `infra/gateway/README.md` | `runtime/gateway_handler.py`·`runtime/deploy_gateway` 언급 전부 → `gateway/…` (grep 으로 전수: `grep -n 'runtime' infra/gateway/README.md`) |
| `design/architecture/system-install-plan.md:48` | `runtime/deploy_gateway.py` → `gateway/deploy_gateway.py` |
| `CLAUDE.md` | `① Gateway: gateway_handler·deploy_gateway` 가 runtime/ 소속으로 서술된 부분 → `gateway/` 소속으로 |

- [ ] **Step 4: 검증**

```bash
grep -rn 'briefing\.runtime\.gateway_handler\|runtime/gateway_handler\|runtime\.deploy_gateway\|runtime/deploy_gateway' src tests scripts infra CLAUDE.md design
uv run ruff check src tests && uv run pytest -q | tail -1
```
Expected: grep 0줄 · `176 passed, 3 skipped`.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "refactor(gateway): 어댑터 승격(handler+deploy) + update 경로에 Handler 밀어넣기 — 스펙 v3 §D3·§5-1"
```

---

### Task 4: runtime/container/ — 컨테이너 빌드 자산 분리

**Files:**
- Move: `src/briefing/runtime/{Dockerfile,requirements.txt,claude_config.json,codex_config.toml}` → `src/briefing/runtime/container/` (4종 한 세트 — 일부만 옮기면 스테이징 crash)
- Modify: `src/briefing/runtime/deploy_runtime.py` (1줄), `runtime/container/Dockerfile` 헤더 주석

**Interfaces:**
- Consumes: 없음 (Task 2·3 과 독립)
- Produces: 스테이징 소스 경로 `PACKAGE_DIR / "runtime" / "container"` — Task 7 REDEPLOY-2 가 사용

- [ ] **Step 1: 이동**

```bash
mkdir -p src/briefing/runtime/container
git mv src/briefing/runtime/Dockerfile src/briefing/runtime/container/
git mv src/briefing/runtime/requirements.txt src/briefing/runtime/container/
git mv src/briefing/runtime/claude_config.json src/briefing/runtime/container/
git mv src/briefing/runtime/codex_config.toml src/briefing/runtime/container/
```
`container/` 는 데이터 디렉토리 — `__init__.py` 불필요.

- [ ] **Step 2: `deploy_runtime.py` 스테이징 앵커 1줄 (S1 의 유일한 코드 변경)**

```python
# 옛
    rt = PACKAGE_DIR / "runtime"
# 새
    rt = PACKAGE_DIR / "runtime" / "container"
```
바로 아래 4종 `shutil.copy2` 루프·users/ 블록·copytree ignore 는 **무수정** (Global Constraints).

- [ ] **Step 3: Dockerfile 헤더 주석 갱신 (cosmetic)** — `grep -n 'runtime' src/briefing/runtime/container/Dockerfile | head` 로 자산 출처를 `src/briefing/runtime/` 로 서술한 주석을 찾아 `src/briefing/runtime/container/` 로. `CMD [... "briefing.runtime.agentcore_runtime"]` 는 **절대 무수정**.

- [ ] **Step 4: 로컬 스테이징 증명 (AWS 불요 — copy 만 실행)**

```bash
uv run python -c "from briefing.runtime.deploy_runtime import stage_build_context; print(stage_build_context())"
ls .agentcore_build/Dockerfile .agentcore_build/requirements.txt .agentcore_build/codex_config.toml .agentcore_build/claude_config.json .agentcore_build/briefing/core/lenses.yaml .agentcore_build/briefing/core/prompts/supervisor.md .agentcore_build/users
rm -rf .agentcore_build
```
Expected: 4 자산이 빌드 컨텍스트 **루트**에, core/ 밑 yaml·md 와 users/ 가 트리에 존재 — FileNotFoundError 없음. (이 step 이 실패하면 4종 세트 이동 누락이다.)

- [ ] **Step 5: 검증 + Commit**

```bash
uv run ruff check src tests && uv run pytest -q | tail -1
git add -A && git commit -m "refactor(runtime): 컨테이너 빌드 자산 4종을 runtime/container/ 로 — 스펙 v3 §S1"
```
Expected: `176 passed, 3 skipped`.

---

### Task 5: VERIFY-0 라이브 게이트 (커밋 없음 — 통과 전 Task 6·7 진행 금지)

**Files:** 없음 (검증만). **Interfaces:** Consumes: Task 2–4 완료 트리.

- [ ] **Step 1: 라이브 e2e 스모크 (실 RSS → `claude -p` author → `codex` certifier → render; 비용 발생)**

```bash
DEBUG=1 uv run python scripts/e2e_smoke.py
```
Expected: 파이프라인 완주 + 렌더 HTML 산출. 이것이 하니스 분리(authoring/verification) + prompts 로딩을 **AWS 밖에서** 증명하는 유일한 수단이다 (pytest 는 fake DI 라 못 잡음).

- [ ] **Step 2: (Gateway 검증 준비 확인)** `scripts/e2e_gateway.py` 는 라이브 Lambda 재배포 **후**에만 의미 있음 — Task 7 REDEPLOY-1 에서 실행. 여기서는 private 이름 import 가 새 경로에 실존하는지만 확인 (모듈 실행 금지 — 비용/부작용 방지):

```bash
uv run python -c "from briefing.core.retrieval.curation import _default_fetch; from briefing.core.retrieval.gateway_client import _token; print('private names OK')"
```
Expected: `private names OK`.

---

### Task 6: 폴더 README 7곳 + infra/ 인덱스 + CLAUDE.md·README 구조 정합

**Files:**
- Create: `src/briefing/core/README.md`, `src/briefing/runtime/README.md`, `src/briefing/gateway/README.md`, `src/briefing/scheduler/README.md`, `src/briefing/webapi/README.md`, `src/briefing/local/README.md`, `infra/README.md`
- Modify: `CLAUDE.md` (저장소 현황 구조 문장 + 테스트 수), `README.md` (:43-53 구조 블록)

**Interfaces:** Consumes: Task 1–4 의 최종 트리. Produces: 없음 (문서).

- [ ] **Step 1: README 7곳 생성 — 아래 내용 그대로 (각 파일 첫 줄이 제목)**

`src/briefing/core/README.md`:
```markdown
# core — 도메인 전부 (구 shared/)
파이프라인의 진실이 사는 곳. 루트 = 척추: `pipeline.py`(fetch→curate→author→gate→render 조립) · `gate.py`(verify-before-publish 게이트, maker-checker 루프) · `config.py` · `render.py`(이메일 HTML) · `lenses.py`+`lenses.yaml`(관점 — webapi 카탈로그도 소비).
하위: `retrieval/`(증거 수집 + catalog.yaml) · `authoring/`(author.py = `claude -p` 작성자) · `verification/`(certifier.py = `codex exec` 검증자) · `stores/`(ledger·cache·source_store, backends.py 가 로컬/DDB seam) · `prompts/`(template.py 와 .md 는 같은 디렉토리 필수 — 로더가 자기 폴더에서만 읽음).
⚠️ authoring/verification 폴더 분리는 **가독성**이다 — decorrelation 의 실제 메커니즘은 gate 가 만드는 4필드 Envelope 화이트리스트 + certifier 의 clean-dir subprocess. lenses.yaml·catalog.yaml 은 import-time 로드: .py 와 분리하면 기동 crash.
새 기능: 관점 추가=`lenses.yaml` 한 항목 · 미디어 추가=`retrieval/catalog.yaml` 한 항목 · 저장 교체=`stores/backends.py`.
```

`src/briefing/runtime/README.md`:
```markdown
# runtime — AgentCore 어댑터 (컨테이너로 배포)
`agentcore_runtime.py` = 엔트리포인트(컨테이너 CMD `-m briefing.runtime.agentcore_runtime`). `supervisor.py` = Strands supervisor 옵션 · `_trial.py` = trial 모드 · `_smoke.py` = 스모크.
`deploy_runtime.py`(배포: 스테이징→CodeBuild→launch) · `invoke_runtime.py`(호출 검증) · `teardown.sh`.
`container/` = 이미지 빌드 자산 4종(Dockerfile·requirements.txt·claude_config.json·codex_config.toml) — deploy_runtime 이 빌드 컨텍스트 루트로 복사. 4종은 한 세트: 일부만 옮기면 스테이징 crash.
⚠️ scheduled/trial 분기의 import 는 lazy — 스모크가 통과해도 발송 경로는 `mode=scheduled` dry_run 으로 따로 증명해야 한다.
```

`src/briefing/gateway/README.md`:
```markdown
# gateway — ① AgentCore Gateway 어댑터 (독립 Lambda 배포 단위)
`gateway_handler.py` = retrieval 3도구(fetch_article·get_source·discover_feed) Lambda(.gw_build.zip). `deploy_gateway.py` = 멱등 배포(CFN Cognito→zip→provider→Gateway).
기본 off — `GATEWAY_ENABLED=1` 일 때만 fabric 이 경유. guardrail(비협상): 노출 도구는 retrieval 3개뿐(gate/certify/author 미노출 — decorrelation).
zip 은 briefing 패키지 전체를 담는다(handler 가 core config/retrieval/stores 를 import-time 로드) — 슬림화 금지. 재현 번들·검증: `infra/gateway/` + `scripts/e2e_gateway.py`.
```

`src/briefing/scheduler/README.md`:
```markdown
# scheduler — ⑤ 발송 체인 어댑터 (EventBridge→Lambda)
`due.py`(발송 대상 판정) → `dispatch.py`(runtime `add_async_task` 호출) → `deliver.py`(SES) · `sent_log.py`(중복 방지) · `run_dispatch.py`(로컬 프리뷰).
`lambda_handler.py` 는 **의도적으로 briefing import 0**(boto3 만) — flat zip(Handler=`lambda_handler.handler`)이라 소스 트리 레이아웃과 무관. invoke_runtime 의 SSE 파서와 "중복 제거" 금지(의도된 복사).
`deploy_scheduler.py`·`teardown_scheduler.sh` = 배포/철거.
```

`src/briefing/webapi/README.md`:
```markdown
# webapi — ④ Web UI 백엔드 어댑터 (Lambda + CloudFront 프론트는 web/)
`app.py`(FastAPI; `sample_briefing.html` 은 import-time 로드라 같은 디렉토리 필수) · `catalog.py`(공개 카탈로그 — core lenses/sources 소비) · `profile.py` · `trial.py`(체험 가드) · `lambda_main.py`(Handler=`briefing.webapi.lambda_main.handler`) · `run.py`(로컬 uvicorn).
`deploy_api.py`·`deploy_web.py`·`teardown_webui.sh` = 배포/철거.
⚠️ `/profile` 의존성은 함수 안 lazy import — 배포 후 curl 로만 실증 가능.
```

`src/briefing/local/README.md`:
```markdown
# local — AWS-free 베이스라인
`run.py`: fake DI(author/certifier 스텁)로 전체 파이프라인을 로컬에서 완주 — `uv run python -m briefing.local.run`.
리팩토링·의존성 변경 후 첫 번째 검증 관문(카탈로그/lens yaml 동거, import 정합을 실행으로 증명).
```

`infra/README.md`:
```markdown
# infra — 배포 단위 인덱스 (CFN + 셸 배포자)
| 배포 단위 | 코드 | 배포/철거 | CFN |
|---|---|---|---|
| ② AgentCore 컨테이너 | `src/briefing/runtime/` | `uv run python -m briefing.runtime.deploy_runtime` · `runtime/teardown.sh` | (toolkit 관리) |
| ① Gateway Lambda | `src/briefing/gateway/` | `uv run python -m briefing.gateway.deploy_gateway` | `infra/gateway/cognito.yaml` |
| ⑤ scheduler Lambda | `src/briefing/scheduler/` | `-m briefing.scheduler.deploy_scheduler` · `teardown_scheduler.sh` | — |
| ④ webapi Lambda + web | `src/briefing/webapi/` + `web/` | `-m briefing.webapi.deploy_api` · `deploy_web` · `teardown_webui.sh` | `infra/auth/cognito-users.yaml` |
| ③ DynamoDB 3테이블 | `src/briefing/core/stores/` | `infra/deploy_ddb.sh` | `infra/ddb.yaml` |
컨벤션: 각 어댑터의 배포 스크립트는 `deploy_*.py`/`teardown_*.sh` 파일명 접두어로 그 어댑터 패키지 안에 산다(ops/ 집결은 기각 — install.sh 페이즈에서 재검토).
```

- [ ] **Step 2: CLAUDE.md 구조 문장 최종 정합** — "저장소 현황" 의 구조 서술을 새 트리로 재작성:

```
**구조:** `src/briefing/` = `core/`(진실, 구 shared) — **`stores/`**(source_store·cache·ledger·dynamo·backends) · **`retrieval/`**(sources·curation·catalog·gateway_client) · **`authoring/`**(author=`claude -p`) · **`verification/`**(certifier=`codex exec`) · core 루트(config·gate·pipeline·render·lenses·prompts) / `runtime/`(AgentCore 어댑터 + supervisor 옵션 + `container/` 빌드 자산) / `gateway/`(① Gateway: handler+deploy) / `scheduler/`(⑤ due→dispatch→SES deliver) / `webapi/`(④) / `local/`(AWS-free baseline)
```
같은 커밋에서 스테일 테스트 수 갱신: `테스트 **92개**` → `테스트 **176개+3 skipped**` (Task 1 베이스라인 실측 기준으로).

- [ ] **Step 3: README.md 구조 블록(:43-53)을 아래 내용으로 교체** (`-m briefing.runtime.deploy_runtime` 등 명령 예시는 불변):

```
src/briefing/
├── core/          # 도메인(구 shared): pipeline·gate·config·render·lenses(+yaml)
│   │              #   + retrieval/(catalog.yaml) · authoring/(author=claude -p)
│   │              #   + verification/(certifier=codex exec) · stores/ · prompts/
├── runtime/       # AgentCore 어댑터 + container/(Dockerfile 등 이미지 빌드 자산 4종)
├── gateway/       # ① Gateway Lambda 어댑터 (gateway_handler + deploy_gateway)
├── scheduler/     # ⑤ 발송 체인 (due→dispatch→deliver + flat Lambda handler)
├── webapi/        # ④ Web UI 백엔드 (FastAPI + Lambda)
└── local/         # AWS-free 베이스라인 (fake DI 전체 파이프라인)
web/               # ④ 프론트엔드 (Vite+React → CloudFront)
infra/             # CFN 템플릿 + 배포 단위 인덱스(infra/README.md)
design/            # 설계 문서: prd/ · research/ · architecture/ · ux/(email-ux-mockup.md)
docs/              # 산출물: superpowers/(specs·plans) · deck/ · assets/
```

- [ ] **Step 4: 검증 + Commit**

```bash
grep -rn 'shared/' CLAUDE.md README.md | grep -v 'core'   # 옛 구조 서술 잔존 확인
uv run pytest -q | tail -1
git add -A && git commit -m "docs: 폴더 README 7곳 + infra 인덱스 + CLAUDE.md/README 구조 정합 — 스펙 v3 §7"
```
Expected: grep 0줄 · 테스트 동수.

---

### Task 7: 재배포 사다리 (human-supervised — 서브에이전트 단독 실행 금지)

**Files:** 없음 (운영). **Interfaces:** Consumes: Task 1–6 전부 + 사용자의 시간창 결정.
**전제:** 라이브 시스템(매일 07:00 KST 발송, moongons@amazon.com). 7/2 카드 격리 인시던트의 silent-failure 통지가 아직 미구현 — 실패해도 에러 신호가 없다. 강제 재발송 런북 대기 상태로 진행.

- [ ] **Step 1 — REDEPLOY-1: Gateway Lambda (최저 위험 먼저).** 사전에 라이브 runtime 에 콘솔 수동 `GATEWAY_ENABLED` 오버라이드가 없는지 확인 후:

```bash
uv run python -m briefing.gateway.deploy_gateway
aws lambda get-function-configuration --function-name briefing-gw-gonsoo-handler --region us-east-1 --query Handler
uv run python scripts/e2e_gateway.py
```
Expected: Handler = `"briefing.gateway.gateway_handler.lambda_handler"` · e2e 3도구 byte-identical PASS.
실패 시 롤백: `aws lambda update-function-configuration --function-name briefing-gw-gonsoo-handler --handler briefing.runtime.gateway_handler.lambda_handler` + git revert 후 재배포.

- [ ] **Step 2 — REDEPLOY-2: AgentCore 컨테이너 (발송 크리티컬 — 06:00–08:00 KST 창 밖에서만).**

```bash
uv run python -m briefing.runtime.deploy_runtime          # 스테이징→CodeBuild(5-10분)→launch(기존 runtime 재부착 확인 — 신규 생성이면 중단)
uv run python -m briefing.runtime.invoke_runtime          # trial/스모크 invoke: CMD·prompts·lenses 증명
```
그리고 **발송 경로 실증(필수):** `mode=scheduled` dry_run invoke — trial 만으론 lazy 한 `..core.pipeline`(dispatch) import 가 검증되지 않는다. supervisor 경로를 유지한다면 `uv run python scripts/supervisor_smoke.py` (supervisor.md 로딩을 검증하는 유일한 수단).

- [ ] **Step 3 — REDEPLOY-3: webapi Lambda (runtime 다음 — trial 이 runtime ARN 을 호출).**

```bash
uv run python -m briefing.webapi.deploy_api
# 전 라우트 스모크 (API URL 은 .env 의 BRIEFING_API_URL):
curl -sf "$API/catalog" >/dev/null && echo catalog-OK
curl -sf "$API/sample"  >/dev/null && echo sample-OK
# POST /profile — lazy import 경로의 유일한 실증 (Cognito 토큰 필요; 웹 UI 로그인 후 프로필 저장으로 대체 가능)
# POST /trial  — 웹 UI '체험' 버튼으로 e2e (재배포된 runtime 호출 증명)
```

- [ ] **Step 4 — REDEPLOY-4 (선택): scheduler Lambda.** flat zip(briefing import 0)이라 필수 아님 — 멱등 재실행으로 스크립트 건재만 증명: `uv run python -m briefing.scheduler.deploy_scheduler`.

- [ ] **Step 5 — VERIFY-FINAL: 다음 날 07:00 KST 발송 능동 확인.** 받은편지함 + runtime CloudWatch 로그(`/aws/bedrock-agentcore/runtimes/briefing_agent-*`)를 직접 확인 — 에러 신호가 자동으로 오지 않는다. 실패 시 강제 재발송 런북 실행.

- [ ] **Step 6 — 저장소 밖 마무리:** auto-memory 의 런북·프로젝트 메모리가 인용하는 `src/briefing/runtime`·`shared` 경로 갱신(강제 재발송 런북 포함) — Claude 세션에서 메모리 파일 수정.
