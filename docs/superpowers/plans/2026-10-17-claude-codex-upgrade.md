# Claude Code·Codex 업그레이드 비교 실험 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 업그레이드 후보(검증 AI 5종, 요약 AI 조건 6가지)를 운영과 같은 조건으로 오프라인 비교한다. 그 결과로 품질·비용 근거가 있는 업그레이드 조합을 리포트로 낸다(U2–U7).

**Architecture:**
- 실험 코드는 운영 커밋에 고정한 worktree 의 `scripts/upgrade_eval/` 패키지에 둔다.
- 운영 모듈(`author`·`gate`·`certifier`·`numeric`)을 import 해 운영 경로를 그대로 쓰고, CLI 경로·env·effort 만 주입한다.
- CLI 는 `~/upgrade-eval/bin/` 의 버전별 설치본을 허용 목록 env 로 실행한다. 원시 결과는 JSONL 로 `~/upgrade-eval/` 에 쌓는다.
- 판정은 Bedrock Converse 로 한다. 집계·결정·리포트는 순수 함수로 만든다.

**Tech Stack:** Python 3(uv), boto3(bedrock-runtime Converse, dynamodb 읽기 전용, pricing, ce), pytest, claude-code 2.1.195/2.1.301, codex 0.142.2/0.163.0.

**Spec:** `docs/superpowers/specs/2026-10-17-claude-codex-upgrade-design.md`

## Global Constraints

- **코드 기준점**
  - worktree `/home/ubuntu/Agent-Claude-Code-With-Codex-upgrade-eval`, 브랜치 `upgrade-eval`, 시작 커밋 `221701a`(운영 `96dee74` 에 `.gitignore` 만 더한 것).
  - 메인 작업 트리의 미커밋 변경(헤드라인·카탈로그)은 가져오지 않는다.
- **실행 격리**
  - `claude -p`·`codex exec` 는 호출마다 새 빈 cwd 에서 `stdin=DEVNULL` 로 실행한다.
  - 검증 AI 프롬프트는 `certifier._build_codex_prompt(envelope)` 그대로 쓴다(envelope 4필드만).
- **author env 는 허용 목록만** — 아래 외에는 아무것도 상속하지 않는다.
  - `PATH`(CLI bin + node + `/usr/local/bin:/usr/bin:/bin`)
  - `HOME`: 호출마다 새 빈 디렉토리. `.claude.json` 은 `src/briefing/runtime/container/claude_config.json` 사본.
  - `LANG=C.UTF-8`, `CLAUDE_CODE_USE_BEDROCK=1`, `ANTHROPIC_MODEL`, `AWS_REGION=us-east-1`, `ENABLE_TOOL_SEARCH=false`
  - `AWS_SHARED_CREDENTIALS_FILE=/home/ubuntu/.aws/credentials`, `AWS_CONFIG_FILE=/home/ubuntu/.aws/config`
  - 조건별로 `CLAUDE_CODE_EFFORT_LEVEL`
- **명령**
  - author: `claude -p --system-prompt <system> --output-format json <user>` (운영 `_run_author` 와 같음)
  - codex: `codex exec --skip-git-repo-check --json <prompt>`, `CODEX_HOME=~/upgrade-eval/codex-home/<verifier>`
- **운영 DynamoDB 는 읽기만 한다:** `scan`·`get_item` 만, 대상은 `briefing-card-cache`·`briefing-source-store`. 실험 원문 저장소는 `SourceStore(EXP_ROOT / "sources")` 다.
- **원문·원시 출력은 `EXP_ROOT`(`~/upgrade-eval/`)에만 둔다.** 저장소에는 코드·테스트·`manifest.json`(원문 없음)·테스트 픽스처(원문 없음)만 커밋한다.
- **시간 제한**
  - author 는 모든 실행에서 강제 상한 600초다. 운영 기준 360초 초과 여부는 순차 1회분의 소요 시간으로 판정한다.
  - codex 는 120초(운영 `_CODEX_TIMEOUT_S`).
- **동시 실행은 4개 이하.**
- **모델 id**
  - 요약: `global.anthropic.claude-sonnet-5`, `global.anthropic.claude-sonnet-5-5`, `global.anthropic.claude-opus-5-5`, `global.anthropic.claude-haiku-5-5`
  - 검증(codex `model`): `openai.gpt-6-astra`, `openai.gpt-6-sol`, `openai.gpt-6.1-sol`, `openai.gpt-6-luna`, `openai.gpt-5.5`
  - 판정(Converse): `us.openai.gpt-6-astra`, `global.openai.gpt-6.1-sol`
  - 제3계열 후보: `global.xai.grok-4.7`, `global.moonshotai.kimi-k3`, `global.zai.glm-5.3`, `us.amazon.nova-premier-v1:0`
- **알려진 버그(F1 잘림 경고, F2 숫자 오판)는 실험 중 고치지 않는다.**
- **게이트(멈추고 사용자에게 묻는 지점)**
  - 첫 유료 실행 전 코드 리뷰
  - Stage B 결과 뒤 재승인(§14-2)
  - GPT 판정자 둘 다 기준 미달이면 채점 전에 멈춤
  - 사람 확인 2회(D2)
- **배포는 하지 않는다**(§14-4 보류). `deploy_scheduler` 를 다시 실행하지 않는다.
- **표기:** 확인하지 않은 가격은 결과와 리포트에 '미확인'으로 적는다.
- **언어:** 문서·docstring·주석은 한국어 우선이고, 식별자·로그·CLI 플래그는 영어다.
- **시드:** 20261017(`common.SEED`) — 선정, 무작위 순서, 부트스트랩에 공통으로 쓴다.
- **커밋:** 브랜치 `upgrade-eval` 에만 하고 push 하지 않는다. 메시지 끝에 `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` 를 붙인다.
- **검사 명령:** `uv run pytest tests/test_upgrade_eval_*.py -q`, `uv run ruff check scripts/upgrade_eval tests/test_upgrade_eval_*.py`
- **새 테스트는 AWS·CLI 를 호출하지 않는다.** client 와 runner 는 주입받는다.

## Review Focus

1. **CLI 비정상 출력:** 빈 stdout, JSON 아님, 이벤트 누락, rc≠0, 시간 초과. 실행은 계속되고 기록만 남아야 하며, 검증 판정은 절대 VERIFIED 가 되면 안 된다. → Task 3 `test_certify_is_fail_closed`, Task 4 `test_runner_error_raises_after_logging`
2. **'다.' 로 끝나지 않는 문장:** 따옴표로 끝남, 소수점 `3.5`, 약어 `U.S.`, 영어 문장. 요약 문장 분리가 이런 경우에 깨지면 안 된다. → Task 5 `test_split_sentences_korean_and_edge_cases`
3. **판정자 응답이 스키마를 벗어남:** 없는 라벨, 범위 밖 문장 번호, 원문에 없는 인용, 빈 목록. 거부한 뒤 1회 재시도하고, 그래도 실패하면 기록한 뒤 집계에서 빼고 개수를 보고해야 한다. → Task 9 `test_parse_fidelity_rejects_unknown_label_and_bad_index`, `test_converse_retries_once_then_errors`
4. **중단 후 재실행:** 이미 끝난 유료 호출을 다시 하지 않아야 한다. → Task 2 `test_jsonl_roundtrip_and_resume_keys`, Task 8 `test_resume_skips_done`
5. **층의 후보 부족이나 채울 수 없는 조건:** 조용히 넘어가지 말고, 부족분과 이유를 manifest 에 기록해야 한다. → Task 6 `test_shortfall_is_reported`

**진행 순서와 비용**
- 코드 단계는 유료 실행을 기다리지 않고 먼저 진행해도 된다.
- 유료 실행: Task 1 프로브(<$1) → Task 7 Stage B(~$50–60) → [재승인] → Task 8 Stage A(요약 ~$30–40 + 검증, 재승인 금액) → Task 10 판정(검증 ~$5, 핵심 사실 ~$2, 채점 ~$80–100, 참고 비교 ~$5)

---

### Task 1: 작업 공간·CLI 준비와 사전 확인

**Files:**
- Create(커밋): `tests/fixtures/codex_json_sample_0142.jsonl`, `tests/fixtures/codex_json_sample_0163.jsonl` — 원문이 없는 장난감 claim 출력
- Copy(커밋): 설계 문서, 이 계획, `docs/README.md` 색인 두 줄

**Interfaces:**
- Produces:
  - `~/upgrade-eval/{bin,sources,runs,results,judge,codex-home}`
  - 버전별 CLI 설치본
  - `~/upgrade-eval/results/setup.md`: `E`(codex effort), `EFFORT_VIA`(`env`|`flag`), `REASONING_IN_OUTPUT`(bool)

- [ ] **Step 1: worktree 를 만든다**

Run: `git -C /home/ubuntu/Agent-Claude-Code-With-Codex worktree add -b upgrade-eval /home/ubuntu/Agent-Claude-Code-With-Codex-upgrade-eval 221701a`
Expected: `git -C /home/ubuntu/Agent-Claude-Code-With-Codex-upgrade-eval log -1 --format=%h` → `221701a`

- [ ] **Step 2: 문서를 옮기고 기준 테스트를 확인한다**

메인 트리의 설계·계획 파일과 `docs/README.md` 의 `claude-codex-upgrade` 색인 블록을 worktree 에 복사한다.
Run: `cd /home/ubuntu/Agent-Claude-Code-With-Codex-upgrade-eval && uv sync && uv run pytest -q`
Expected: 모두 통과(운영 커밋 기준선).

```bash
git add docs/superpowers/specs/2026-10-17-claude-codex-upgrade-design.md docs/superpowers/plans/2026-10-17-claude-codex-upgrade.md docs/README.md
git commit -m "docs(upgrade-eval): 업그레이드 비교 설계·실행 계획"
```

- [ ] **Step 3: 실험 디렉토리와 CLI 를 설치한다(전역 설치 금지)**

Run:
```bash
mkdir -p ~/upgrade-eval/{bin,sources,runs,results,judge,codex-home}
for v in 2.1.195 2.1.301; do npm install --prefix ~/upgrade-eval/bin/claude-$v @anthropic-ai/claude-code@$v; done
for v in 0.142.2 0.163.0; do npm install --prefix ~/upgrade-eval/bin/codex-$v @openai/codex@$v; done
```
Expected:
- `~/upgrade-eval/bin/claude-2.1.301/node_modules/.bin/claude --version` 에 2.1.301 이 나온다(2.1.195 도 같은 방식).
- `~/upgrade-eval/bin/codex-0.163.0/node_modules/.bin/codex --version` 에 0.163.0 이 나온다(0.142.2 도 같은 방식).

- [ ] **Step 4: 프로브 A — effort 주입 방식을 확인한다(< $0.3)**

- 2.1.301 · Sonnet 5.5 · 허용 목록 env 로, 같은 고정 프롬프트("다음 문단을 한 문장으로 요약하라: …" 300자)를 두 번 돌린다.
  - 한 번은 `CLAUDE_CODE_EFFORT_LEVEL=low`, 한 번은 `high`.
- 판정: envelope `usage` 의 thinking/output 토큰이 high > low 이면 `EFFORT_VIA=env` 다.
- 차이가 없으면 env 를 빼고 `--effort low|high` 로 다시 해서 차이를 확인하고 `EFFORT_VIA=flag` 로 정한다.

- [ ] **Step 5: 프로브 B — codex `--json` 과 기본 effort 를 확인한다(< $0.3)**

- `~/upgrade-eval/codex-home/<verifier>/config.toml` 을 만든다.
  - 내용은 `src/briefing/runtime/container/codex_config.toml` 사본이고, `model` 만 바꾼다.
  - 대상 verifier: `gpt-6-astra`, `gpt-6-sol`, `gpt-6.1-sol`, `gpt-6-luna`, `gpt-5.5`.
- 0.142.2(`gpt-5.5`)와 0.163.0(`gpt-6-sol`)으로 장난감 envelope 의 `_build_codex_prompt` 출력을 `codex exec --skip-git-repo-check --json` 으로 실행한다(`stdin=/dev/null`).
- 확인할 것:
  - (a) rc=0 — stdin 회귀가 없다
  - (b) `item.completed`(`item.type=agent_message`)와 `turn.completed.usage` 의 네 키가 있다
  - (c) `output_tokens` 에 reasoning 이 포함되는지. codex 문서·소스 문자열로 확인한다. 모르면 `REASONING_IN_OUTPUT=True` 로 두고 비용을 '추정'으로 표기한다.
  - (d) 0.142.2 의 기본 `model_reasoning_effort`. `codex --help`·문서·바이너리 문자열로 확인하고, 모르면 `E=medium` 으로 두고 '운영 기본값 미확인'으로 표기한다.
- 그다음 모든 `config.toml` 에 `model_reasoning_effort = "<E>"` 를 넣는다.
- 원시 출력은 `~/upgrade-eval/runs/probes/` 에 저장한다. 두 출력을 테스트 픽스처로 복사한다(원문이 없는 장난감 claim 이다).

- [ ] **Step 6: 결과를 기록하고 픽스처를 커밋한다**

`~/upgrade-eval/results/setup.md` 에 버전, `E`, `EFFORT_VIA`, `REASONING_IN_OUTPUT`, 프로브 비용을 적는다.
```bash
git add tests/fixtures/codex_json_sample_0142.jsonl tests/fixtures/codex_json_sample_0163.jsonl
git commit -m "test(upgrade-eval): codex --json 실제 출력 픽스처(0.142.2·0.163.0)"
```

---

### Task 2: 공통 유틸

**Files:**
- Create: `scripts/upgrade_eval/__init__.py`(한 줄 docstring), `scripts/upgrade_eval/common.py`
- Test: `tests/test_upgrade_eval_common.py`

**Interfaces:**
- Produces:
  - `EXP_ROOT: Path` — env `UPGRADE_EVAL_ROOT`, 없으면 `Path.home() / "upgrade-eval"`
  - `SEED = 20261017`
  - `append_jsonl(path: Path, record: dict) -> None`
  - `read_jsonl(path: Path) -> list[dict]`
  - `done_keys(path: Path, fields: tuple[str, ...]) -> set[tuple]`
  - `source_kind(url: str) -> str` — 반환값은 `"뉴스"`, `"기업 발표"`, `"기술·연구"`, `"커뮤니티"`, `"미상"` 중 하나
  - `source_lang(url: str) -> str` — `"ko"` 또는 `"en"`

모든 테스트 파일의 머리는 아래와 같다.
```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from upgrade_eval import common
```

- [ ] **Step 1: 실패하는 테스트를 쓴다**

```python
def test_jsonl_roundtrip_and_resume_keys(tmp_path):
    p = tmp_path / "r.jsonl"
    common.append_jsonl(p, {"model": "m", "pass": 1, "claim": "c1", "v": "가"})
    common.append_jsonl(p, {"model": "m", "pass": 2, "claim": "c1"})
    assert common.read_jsonl(p)[0]["v"] == "가"
    assert common.done_keys(p, ("model", "pass", "claim")) == {("m", 1, "c1"), ("m", 2, "c1")}
    assert common.read_jsonl(tmp_path / "missing.jsonl") == []

def test_source_kind_and_lang():
    k = common.source_kind
    assert k("https://www.aitimes.com/news/articleView.html?idxno=1") == "뉴스"
    assert k("https://the-decoder.com/x/") == "뉴스"
    assert k("https://discuss.pytorch.kr/t/x/1") == "커뮤니티"
    assert k("https://www.anthropic.com/engineering/x") == "기술·연구"
    assert k("https://research.google/blog/x/") == "기술·연구"
    assert k("https://developers.googleblog.com/x/") == "기술·연구"
    assert k("https://aws.amazon.com/blogs/machine-learning/x/") == "기술·연구"
    assert k("https://aws.amazon.com/ko/blogs/tech/x/") == "기술·연구"
    assert k("https://www.anthropic.com/news/x") == "기업 발표"
    assert k("https://claude.com/blog/x") == "기업 발표"
    assert k("https://blog.google/technology/ai/x/") == "기업 발표"
    assert k("https://deepmind.google/discover/blog/x/") == "기업 발표"
    assert common.source_lang("https://aws.amazon.com/ko/blogs/tech/x/") == "ko"
    assert common.source_lang("https://www.aitimes.com/news/x") == "ko"
    assert common.source_lang("https://the-decoder.com/x/") == "en"
```

- [ ] **Step 2: 실패를 확인한다** — Run: `uv run pytest tests/test_upgrade_eval_common.py -v` / Expected: FAIL(`ModuleNotFoundError: upgrade_eval`)

- [ ] **Step 3: `common.py` 를 구현한다**

- 분류 규칙은 `criteria-application-audit.md` 의 '측정 방법'과 같다.
- `done_keys` 는 레코드에 없는 필드를 `None` 으로 채운 튜플을 돌려준다.

- [ ] **Step 4: 통과를 확인한다** — Run: `uv run pytest tests/test_upgrade_eval_common.py -v` / Expected: PASS

- [ ] **Step 5: 커밋한다**
```bash
git add scripts/upgrade_eval/__init__.py scripts/upgrade_eval/common.py tests/test_upgrade_eval_common.py
git commit -m "feat(upgrade-eval): 공통 유틸 — JSONL 기록·재개 키·소스 종류 분류"
```

---

### Task 3: codex `--json` 러너

**Files:**
- Create: `scripts/upgrade_eval/codex_runner.py`
- Test: `tests/test_upgrade_eval_codex_runner.py`

**Interfaces:**
- Consumes: `briefing.core.verification.certifier` 의 `Envelope`, `CertVerdict`, `_build_codex_prompt(envelope) -> str`, `_last_json_object(text) -> dict | None`
- Produces:
  - `@dataclass(frozen=True) class CodexModel: name: str; codex_version: str; model: str`
    - 속성 `codex_bin -> Path`(`EXP_ROOT/bin/codex-<ver>/node_modules/.bin/codex`), `codex_home -> Path`(`EXP_ROOT/codex-home/<name>`)
  - `VERIFIERS: dict[str, CodexModel]`

    | key | codex 버전 | model |
    |---|---|---|
    | `gpt-6-astra` | 0.163.0 | `openai.gpt-6-astra` |
    | `gpt-6-sol` | 0.163.0 | `openai.gpt-6-sol` |
    | `gpt-6.1-sol` | 0.163.0 | `openai.gpt-6.1-sol` |
    | `gpt-6-luna` | 0.163.0 | `openai.gpt-6-luna` |
    | `gpt-5.5` | 0.142.2 | `openai.gpt-5.5` |

  - `@dataclass class CodexRun: final_text: str | None; usage: dict; duration_ms: int; returncode: int | None; error: str | None`
  - `parse_codex_jsonl(stdout: str) -> tuple[str | None, dict]`
  - `run_codex_json(prompt: str, model: CodexModel, *, timeout_s: int = 120) -> CodexRun`
  - `certify_entailment_json(claim_id: str, envelope: Envelope, model: CodexModel, *, timeout_s: int = 120, runner=run_codex_json) -> tuple[CertVerdict, CodexRun]`
    - 성공 시 `CertVerdict.model = f"codex:{model.name}"`
    - 실패 시 `CertVerdict(claim_id, "DEMOTED", <사유>, "codex-error")`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

```python
ENV = Envelope(source_excerpt="원문", claim_text="A사는 출시했다", claim_type="entailment", schema="{}")

def test_parse_takes_last_agent_message_and_usage():
    out = "\n".join([
        '{"type":"thread.started","thread_id":"t"}',
        '{"type":"item.completed","item":{"type":"agent_message","text":"draft"}}',
        "not json",
        '{"type":"item.completed","item":{"type":"agent_message","text":"{\\"verdict\\":\\"VERIFIED\\",\\"evidence\\":\\"e\\"}"}}',
        '{"type":"turn.completed","usage":{"input_tokens":9000,"cached_input_tokens":0,"output_tokens":40,"reasoning_output_tokens":12}}',
    ])
    text, usage = codex_runner.parse_codex_jsonl(out)
    assert text.startswith('{"verdict"')
    assert usage == {"input_tokens": 9000, "cached_input_tokens": 0, "output_tokens": 40, "reasoning_output_tokens": 12}

def test_parse_recorded_samples():
    for name in ("codex_json_sample_0142.jsonl", "codex_json_sample_0163.jsonl"):
        text, usage = codex_runner.parse_codex_jsonl((FIXTURES / name).read_text(encoding="utf-8"))
        assert text and "verdict" in text and usage["input_tokens"] > 0

def test_parse_missing_message():
    assert codex_runner.parse_codex_jsonl('{"type":"turn.completed","usage":{}}') == (None, {})

def test_certify_is_fail_closed():
    for run in (CodexRun(None, {}, 5, 1, "rc=1"), CodexRun(None, {}, 120000, None, "timeout"),
                CodexRun("not json", {}, 5, 0, None), CodexRun('{"verdict":"MAYBE"}', {}, 5, 0, None)):
        v, _ = codex_runner.certify_entailment_json("C1", ENV, VERIFIERS["gpt-6-sol"], runner=lambda *a, **k: run)
        assert v.verdict == "DEMOTED" and v.model == "codex-error"

def test_certify_passes_verdict_through():
    run = CodexRun('{"verdict":"BLOCKED","evidence":"반대"}', {"input_tokens": 1}, 5, 0, None)
    v, r = codex_runner.certify_entailment_json("C1", ENV, VERIFIERS["gpt-5.5"], runner=lambda *a, **k: run)
    assert (v.verdict, v.model, r.usage) == ("BLOCKED", "codex:gpt-5.5", {"input_tokens": 1})
```

- [ ] **Step 2: 실패를 확인한다** — Run: `uv run pytest tests/test_upgrade_eval_codex_runner.py -v` / Expected: FAIL

- [ ] **Step 3: `codex_runner.py` 를 구현한다**

- `run_codex_json` 은 운영 `_run_codex` 와 같은 형태다(새 빈 cwd, `stdin=DEVNULL`, 끝나면 cwd 삭제).
- 명령은 `[codex_bin, "exec", "--skip-git-repo-check", "--json", prompt]` 다.
- env 는 허용 목록만이다: `PATH`, `HOME`(호출마다 새 빈 디렉토리), `CODEX_HOME`, `AWS_REGION=us-east-1`, AWS 파일 두 개, `LANG`.
- 시간 초과면 `returncode=None, error="timeout"`, rc≠0 이면 `error=f"rc={rc}: {stderr[:200]}"` 다.

- [ ] **Step 4: 통과를 확인한다** — Run: `uv run pytest tests/test_upgrade_eval_codex_runner.py -v` / Expected: PASS

- [ ] **Step 5: 커밋한다**
```bash
git add scripts/upgrade_eval/codex_runner.py tests/test_upgrade_eval_codex_runner.py
git commit -m "feat(upgrade-eval): codex --json 러너 — 이벤트 파서·토큰 기록·fail-closed 판정"
```

---

### Task 4: author 러너

**Files:**
- Create: `scripts/upgrade_eval/author_runner.py`
- Test: `tests/test_upgrade_eval_author_runner.py`

**Interfaces:**
- Consumes:
  - `briefing.core.authoring.author` 의 `build_system_prompt`, `build_user_prompt`, `_build_revise_prompt`, `_parse_card_json`, `_to_draft_card`, `DraftCard`
  - `briefing.core.lenses.resolve_lens`
  - `briefing.core.stores.source_store.FrozenSource`
- Produces:
  - `@dataclass(frozen=True) class Arm: key: str; model_id: str; cli_version: str; effort: str | None`
  - `ARMS: dict[str, Arm]`

    | key | model_id | CLI | effort |
    |---|---|---|---|
    | `A0` | `global.anthropic.claude-sonnet-5` | 2.1.195 | `None` |
    | `A1` | `global.anthropic.claude-sonnet-5` | 2.1.301 | `None` |
    | `A2` | `global.anthropic.claude-sonnet-5-5` | 2.1.301 | `"medium"` |
    | `A3` | `global.anthropic.claude-sonnet-5-5` | 2.1.301 | `"high"` |
    | `A4` | `global.anthropic.claude-opus-5-5` | 2.1.301 | `"medium"` |
    | `A5` | `global.anthropic.claude-haiku-5-5` | 2.1.301 | `"medium"` |

  - `EFFORT_VIA: str` — Task 1 의 값(`"env"` 또는 `"flag"`)
  - `@dataclass class AuthorRun: kind: str; text: str; cost_usd: float | None; usage: dict; stop_reason: str | None; duration_ms: int; returncode: int | None; error: str | None`
  - `build_env(arm: Arm, *, home_dir: Path) -> dict[str, str]`
  - `run_author(system_prompt: str, user_prompt: str, arm: Arm, *, timeout_s: int = 600) -> AuthorRun`
  - `make_author_fns(arm: Arm, *, log: list[AuthorRun], timeout_s: int = 600, runner=run_author) -> tuple[DraftFn, ReviseFn]`
    - `draft_fn(source, user, settings) -> DraftCard`
    - `revise_fn(source, user, settings, *, prior, failed_ids) -> DraftCard`
    - 둘 다 `author.draft_card`/`revise_claims` 와 같은 시그니처라 `gate.produce_card` 에 그대로 주입한다.
    - 러너 오류는 기록한 뒤 `RuntimeError(run.error)` 로 올린다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

```python
CARD = '{"summary":"S","why_it_matters":"W","claims":[{"id":"C1","text":"t","claim_type":"entailment","importance":"core"}]}'

def test_env_is_allowlisted(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.setenv("CLAUDECODE", "1")
    env = author_runner.build_env(author_runner.ARMS["A3"], home_dir=tmp_path)
    assert env["HOME"] == str(tmp_path) and env["ANTHROPIC_MODEL"] == "global.anthropic.claude-sonnet-5-5"
    assert env["AWS_REGION"] == "us-east-1" and env["CLAUDE_CODE_USE_BEDROCK"] == "1"
    assert "ANTHROPIC_API_KEY" not in env and "CLAUDECODE" not in env
    if author_runner.EFFORT_VIA == "env":
        assert env["CLAUDE_CODE_EFFORT_LEVEL"] == "high"
    assert "CLAUDE_CODE_EFFORT_LEVEL" not in author_runner.build_env(author_runner.ARMS["A0"], home_dir=tmp_path)

def test_draft_and_revise_fns_parse_and_log():
    fake = lambda s, u, arm, timeout_s: AuthorRun("", CARD, 0.01, {}, "end_turn", 10, 0, None)
    log = []
    draft, revise = author_runner.make_author_fns(author_runner.ARMS["A2"], log=log, runner=fake)
    d = draft(SRC, FACT_USER, SETTINGS)
    assert d.summary == "S" and d.headline == SRC.title
    revise(SRC, FACT_USER, SETTINGS, prior=d, failed_ids=("C1",))
    assert [r.kind for r in log] == ["draft", "revise"]

def test_runner_error_raises_after_logging():
    bad = lambda *a, **k: AuthorRun("", "", None, {}, None, 600000, None, "timeout")
    log = []
    draft, _ = author_runner.make_author_fns(author_runner.ARMS["A2"], log=log, runner=bad)
    with pytest.raises(RuntimeError):
        draft(SRC, FACT_USER, SETTINGS)
    assert log[0].error == "timeout"
```

- [ ] **Step 2: 실패를 확인한다** — Run: `uv run pytest tests/test_upgrade_eval_author_runner.py -v` / Expected: FAIL

- [ ] **Step 3: `author_runner.py` 를 구현한다**

- `run_author`
  - 호출마다 새 빈 HOME(`.claude.json` 복사)과 새 빈 cwd 를 만든다.
  - CLI 는 `EXP_ROOT/bin/claude-<ver>/node_modules/.bin/claude` 다.
  - `EFFORT_VIA == "flag"` 이고 effort 가 있으면 `--effort <effort>` 를 더한다.
- envelope 처리
  - `result` 를 `text` 로, `total_cost_usd` 를 `cost_usd` 로 옮긴다.
  - `usage`, `stop_reason`(없으면 `subtype`)을 그대로 남긴다.
  - `is_error` 가 참이면 `error` 로 기록한다.
- 시스템 프롬프트는 `build_system_prompt(lens_guidance=resolve_lens(user.lens).guidance, skill_md=user.skill_md)` 로 운영과 같게 만든다.

- [ ] **Step 4: 통과를 확인한다** — Run: `uv run pytest tests/test_upgrade_eval_author_runner.py -v` / Expected: PASS

- [ ] **Step 5: 커밋한다**
```bash
git add scripts/upgrade_eval/author_runner.py tests/test_upgrade_eval_author_runner.py
git commit -m "feat(upgrade-eval): author 러너 — 허용 목록 env·빈 HOME·조건 6가지·DI 함수"
```

---

### Task 5: 코드 지표

**Files:**
- Create: `scripts/upgrade_eval/metrics.py`
- Test: `tests/test_upgrade_eval_metrics.py`

**Interfaces:**
- Consumes:
  - `ab_prompt._HEDGE`, `ab_prompt._depth` — `scripts/` 가 `sys.path` 에 있으므로 `import ab_prompt` 로 가져온다
  - `briefing.core.verification.numeric` 의 `scan`, `contains`
- Produces:
  - `split_sentences(text: str) -> list[str]` — `다.`·`다."`·`다”.` 뒤 공백에서 나눈다
  - `long_sentence_ratio(sentences: list[str], limit: int = 150) -> float`
  - `has_hedge(text: str) -> bool`
  - `deepest_position(source: str, summary: str) -> float | None`
  - `transliterated_names(text: str) -> list[str]` — 정규식 `앤트로픽|오픈AI|오픈에이아이|클로드|딥마인드|제미나이|챗GPT|구글|아마존|엔비디아|마이크로소프트|메타(?![데버])`
  - `uncovered_numbers(summary: str, claims: list[str]) -> list[float]`
  - `uncovered_names(summary: str, claims: list[str]) -> list[str]` — 요약의 라틴 고유명사(`[A-Z][A-Za-z0-9.\-]{2,}`) 중 어떤 claim 에도 없는 것
  - `why_new_numbers(why: str, summary: str, claims: list[str]) -> list[float]`
  - `quote_mismatches(summary: str, source: str) -> list[str]` — 따옴표 안 한글 인용이 원문 부분 문자열이 아닌 것. 원문의 한글 비율이 10% 미만이면 번역 인용으로 보고 건너뛴다.
  - `repeats_title(title: str, first_sentence: str) -> bool` — 같은 언어일 때만, 토큰 자카드 ≥ 0.6
  - `is_known_f2_block(claim_text: str, evidence: str) -> bool`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

```python
def test_split_sentences_korean_and_edge_cases():
    s = 'A사는 3.5% 늘었다고 밝혔다. U.S. 기준이다. 그는 "준비됐다."고 했다. 그는 "끝났다”. 마지막'
    assert metrics.split_sentences(s) == [
        "A사는 3.5% 늘었다고 밝혔다.", "U.S. 기준이다.", '그는 "준비됐다."고 했다.', '그는 "끝났다”.', "마지막"]

def test_long_sentence_ratio():
    assert metrics.long_sentence_ratio(["가" * 151, "나" * 150]) == 0.5

def test_numbers_cover_and_why():
    assert metrics.uncovered_numbers("가격은 74.99달러다.", ["가격은 74.99달러다."]) == []
    assert metrics.uncovered_numbers("31,200명이 참여했다.", ["참여자가 많았다."]) == [31200.0]
    assert metrics.why_new_numbers("6배 빠르다", "속도가 늘었다.", ["속도가 늘었다."]) == [6.0]
    assert metrics.uncovered_names("Anthropic이 Claude Sonnet을 냈다.", ["Anthropic이 새 모델을 냈다."]) == ["Claude", "Sonnet"]

def test_transliteration():
    assert metrics.transliterated_names("앤트로픽과 오픈AI, 구글이") == ["앤트로픽", "오픈AI", "구글"]
    assert metrics.transliterated_names("메타데이터를 쓰는 Anthropic") == []

def test_quote_mismatch_same_language_only():
    src = '그는 "준비됐다"고 말했다. 이어 다른 말을 했다.'
    assert metrics.quote_mismatches('그는 "준비됐다"고 했다.', src) == []
    assert metrics.quote_mismatches('그는 "다 준비됐다"고 했다.', src) == ["다 준비됐다"]
    assert metrics.quote_mismatches('그는 "우리는 준비됐다"고 했다.', 'He said "we are ready".') == []

def test_known_f2_patterns():
    assert metrics.is_known_f2_block("입력 토큰 100만 개당 2달러이다.", "원문에 없는 수치: 수량=[1000000.0]")
    assert metrics.is_known_f2_block("2분기부터 함께 일해왔다.", "원문에 없는 수치: 수량=[2.0]")
    assert metrics.is_known_f2_block("121개국 중 2위다.", "원문에 없는 수치: 수량=[2.0]")
    assert metrics.is_known_f2_block("기부액의 3배다.", "원문에 없는 수치: 수량=[3.0]")
    assert metrics.is_known_f2_block("약 40년간의 연구다.", "원문에 없는 수치: 수량=[40.0]")
    assert metrics.is_known_f2_block("건당 약 1만2000달러를 받았다.", "원문에 없는 수치: 수량=[2000.0, 10000.0]")
    assert not metrics.is_known_f2_block("매출은 46억달러다.", "원문에 없는 수치: 수량=[46.0]")

def test_hedge_and_title_repeat():
    assert metrics.has_hedge("확인되지 않았다") and not metrics.has_hedge("출시했다")
    assert metrics.repeats_title("앤트로픽, 새 모델 공개", "앤트로픽, 새 모델 공개했다.")
    assert not metrics.repeats_title("Anthropic releases Claude", "Anthropic이 Claude 새 버전을 공개했다.")
```

- [ ] **Step 2: 실패를 확인한다** — Run: `uv run pytest tests/test_upgrade_eval_metrics.py -v` / Expected: FAIL

- [ ] **Step 3: `metrics.py` 를 구현한다**

- `is_known_f2_block`: evidence 가 `원문에 없는 수치` 로 시작하고, claim 이 아래 패턴 중 하나를 포함하면 참이다.
  - `\d+만 (개|토큰)?당`
  - `\d+배`
  - `\d+년간`
  - `\d+위`
  - `\d+분기`
  - `\d+만\s?\d{3,4}`

- [ ] **Step 4: 통과를 확인한다** — Run: `uv run pytest tests/test_upgrade_eval_metrics.py -v` / Expected: PASS

- [ ] **Step 5: 커밋한다**
```bash
git add scripts/upgrade_eval/metrics.py tests/test_upgrade_eval_metrics.py
git commit -m "feat(upgrade-eval): 코드 지표 — 문장·150자·유보·이름 표기·숫자 커버·인용·F2 표기"
```

---

### Task 6: 기사 선정

**Files:**
- Create: `scripts/upgrade_eval/select_articles.py`, `scripts/upgrade_eval/manifest.json`(생성물, 커밋)
- Test: `tests/test_upgrade_eval_select.py`

**Interfaces:**
- Consumes:
  - `common.source_kind`/`source_lang`/`SEED`/`EXP_ROOT`, `metrics.has_hedge`
  - `numeric.scan`, `SourceStore`
- Produces:
  - `@dataclass(frozen=True) class CardRow: source_id: str; url: str; title: str; kind: str; lang: str; length: int; truncated: bool; has_numbers: bool; has_hedge: bool; has_quote: bool`
    - `truncated` 는 `length >= 7900` 이다.
  - `QUOTAS = {("뉴스", "ko"): 2, ("뉴스", "en"): 2, ("기업 발표", None): 3, ("기술·연구", None): 3, ("커뮤니티", None): 2}`
  - `select_articles(rows: list[CardRow], *, seed: int = SEED) -> dict` — 반환값:
    - `"articles"`: 항목마다 `source_id, url, title, kind, lang, length, truncated, has_numbers, has_hedge, has_quote, human_check, reason`
    - `"shortfalls"`: 부족분과 이유 목록
  - `load_manifest() -> list[dict]`
  - `main() -> None`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

```python
def test_quotas_constraints_and_determinism():
    rows = make_rows()   # 층마다 10건, 길이 1,000–7,999·속성 다양
    m1, m2 = select_articles(rows, seed=1), select_articles(rows, seed=1)
    assert m1 == m2
    arts = m1["articles"]
    strata = Counter((a["kind"], a["lang"] if a["kind"] == "뉴스" else None) for a in arts)
    assert strata == Counter(QUOTAS)
    assert 3 <= sum(a["truncated"] for a in arts) <= 5 and any(a["length"] < 3000 for a in arts)
    assert sum(a["has_numbers"] for a in arts) >= 2 and sum(a["has_hedge"] for a in arts) >= 2
    assert any(a["has_quote"] for a in arts)
    assert sorted(a["kind"] for a in arts if a["human_check"]) == ["기술·연구", "기업 발표", "뉴스"]

def test_shortfall_is_reported():
    rows = [r for r in make_rows() if r.kind != "커뮤니티"] + make_rows(kind="커뮤니티", n=1)
    m = select_articles(rows, seed=1)
    assert any("커뮤니티" in s for s in m["shortfalls"]) and len(m["articles"]) == 11
```

- [ ] **Step 2: 실패를 확인한다** — Run: `uv run pytest tests/test_upgrade_eval_select.py -v` / Expected: FAIL

- [ ] **Step 3: `select_articles.py` 를 구현한다**

- 층마다 `random.Random(seed)` 로 뽑는다.
- 그다음 조건을 채운다:
  - 잘린 원문 3–5건(목표 4)
  - 3,000자 미만 1건 이상
  - 숫자 있는 글 2건 이상, 유보 있는 글 2건 이상, 인용 있는 글 1건 이상
- 조건을 채우려고 바꿀 때는 같은 층 안에서 바꾸고 `reason="교체: <조건>"` 을 남긴다. 채울 수 없으면 `shortfalls` 에 적는다.
- `human_check` 는 뉴스·기업 발표·기술·연구에서 첫 번째로 뽑힌 기사다.
- `main()`
  - 운영 card-cache 를 `scan`(`ProjectionExpression="card_json"`)해 사실층(`based_on` 비어 있음)·PUBLISH 만 남긴다.
  - source-store 는 `get_item` 으로 url·title·text 를 읽어 `CardRow` 를 만든다.
  - manifest 를 쓰고, 고른 원문을 `SourceStore(EXP_ROOT/"sources").freeze(...)` 로 복사한다. 반환된 `source_id` 가 운영 id 와 같은지 `assert` 한다.

- [ ] **Step 4: 통과를 확인한다** — Run: `uv run pytest tests/test_upgrade_eval_select.py -v` / Expected: PASS

- [ ] **Step 5: 실제로 고른다(읽기 전용)**

Run: `uv run python scripts/upgrade_eval/select_articles.py`
Expected: `manifest.json` 에 12건이 있고 `shortfalls` 가 비어 있다. 12개 `source_id` 를 로컬 저장소에서 읽을 수 있다.

- [ ] **Step 6: 커밋한다**
```bash
git add scripts/upgrade_eval/select_articles.py scripts/upgrade_eval/manifest.json tests/test_upgrade_eval_select.py
git commit -m "feat(upgrade-eval): 기사 12건 층화 선정 — manifest(원문 없음)·로컬 사본"
```

---

### Task 7: Stage B — 검증 AI 비교

**Files:**
- Create: `scripts/upgrade_eval/stage_b.py`, `scripts/upgrade_eval/costs.py`(가격 자료형과 2차 출처 가격만; Task 11 이 확장)
- Test: `tests/test_upgrade_eval_stage_b.py`

**Interfaces:**
- Consumes:
  - `codex_runner.VERIFIERS`/`certify_entailment_json`, `select_articles.load_manifest`, `common`
  - `certifier._NUM_RE`, `gate._build_envelope`
- Produces:
  - `costs.py`
    - `@dataclass(frozen=True) class Price: input: float; output: float; cache_read: float | None; verified: bool; source: str` — 단위는 $/1M 토큰
    - `FALLBACK_PRICES: dict[str, Price]` — 2차 출처, `verified=False`:

      | verifier | 입력 | 출력 |
      |---|---|---|
      | `gpt-6-astra` | 10 | 50 |
      | `gpt-6-sol` | 2 | 10 |
      | `gpt-6.1-sol` | 2 | 10 |
      | `gpt-6-luna` | 0.10 | 0.50 |
      | `gpt-5.5` | 5 | 30 |

    - `codex_cost(usage: dict, price: Price, *, reasoning_in_output: bool = True) -> float`
  - `@dataclass(frozen=True) class ClaimItem: key: str; source_id: str; text: str; origin: str; planted_type: str | None = None; base_key: str | None = None`
  - `PLANTED_TYPES = ("주체 바꾸기", "유보→단정", "단계 격상", "귀속 삭제", "의미 반전", "사실 추가")`
  - `original_claims(cards: list[dict], source_ids: set[str]) -> list[ClaimItem]` — key 는 `f"{source_id[:12]}:{claim_id}"`
  - `validate_planted(planted: list[ClaimItem], originals: list[ClaimItem]) -> list[str]`
  - `@dataclass class ModelScore: catch_rate: float; catch_blocked_rate: float; fp_rate: float; fp_blocked: float; fp_demoted: float; consistency: float; cost_per_claim: float; cost_verified: bool; p50_ms: float; p95_ms: float; timeouts: int; n_true: int; n_uncertain: int`
  - `score_stage_b(records: list[dict], claims: list[ClaimItem], prices: dict[str, Price]) -> dict[str, ModelScore]`
  - `pick_winner(scores: dict[str, ModelScore], *, baseline: str = "gpt-5.5") -> str`
  - CLI 하위 명령: `build-claims`, `validate`, `run`, `latency`, `score`

규칙(설계 §6 그대로):
- **맞는 claim:** 원본 중 5개 모델의 1회차 판정에서 4개 이상 VERIFIED 인 것. 그 밖은 '불확실'이다.
- **비율:** 1·2회차 평균으로 낸다.
  - `catch_rate` = 심은 오류가 VERIFIED 가 아닌 비율
  - `fp_rate` = 맞는 claim 이 VERIFIED 가 아닌 비율(BLOCKED·DEMOTED 를 따로도 냄)
  - `consistency` = 1·2회차 판정이 같은 비율
- **처리 시간:** `pass == "seq"` 레코드로 잰다.
- **`pick_winner`**
  1. 검출률이 최고값 −0.05 이상이면서 기준선 이상인 모델만 남긴다.
  2. 그중 오탐률이 최저값 +0.02 이내인 모델만 남긴다.
  3. `(cost_per_claim, p95_ms)` 가 가장 작은 모델을 고른다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

```python
def test_original_claims_entailment_only():
    sid = "s" * 12
    cards = [{"decision": "PUBLISH", "card": {"source_id": sid, "based_on": [], "claims": [
        {"id": "C1", "text": "A사는 출시했다", "claim_type": "entailment", "importance": "core"},
        {"id": "C2", "text": "가격은 2달러다", "claim_type": "arithmetic", "importance": "core"},
        {"id": "C3", "text": "B는 3배다", "claim_type": "entailment", "importance": "supporting"}]}}]
    assert [c.key for c in stage_b.original_claims(cards, {sid})] == [f"{sid}:C1"]

def test_validate_planted_counts_and_digits():
    errs = stage_b.validate_planted(PLANTED_ONE_TYPE_FIVE_AND_A_DIGIT, ORIGINALS)
    assert any("유보→단정" in e and "5" in e for e in errs) and any("숫자" in e for e in errs)

def test_degenerate_demote_everything_loses():
    scores = stage_b.score_stage_b(RECORDS_WITH_LAZY_MODEL, CLAIMS, PRICES)   # 'lazy' 는 전부 DEMOTED
    assert scores["lazy"].catch_rate == 1.0 and scores["lazy"].fp_rate == 1.0
    assert stage_b.pick_winner(scores) != "lazy"

def test_pick_winner_rules():
    s = {"gpt-5.5": ms(catch=.80, fp=.05, cost=.04, p95=9000), "a": ms(catch=.90, fp=.08, cost=.10, p95=8000),
         "b": ms(catch=.87, fp=.07, cost=.02, p95=7000), "c": ms(catch=.70, fp=.01, cost=.001, p95=5000)}
    assert stage_b.pick_winner(s) == "b"   # c 는 기준선 미만, a·b 는 오탐 2%p 이내 → 비용이 낮은 b

def test_codex_cost_with_cache():
    p = costs.Price(2.0, 10.0, 0.5, False, "2차")
    usage = {"input_tokens": 10_000, "cached_input_tokens": 4_000, "output_tokens": 100, "reasoning_output_tokens": 50}
    assert costs.codex_cost(usage, p) == pytest.approx((6_000 * 2.0 + 4_000 * 0.5 + 100 * 10.0) / 1e6)
```

- [ ] **Step 2: 실패를 확인한다** — Run: `uv run pytest tests/test_upgrade_eval_stage_b.py -v` / Expected: FAIL

- [ ] **Step 3: `costs.py`·`stage_b.py` 를 구현한다**

- `run`: (모델, 회차, claim) 순서를 시드로 섞어 동시 4개 이하로 실행한다.
  - `EXP_ROOT/runs/stage_b/records.jsonl` 에 `{model, pass, claim_key, verdict, evidence, usage, duration_ms, returncode, error}` 를 쓴다.
  - `done_keys(("model", "pass", "claim_key"))` 로 이미 한 것은 건너뛴다.
- `latency`: 원본 30개(시드로 고름)를 모델마다 순서대로 1회 돌린다(`pass="seq"`).

- [ ] **Step 4: 통과를 확인한다** — Run: `uv run pytest tests/test_upgrade_eval_stage_b.py -v` / Expected: PASS

- [ ] **Step 5: 커밋한다**
```bash
git add scripts/upgrade_eval/stage_b.py scripts/upgrade_eval/costs.py tests/test_upgrade_eval_stage_b.py
git commit -m "feat(upgrade-eval): Stage B — claim 세트·심은 오류 검사·채점·승자 규칙"
```

- [ ] **Step 6: claim 세트를 만든다(무료)**

- `uv run python scripts/upgrade_eval/stage_b.py build-claims` 를 실행한다. `EXP_ROOT/stage_b/originals.jsonl` 이 생긴다.
- 설계자가 `EXP_ROOT/stage_b/planted.jsonl` 을 쓴다. 6가지 유형마다 6–8개, `base_key` 로 원본을 가리키고, 숫자는 넣지 않는다.
- Run: `stage_b.py validate` / Expected: 오류 0건.

- [ ] **Step 7: 게이트 — 첫 유료 실행 전 코드 리뷰**

- 새 리뷰어가 Task 2–7 코드를 점검한다. 볼 것: 허용 목록 env, fail-closed, 재개, 운영 DDB 쓰기 없음.
- 지적 사항을 고치고 커밋한다.

- [ ] **Step 8: 실행한다(유료, ~$50–60)**

Run: `stage_b.py run --passes 2 --concurrency 4` 다음에 `stage_b.py latency --n 30`
Expected: 레코드 수 = 5 모델 × 2회 × claim 수 + 5 × 30. 시간 초과는 개수를 기록한다.

- [ ] **Step 9: 채점하고 멈춘다(게이트 §14-2)**

- Run: `stage_b.py score`. `results/stage_b_scores.json` 과 `results/stage_b_summary.md` 가 생긴다.
- summary 에 들어갈 것:
  - 점수표와 승자. 2회 판정 일치율이 90% 미만인 모델에는 경고를 단다.
  - Stage A 예상 검증 비용 = 승자 `cost_per_claim` × (216 × manifest 카드의 평균 함의 claim 수 × 1.3)
  - 판정 예상 비용(~$80–110)
  - 가격 '미확인' 표기
- **사용자에게 보고하고 재승인을 받기 전에는 Task 8 Step 6 을 실행하지 않는다.**

---

### Task 8: Stage A — 요약 AI 비교

**Files:**
- Create: `scripts/upgrade_eval/stage_a.py`
- Test: `tests/test_upgrade_eval_stage_a.py`

**Interfaces:**
- Consumes:
  - `author_runner.ARMS`/`make_author_fns`/`AuthorRun`, `codex_runner.VERIFIERS`/`certify_entailment_json`
  - `gate.produce_card`, `gate._build_envelope`, `certifier._certify_arithmetic`
  - `pipeline._FACT_USER`, `config.load_settings`, `SourceStore`, `select_articles.load_manifest`, `common`
- Produces:
  - `make_verify_fn(verifier: CodexModel, store: SourceStore, log: list[dict]) -> Callable[[DraftCard], tuple[CertVerdict, ...]]`
    - 숫자가 든 claim 은 `_certify_arithmetic` 으로, 나머지는 `certify_entailment_json` 으로 보낸다.
    - codex 호출마다 `{claim_id, usage, duration_ms, error}` 를 `log` 에 남긴다.
  - `run_one(arm: Arm, source: FrozenSource, rep: int, *, sequential: bool, verifier: CodexModel, store: SourceStore, settings: Settings, timeout_s: int = 600, author_fns: tuple | None = None, verify_fn: Callable | None = None) -> dict`
    - `author_fns`·`verify_fn` 은 테스트 주입용이다. `None` 이면 실제 러너를 쓴다.
    - 반환 레코드 필드: `arm, source_id, rep, sequential, decision`(`PUBLISH`|`QUARANTINE`|`ERROR`), `attempts, summary, why, claims, verdicts, first_draft_summary, author_runs, codex_calls, duration_ms, over_360, error`
  - `run_stage_a(arm_keys: list[str], *, verifier: str, reps: int = 3, seq_rep: int = 1, concurrency: int = 4) -> None`
    - 결과는 `EXP_ROOT/runs/stage_a/records.jsonl` 에 쓴다.
    - `(arm, source_id, rep)` 로 이미 한 것은 건너뛴다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

```python
def test_run_one_records_publish():
    rec = stage_a.run_one(ARM, SRC, 2, sequential=False, verifier=V, store=STORE, settings=SETTINGS,
                          author_fns=fake_author_fns(summary="S"), verify_fn=lambda card: verified_all(card))
    assert (rec["decision"], rec["attempts"], rec["first_draft_summary"]) == ("PUBLISH", 1, "S")

def test_run_one_records_error_on_timeout():
    rec = stage_a.run_one(ARM, SRC, 2, sequential=False, verifier=V, store=STORE, settings=SETTINGS,
                          author_fns=fake_author_fns(raise_error="timeout"), verify_fn=lambda c: ())
    assert rec["decision"] == "ERROR" and rec["error"] == "timeout"

def test_verify_fn_routes_numbers_without_codex(monkeypatch):
    called = []
    monkeypatch.setattr(stage_a, "certify_entailment_json", lambda *a, **k: called.append(1))
    verify = stage_a.make_verify_fn(V, STORE_WITH_SRC, [])
    verify(card_with_claims(["가격은 2달러다"]))
    assert called == []

def test_resume_skips_done(tmp_path, monkeypatch):
    monkeypatch.setenv("UPGRADE_EVAL_ROOT", str(tmp_path))
    write_done_records(tmp_path, [("A2", SRC.source_id, 1)])
    calls = count_run_one_calls(monkeypatch)
    stage_a.run_stage_a(["A2"], verifier="gpt-6-sol", reps=1, seq_rep=0)
    assert calls == []
```

- [ ] **Step 2: 실패를 확인한다** — Run: `uv run pytest tests/test_upgrade_eval_stage_a.py -v` / Expected: FAIL

- [ ] **Step 3: `stage_a.py` 를 구현한다**

- `settings = dataclasses.replace(load_settings(), author_model_id=arm.model_id, backend="local")`
- 호출: `produce_card(fs, _FACT_USER, settings, store, draft_fn=..., revise_fn=..., verify_fn=...)`
- 1차 초안 요약은 draft_fn 래퍼로 잡는다. 예외는 `decision="ERROR"` 로 기록한다.
- `rep == seq_rep` 실행은 병렬 묶음이 끝난 뒤 순서대로 돌린다. `over_360 = duration_ms > 360_000` 이다.

- [ ] **Step 4: 통과를 확인한다** — Run: `uv run pytest tests/test_upgrade_eval_stage_a.py -v` / Expected: PASS

- [ ] **Step 5: 커밋한다**
```bash
git add scripts/upgrade_eval/stage_a.py tests/test_upgrade_eval_stage_a.py
git commit -m "feat(upgrade-eval): Stage A — 운영 produce_card 경로·1차 초안 보존·재개"
```

- [ ] **Step 6: 실행한다(유료, Task 7 Step 9 재승인 뒤)**

Run: `uv run python scripts/upgrade_eval/stage_a.py run --arms A0,A1,A2,A3,A4,A5 --verifier <승자>`
Expected: 레코드 216건, 빠진 키 0. `ERROR`·`over_360` 개수를 `results/stage_a_runs.md` 에 적는다.

---

### Task 9: 판정자 클라이언트·프롬프트·파서

**Files:**
- Create: `scripts/upgrade_eval/judge.py`
- Test: `tests/test_upgrade_eval_judge.py`

**Interfaces:**
- Produces:
  - `JUDGES = {"astra": "us.openai.gpt-6-astra", "sol61": "global.openai.gpt-6.1-sol"}`
  - `THIRD = {"grok": "global.xai.grok-4.7", "kimi": "global.moonshotai.kimi-k3", "glm": "global.zai.glm-5.3", "nova": "us.amazon.nova-premier-v1:0"}`
  - `@dataclass class JudgeCall: obj: dict | None; raw: str; usage: dict; latency_ms: int; error: str | None`
  - `converse_json(model_id: str, system: str, user: str, *, max_tokens: int = 4000, client=None, validate: Callable[[dict], None] | None = None) -> JudgeCall`
    - temperature 는 넘기지 않는다.
    - text 블록만 이어 붙이고, 마지막 JSON object 를 꺼낸다.
    - `validate` 가 `ValueError` 를 던지면 오류 문구를 덧붙여 1회 재시도하고, 그래도 실패하면 `error` 로 남긴다.
  - `KEYFACT_CATEGORIES = ("새 사실", "수치", "변화", "단서", "배경", "발언")`
  - `FIDELITY_LABELS = ("부풀림-범위", "부풀림-단계", "부풀림-한정어", "부풀림-인과", "부풀림-권고", "부풀림-확신도", "지나친 흐림", "귀속 누락", "의견→사실", "인용 불일치")`
  - `@dataclass class KeyFact: id: str; text: str; quote: str; position: float | None; tercile: str | None; category: str; ai_related: bool`
  - 메시지 빌더 — 모두 `(system, user)` 를 반환한다:
    - `keyfacts_messages(source_text)`
    - `review_messages(source_text, facts)`
    - `align_messages(source_text, facts, sentences)`
    - `fidelity_messages(source_text, sentences)`
    - `bypass_messages(sentences, claims)`
    - `pairwise_messages(source_text, first, second)`
  - 파서 — 스키마를 어기면 `ValueError` 를 던지고, `validate` 로도 쓴다:
    - `parse_keyfacts(obj, source_text) -> list[KeyFact]` — 위치는 `source_text.find(quote)` 로 코드가 계산하고, 인용을 못 찾으면 `None` 으로 둔다
    - `parse_align(obj, fact_ids, n_sentences) -> tuple[dict[str, bool], bool]`
    - `parse_fidelity(obj, n_sentences) -> dict[int, list[str]]`
    - `parse_bypass(obj) -> list[str]`
    - `parse_pairwise(obj) -> str`(`first`|`second`|`tie`)
  - `@dataclass class PlantedSummary: item_id: str; source_id: str; summary: str; defect: str | None; sentence_idx: int | None; removed_fact: str | None`
  - `@dataclass class JudgeGate: detection: float; false_flag_rate: float; passed: bool`
  - `DETECTION_MIN = 0.80`, `FALSE_FLAG_MAX = 0.10`
  - `score_gate(flags: dict[str, dict[int, list[str]]], uncovered: dict[str, set[str]], items: list[PlantedSummary], *, adjudicated_ok: set[tuple[str, int]]) -> JudgeGate`
  - `class GateStop(Exception)`
  - `select_judges(stage_b_winner: str, gates: dict[str, JudgeGate], third_ranking: list[str]) -> tuple[str, str, str]` — `(주 판정, 교차 판정, 가림)`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

```python
def test_parse_fidelity_rejects_unknown_label_and_bad_index():
    with pytest.raises(ValueError):
        judge.parse_fidelity({"sentences": [{"idx": 0, "labels": ["과장"]}]}, 3)
    with pytest.raises(ValueError):
        judge.parse_fidelity({"sentences": [{"idx": 5, "labels": []}]}, 3)
    assert judge.parse_fidelity({"sentences": [{"idx": 1, "labels": ["귀속 누락"], "evidence": "e"}]}, 3) == {1: ["귀속 누락"]}

def test_parse_keyfacts_positions():
    src = "앞부분 문장. " + "가" * 100 + " 결론: 출시는 내년이다."
    facts = judge.parse_keyfacts({"facts": [{"id": "K1", "text": "출시는 내년", "quote": "출시는 내년이다",
                                             "category": "단서", "ai_related": False}]}, src)
    assert facts[0].tercile == "뒤" and facts[0].position > 0.66
    with pytest.raises(ValueError):
        judge.parse_keyfacts({"facts": [{"id": "K1", "text": "x", "quote": "x", "category": "기타", "ai_related": False}]}, src)

def test_converse_retries_once_then_errors():
    client = FakeConverse(["no json", "still no json"])
    call = judge.converse_json("m", "s", "u", client=client, validate=lambda o: None)
    assert call.obj is None and call.error and client.calls == 2

def test_score_gate_units_and_adjudication():
    gate = judge.score_gate(FLAGS, UNCOVERED, ITEMS_5_DEFECTS_20_CLEAN_SENTENCES, adjudicated_ok={("orig-3", 1)})
    assert gate.detection == pytest.approx(0.8)              # 결함 5개 중 4개 검출
    assert gate.false_flag_rate == pytest.approx(2 / 20)     # 지적 3개 중 1개는 확인 결과 맞는 지적
    assert gate.passed

def test_select_judges_substitution():
    ok = {k: judge.JudgeGate(.9, .05, True) for k in ("astra", "sol61", "grok", "kimi")}
    assert judge.select_judges("gpt-6-sol", ok, ["grok", "kimi"]) == ("astra", "sol61", "grok")
    assert judge.select_judges("gpt-6-astra", ok, ["grok", "kimi"]) == ("sol61", "grok", "kimi")
    assert judge.select_judges("gpt-6.1-sol", ok, ["grok", "kimi"]) == ("astra", "grok", "kimi")
    bad = {**ok, "astra": judge.JudgeGate(.5, .3, False), "sol61": judge.JudgeGate(.5, .3, False)}
    with pytest.raises(judge.GateStop):
        judge.select_judges("gpt-6-sol", bad, ["grok", "kimi"])
```

- [ ] **Step 2: 실패를 확인한다** — Run: `uv run pytest tests/test_upgrade_eval_judge.py -v` / Expected: FAIL

- [ ] **Step 3: `judge.py` 를 구현한다**

- **시스템 프롬프트(한국어)에 넣을 것**
  - 라벨 정의: 설계 §8.3 과 `summary-evaluation-guide.md` 질문 2 의 네 범주
  - 출력 JSON 스키마
  - "원문만 근거로"
- **요구 사항**
  - 핵심 사실 프롬프트는 사실마다 원문에서 그대로 옮긴 짧은 `quote` 를 요구한다.
  - 정렬 프롬프트는 `first_sentence_is_new_fact` 를 함께 요구한다.
- **`score_gate` 계산**
  - 검출: 라벨 결함은 해당 문장이 지적됐는지, `뒤쪽 사실 삭제` 는 지운 사실이 미포함으로 표시됐는지로 본다.
  - 오탐: 결함 없는 문장의 지적에서 `adjudicated_ok` 를 뺀 수를 결함 없는 문장 수로 나눈다.
- **`select_judges`**
  - 기본은 `(astra, sol61, third[0])` 이다.
  - 승자가 판정자 후보면 그 모델을 빼고 다음 후보로 채운다(§14-3).
  - 기준 미달 판정자는 `[astra, sol61, *third]` 순서로 다음 통과자로 바꾼다.
  - GPT 판정자가 둘 다 미달이면 `GateStop` 을 던진다.

- [ ] **Step 4: 통과를 확인한다** — Run: `uv run pytest tests/test_upgrade_eval_judge.py -v` / Expected: PASS

- [ ] **Step 5: 커밋한다**
```bash
git add scripts/upgrade_eval/judge.py tests/test_upgrade_eval_judge.py
git commit -m "feat(upgrade-eval): 판정자 — Converse 클라이언트·스키마 파서·판정자 검증·대체 규칙"
```

---

### Task 10: 채점 실행

**Files:**
- Create: `scripts/upgrade_eval/judging.py`
- Test: `tests/test_upgrade_eval_judging.py`

**Interfaces:**
- Consumes: `judge.*`, `metrics.split_sentences`, Stage A 레코드, `select_articles.load_manifest`, `common`
- Produces:
  - `median_length_rep(records: list[dict]) -> dict` — 같은 조건·기사의 PUBLISH 반복 중 요약 길이가 중간인 것. 동률이면 낮은 rep.
  - `fidelity_disagreements(a: dict[int, list[str]], b: dict[int, list[str]]) -> list[int]`
  - `align_disagreements(a: dict[str, bool], b: dict[str, bool]) -> list[str]`
  - `scoring_targets(records: list[dict]) -> list[dict]` — PUBLISH 만
  - CLI 하위 명령: `gate`, `keyfacts`, `export-human-1`, `score`, `tiebreak`, `export-human-2`, `pairwise`. 결과는 모두 `EXP_ROOT/judge/*.jsonl` 에 쓰고 재개할 수 있다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

```python
def test_median_length_rep():
    recs = [rec(rep=1, summary="가" * 100), rec(rep=2, summary="가" * 300), rec(rep=3, summary="가" * 200)]
    assert judging.median_length_rep(recs)["rep"] == 3

def test_disagreements():
    assert judging.fidelity_disagreements({0: ["귀속 누락"], 1: []}, {0: [], 1: []}) == [0]
    assert judging.align_disagreements({"K1": True, "K2": False}, {"K1": True, "K2": True}) == ["K2"]

def test_only_published_runs_are_scored():
    recs = [rec(decision="PUBLISH"), rec(decision="QUARANTINE"), rec(decision="ERROR")]
    assert [r["decision"] for r in judging.scoring_targets(recs)] == ["PUBLISH"]
```

- [ ] **Step 2: 실패를 확인한다** — Run: `uv run pytest tests/test_upgrade_eval_judging.py -v` / Expected: FAIL

- [ ] **Step 3: `judging.py` 를 구현한다** — 하위 명령은 설계 §8 의 순서를 따른다.

- [ ] **Step 4: 통과를 확인한다** — Run: `uv run pytest tests/test_upgrade_eval_judging.py -v` / Expected: PASS

- [ ] **Step 5: 커밋한다**
```bash
git add scripts/upgrade_eval/judging.py tests/test_upgrade_eval_judging.py
git commit -m "feat(upgrade-eval): 채점 실행 — 판정자 검증·핵심 사실·채점·가림·사람 확인 내보내기"
```

- [ ] **Step 6: 판정자를 검증한다(유료 ~$5)**

- 설계자가 `EXP_ROOT/judge/planted_summaries.jsonl` 을 쓴다. A0 rep-1 요약 12개와, 결함 6유형 × 6 = 36개 변형으로 이루어진다.
- Run: `judging.py gate --judges astra,sol61,grok,kimi,glm,nova`
- 원본 요약에 대한 지적은 제3계열과 설계자가 원문 근거로 확인한 뒤 `adjudicated_ok` 로 기록한다.
- `select_judges(승자, gates, 제3계열 순위)` 결과를 `results/judges.json` 에 쓴다.
- `GateStop` 이면 **멈추고 사용자에게 묻는다.**

- [ ] **Step 7: 핵심 사실 목록을 만들고 사람이 확인한다(유료 ~$2 + 사람 ~10분)**

Run: `judging.py keyfacts` 다음에 `judging.py export-human-1` → `results/human_check_1.md`(3건)
**사용자 확인을 기다리고**, 고친 내용을 `EXP_ROOT/judge/keyfacts.jsonl` 에 반영한다.

- [ ] **Step 8: 채점하고 사람이 확인한다(유료 ~$80–100 + 사람 ~10분)**

Run: `judging.py score` → `judging.py tiebreak` → `judging.py export-human-2` → `results/human_check_2.md`(갈린 항목 8–12개)
**사용자 확인을 기다리고**, 판정을 반영한다.

- [ ] **Step 9: 참고 비교(유료 ~$5)**

Run: `judging.py pairwise` — A1–A5 각각을 A0 와 비교한다. 중간 길이 rep 끼리, 순서를 바꿔 2회, 판정자 2개.

---

### Task 11: 비용 실측

**Files:**
- Modify: `scripts/upgrade_eval/costs.py`
- Test: `tests/test_upgrade_eval_costs.py`

**Interfaces:**
- Consumes: `costs.Price`/`FALLBACK_PRICES`/`codex_cost`(Task 7), Stage A 레코드
- Produces:
  - `fetch_bedrock_prices(verifier_keys: list[str], *, client=None) -> dict[str, Price]` — 키는 `VERIFIERS` 의 키(`gpt-6-sol` 등). 요약 AI 비용은 envelope 실비용을 쓰므로 Claude 가격은 리포트 참고용으로만 함께 받는다.
    - `pricing.get_products(ServiceCode="AmazonBedrock")` 로 찾은 것은 `verified=True, source="AWS Price List API <날짜>"`
    - 못 찾은 것은 `FALLBACK_PRICES` 를 쓴다(`verified=False`)
  - `cost_explorer_bedrock(start: str, end: str, *, client=None) -> list[dict]` — `get_cost_and_usage`, SERVICE=`Amazon Bedrock`, `GroupBy=USAGE_TYPE`
  - `split_by_model(rows: list[dict]) -> dict[str, float]` — 모르는 usage type 은 `"기타"`
  - `card_cost(record: dict, prices: dict[str, Price], verifier: str) -> tuple[float, bool]` — author envelope 실비용 합 + codex 비용. bool 은 모든 가격이 확인됐는지다.
  - `project(cost_per_card: float, cards_per_day: float = 19.0) -> dict[str, float]` — `{"day": ..., "month": ...}`(30일)

- [ ] **Step 1: 실패하는 테스트를 쓴다**

```python
def test_card_cost_and_unverified_flag():
    rec = {"author_runs": [{"cost_usd": 0.12}, {"cost_usd": 0.03}],
           "codex_calls": [{"usage": {"input_tokens": 1_000_000, "cached_input_tokens": 0, "output_tokens": 0}}]}
    cost, verified = costs.card_cost(rec, {"gpt-6-sol": costs.Price(2.0, 10.0, None, False, "2차")}, "gpt-6-sol")
    assert cost == pytest.approx(0.15 + 2.0) and verified is False

def test_project():
    assert costs.project(0.5) == {"day": pytest.approx(9.5), "month": pytest.approx(285.0)}

def test_split_by_model():
    rows = [{"usage_type": "USE1-claude-sonnet-5-input-tokens", "amount": 3.0},
            {"usage_type": "USE1-gpt-5.5-output-tokens", "amount": 2.0}, {"usage_type": "USE1-x", "amount": 1.0}]
    assert costs.split_by_model(rows) == {"claude-sonnet-5": 3.0, "gpt-5.5": 2.0, "기타": 1.0}
```

- [ ] **Step 2: 실패를 확인한다** — Run: `uv run pytest tests/test_upgrade_eval_costs.py -v` / Expected: FAIL

- [ ] **Step 3: 구현한다.** usage type 의 실제 형식은 Step 5 에서 받은 응답을 보고 `split_by_model` 매칭 표를 맞춘다.

- [ ] **Step 4: 통과를 확인한다** — Run: `uv run pytest tests/test_upgrade_eval_costs.py -v` / Expected: PASS

- [ ] **Step 5: 실측한다(~$0.1)**

Run: `uv run python scripts/upgrade_eval/costs.py --since <30일 전> --until <오늘>` → `results/costs.json`
- `AccessDenied` 이면 **멈추고 권한을 요청한다**(`ce:GetCostAndUsage`, `pricing:GetProducts`).
- 대안(Claude 는 CloudWatch, GPT 는 F5 이후)은 결과에 적는다.

- [ ] **Step 6: 커밋한다**
```bash
git add scripts/upgrade_eval/costs.py tests/test_upgrade_eval_costs.py
git commit -m "feat(upgrade-eval): 비용 — 공식 가격·Cost Explorer·카드당 비용·환산"
```

---

### Task 12: 집계와 결정

**Files:**
- Create: `scripts/upgrade_eval/stats.py`, `scripts/upgrade_eval/aggregate.py`
- Test: `tests/test_upgrade_eval_stats.py`, `tests/test_upgrade_eval_aggregate.py`

**Interfaces:**
- Consumes: Stage A 레코드, 판정 결과, `metrics.*`, `costs.card_cost`
- Produces:
  - `paired_bootstrap(diffs: dict[str, float], *, n: int = 10_000, seed: int = SEED) -> tuple[float, float, float]` — `(평균, 하한, 상한)`
  - `rep_sd(values: dict[str, list[float]]) -> float` — 기사 안 반복 표준편차의 평균
  - `no_difference(ci: tuple[float, float, float], rep_sd: float) -> bool` — 구간이 0 을 포함하거나 `abs(평균) < rep_sd`
  - `scorecard(arm: str, runs: list[dict], judged: list[dict], prices: dict, verifier: str) -> dict`
    - **발행:** `failure_rate`(ERROR + QUARANTINE + 순차분 `over_360`), `failure_rate_f2_adjusted`
    - **안전:** `bypass_rate`, `quote_mismatch_rate`
    - **충실도:** `inflation_rate`, `oversoftening_rate`, `attribution_rate`, `opinion_rate`
    - **커버리지:** `coverage`, `coverage_by_tercile`, `coverage_by_category`, `coverage_per_sentence`, `first_sentence_new_rate`, `ai_coverage`
    - **형식:** `sentences_mean`, `long_sentence_ratio`, `hedge_rate`, `depth_mean`, `translit_rate`, `claims_mean`, `first_pass_rate`, `why_new_numbers_rate`
    - **속도·비용:** `latency_p50`, `latency_p95`(순차분), `cost_per_card`, `cost_verified`
  - `decide(cards: dict[str, dict], per_article: dict[str, dict[str, dict[str, float]]], *, baseline: str = "A0") -> dict` — 반환값 `{"eliminated": {arm: [사유]}, "ranking": [arm], "comparisons": {arm: {지표: [평균, 하한, 상한, 차이없음]}}}`
    - **탈락**
      - 안전 지표나 충실도(부풀림+지나친 흐림)가 A0 보다 나쁘고 신뢰구간이 0 을 포함하지 않으면 탈락이다.
      - `failure_rate_f2_adjusted` 가 A0 + 0.05 이상이면 탈락이다.
    - **순위:** 충실도 → 커버리지 → 비용 → p95 순으로 본다. 각 단계에서 '차이 없음'이면 동률로 다음 단계로 넘어간다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

```python
def test_bootstrap_deterministic():
    d = {"a": 1.0, "b": 1.0, "c": 1.0}
    assert stats.paired_bootstrap(d) == (1.0, 1.0, 1.0)
    d2 = {"a": 0.1, "b": -0.2, "c": 0.4}
    assert stats.paired_bootstrap(d2, seed=7) == stats.paired_bootstrap(d2, seed=7)

def test_no_difference():
    assert stats.no_difference((0.1, -0.05, 0.25), 0.0)
    assert stats.no_difference((0.1, 0.05, 0.15), 0.2)
    assert not stats.no_difference((0.1, 0.05, 0.15), 0.01)

def test_decide_eliminates_failure_rate_and_worse_fidelity():
    out = aggregate.decide(CARDS_A0_A3_A4, PER_ARTICLE)
    assert "발행 실패율" in " ".join(out["eliminated"]["A3"])      # A3: 0.12 vs A0 0.05
    assert "충실도" in " ".join(out["eliminated"]["A4"])          # A4: 부풀림↑, 구간 > 0

def test_decide_ranks_with_ties_falling_through():
    out = aggregate.decide(CARDS_TIED_FIDELITY, PER_ARTICLE_TIED)
    assert out["ranking"][0] == "A2"   # 충실도 동률(차이 없음) → 커버리지 우위
```

- [ ] **Step 2: 실패를 확인한다** — Run: `uv run pytest tests/test_upgrade_eval_stats.py tests/test_upgrade_eval_aggregate.py -v` / Expected: FAIL

- [ ] **Step 3: 구현한다.** 부트스트랩은 기사 단위 재표집(`random.Random(seed)`)이고, 백분위는 2.5·97.5 다.

- [ ] **Step 4: 통과를 확인한다** — Run: 같은 명령 / Expected: PASS

- [ ] **Step 5: 집계를 실행한다(무료)**

Run: `uv run python scripts/upgrade_eval/aggregate.py` → `results/scorecards.json`, `results/decision.json`

- [ ] **Step 6: 커밋한다**
```bash
git add scripts/upgrade_eval/stats.py scripts/upgrade_eval/aggregate.py tests/test_upgrade_eval_stats.py tests/test_upgrade_eval_aggregate.py
git commit -m "feat(upgrade-eval): 집계·결정 — 짝 부트스트랩·차이 없음·탈락·순위"
```

---

### Task 13: 리포트와 마무리

**Files:**
- Create: `scripts/upgrade_eval/report.py`
- Test: `tests/test_upgrade_eval_report.py`
- Output: `/home/ubuntu/Agent-Claude-Code-With-Codex/docs/work_note/Oct-2026/261016-upgrade-claude-codex/upgrade-comparison-report.md` — 메인 트리의 미커밋 work_note

**Interfaces:**
- Consumes: `results/decision.json`, `scorecards.json`, `stage_b_scores.json`, `costs.json`, `setup.md`
- Produces: `render_report(decision: dict, cards: dict, stage_b: dict, costs: dict, meta: dict) -> str`
  - 절: 결론, 요약 품질 성적표, 검증 AI, 비용 전후, 처리 시간, 한계, 사례 모음, 다음 단계, 부록
  - 확인되지 않은 가격에는 '미확인'을, 차이가 없는 항목에는 '차이 없음'을 적는다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

```python
def test_report_sections_and_marks():
    md = report.render_report(DECISION, CARDS, STAGE_B, COSTS_UNVERIFIED, META)
    for h in ("## 결론", "## 요약 품질", "## 검증 AI", "## 비용", "## 처리 시간", "## 한계", "## 사례 모음", "## 다음 단계"):
        assert h in md
    assert "미확인" in md and "차이 없음" in md
    assert "A3" in md and "발행 실패율" in md          # 탈락 사유가 드러난다
```

- [ ] **Step 2: 실패를 확인한다** — Run: `uv run pytest tests/test_upgrade_eval_report.py -v` / Expected: FAIL

- [ ] **Step 3: 구현한다.** 표는 코드가 만들고, '사례 모음'·'한계'·'결론' 의 문장 칸은 비워 둔다(설계자가 채움).

- [ ] **Step 4: 통과를 확인한다** — Run: `uv run pytest tests/test_upgrade_eval_report.py -v` / Expected: PASS

- [ ] **Step 5: 리포트를 생성하고 문장을 채운다**

- 설계자가 결론, 사례 모음(점수 없이), 한계를 쓴다.
- 함께 적을 것: 표본 12건의 한계, 판정자 구성, 가격 확인 상태.

- [ ] **Step 6: 전체 점검과 마무리**

- Run: `uv run pytest -q && uv run ruff check scripts/upgrade_eval tests/test_upgrade_eval_*.py` / Expected: 모두 통과
- 새 리뷰어가 브랜치 전체를 점검한다.
- 메인 트리의 문서를 갱신한다:
  - `work-list.md`: U2–U7 완료 표시
  - 설계 상태: 구현 완료·배포 보류
  - `docs/README.md` 색인
```bash
git add scripts/upgrade_eval/report.py tests/test_upgrade_eval_report.py docs/superpowers/specs/2026-10-17-claude-codex-upgrade-design.md docs/README.md
git commit -m "feat(upgrade-eval): 리포트 생성 — 결론·성적표·비용 전후·미확인 표기"
```
- 사용자에게 리포트 경로와 결론을 보고하고, U8 조합 선택과 §14-4 결정을 요청한다.

---

## 배포 (보류 — 이 계획에서 실행하지 않음)

F3(effort 명시)·F7(해석층 설정 분리)·F5(검증 비용 실측 기록)·U8(단계 배포)은 §14-4(다른 작업과의 배포 순서)가 정해진 뒤 별도 계획으로 쓴다. 이 계획의 결과물(리포트·`codex_runner.parse_codex_jsonl`)이 그 계획의 입력이다.
