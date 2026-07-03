# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

이 저장소는 **Claude Code 와 Codex 를 함께 쓰는 듀얼 하니스(dual-harness)** 위에서 실용적 AI 애플리케이션을 만드는 것을 목표로 합니다.

## 저장소 현황 (Repository status)

- **설계 단계에서 구현 스캐폴드로 진입했습니다.** 저장소 = `README.md` · `CLAUDE.md` · `design/`(설계 문서) · **`src/briefing/`(구현 스캐폴드)** · `tests/`. 설계 문서는 세 하위 폴더: **`design/prd/`**(제품 요구사항)·**`design/research/`**(외부 사실·랜드스케이프 리서치)·**`design/architecture/`**(아키텍처·전략 분석).
- **빌드/실행 (UV):** `uv sync` · `uv run ruff check src tests`(린트) · `uv run pytest`(테스트 **92개** — 불변식·결정론, DI fake 로 전 파이프라인) · `uv run python -m briefing.local.run`(AWS-free baseline) · **실 e2e:** `[DEBUG=1] uv run python scripts/e2e_smoke.py`(실 RSS→`claude -p` author→`codex` certifier→render — 라이브 검증) · `scripts/e2e_gateway.py`(① Gateway 3도구 실 호출 — byte-identical). **구조:** `src/briefing/` = `core/`(진실) — **`stores/`**(source_store·cache·ledger·dynamo·backends) · **`retrieval/`**(sources·curation·catalog·gateway_client) · **`authoring/`**(author)·**`verification/`**(certifier) · core(config·gate·pipeline·render·lenses·_debug·prompts) / `runtime/`(AgentCore 얇은 어댑터 + supervisor 옵션) / `gateway/`(① Gateway: gateway_handler·deploy_gateway) / `scheduler/`(⑤ due→dispatch→SES deliver) / `local/`(AWS-free baseline). **하니스:** author=`claude -p`·certifier=`codex exec` — 둘 다 clean dir·subprocess·cross-family. **수동 author:** `scripts/claude-author.sh -p "..."`. **잔여 미구현:** `fetch_fragile`(Browser Tool v1.5)·배포 3종(deploy/invoke/teardown)·SES 발송 — 그 외 실동작·e2e 검증됨.
- **① Gateway 승격 (deployed · off-by-default):** §79 retrieval 3도구(`fetch_article`·`get_source`·`discover_feed`)를 **AgentCore Gateway**(MCP·Cognito CUSTOM_JWT)에 승격 — **us-east-1 실 배포 + 3도구 e2e byte-identical 검증 완료**. 재현 번들 = `infra/gateway/cognito.yaml`(CFN: Cognito+IAM) · `gateway/deploy_gateway.py`(멱등 boto3: CFN→S3 zip Lambda→OAuth2 provider→Gateway+target) · `scripts/e2e_gateway.py` · 상세 `infra/gateway/README.md`. **Lambda=zip**(lxml=native manylinux wheel → docker 불필요, aiops 충실). **기본 off** — `GATEWAY_ENABLED=1` 일 때만 fabric 이 Gateway 경유(아니면 직접; 현 파이프라인·92 테스트 무변경). **guardrail(비협상):** dispatch 화이트리스트 = retrieval 3도구뿐 → gate/certify/author/freeze **미노출**(decorrelation 유지). 토큰: Runtime=AgentCore Identity(비밀=볼트)·로컬=client_credentials. 가치(정직): v1 은 load-bearing 아님 — indirection+provenance+역량/forward-compat; principal-scope 진짜 값은 author 를 MCP-pull 로 바꾸는 v-next.
- **진실의 원천(source of truth)은 `design/` 문서입니다.** 큰 그림은 여러 문서를 함께 읽어야 드러나므로, 아래 "설계 문서 지도"를 먼저 참고하세요(지도는 출발점이 되는 핵심 문서를 추립니다 — 나머지는 위 세 하위 폴더에 있습니다).

## 핵심 아키텍처 개념 (The one concept that unifies everything)

세 설계 문서를 관통하는 단 하나의 핵심은 **직무 분리(separation of duties) + 검증 후 실행 게이트(verify-before-fire / verify-before-publish gate)** 입니다. 이것이 "왜 하니스가 두 개여야 하는가"에 대한 답이자 이 프로젝트의 존재 이유입니다.

- **Claude Code = 작성자/생성자/오케스트레이터 (author / generator / orchestrator).** 모호한 의도를 분해하고, 산출물(원장 레코드, 통지문, 브리핑 등)을 작성하며, 엔드투엔드 실행과 지속 상태를 소유합니다.
- **Codex = 독립 검증자/인증자 (independent certifier).** 산출물을 **발행/실행하기 전에 차단(BLOCK)** 할 권한을 가집니다. 결정론적 코드로 재도출합니다 — 날짜/통지 기간 산술, 함의(entailment/NLI) 검사, 스키마·diff·완전성 검증.
- **상관관계 끊기 (decorrelation) 가 신뢰의 원천입니다.** Codex 에는 **최소 컨텍스트(minimal context)** — 원본 구절 + 주장 문자열 + 스키마 — 만 주고, **Claude 의 추론(narration)은 절대 전달하지 않습니다.** 작성자의 추론을 숨겨야 "확인 도장(confirmation pass)"이 아니라 진짜 **독립 재도출(independent re-derivation)** 이 강제되어, 두 모델의 오류가 상관되지 않습니다. **Codex 를 제거하면 중심 신뢰 속성이 붕괴합니다** — 단지 마감 품질이 떨어지는 게 아닙니다.
- **지속 가능한 고유 상태 (durable proprietary state).** 제품은 일회성 리포트가 아니라 시간에 걸쳐 재-diff 되는 **원장(ledger, JSON/SQLite)** 을 소유합니다.

## 하니스 라우팅 원칙 (Which harness does what)

작업을 어느 하니스에 맡길지 결정할 때의 기본 토폴로지는 **Specialized(역할 분리)** 입니다:

| 단계 | 도구 | 이유 |
|---|---|---|
| 계획/분해 (Plan) | **Claude Code** | 개방형 계획 수립, 모호한 의도 분해, skill/hook 오케스트레이션 |
| 생성 (Generate) | **Claude Code** | 장문 컨텍스트 종합, 브랜드/톤/관할권에 맞는 작성 |
| 검증 (Verify) | **Codex** | 실행 가능한 코드로 독립·반박적 재도출(산술/함의/diff), 결정론적 PASS/FAIL 게이트 |
| 전달 (Deliver) | **Claude Code** | 사용자 대면 실행, Codex 가 만든 렌더러/검증기를 하위 호출 |

**비가역 조치(irreversible action)의 기본값은 "초안 후 승인 대기(draft → human approval queue)"** 입니다. 자율 실행은 옵트인이며, 모델이 불일치(disagree)하면 아무것도 실행/발행하지 않고 사람 검토용으로 격리(QUARANTINE)합니다.

**런타임 하니스 격리 (runtime isolation) — 비협상.** headless author(`claude -p`)·certifier(`codex exec`)는 **반드시 깨끗한 작업 디렉토리에서 실행**한다 — 저장소의 `CLAUDE.md`/`AGENTS.md` 가 *자동 로드되면 안 된다*. author 는 `build_system_prompt` 로만 통제되어야 하고(repo 아키텍처 컨텍스트로 오염 금지), **certifier 는 envelope 4필드 외 어떤 프로젝트 컨텍스트도 보면 안 된다 — `AGENTS.md`/`CLAUDE.md` 자동 로드는 decorrelation 을 *조용히* 깬다.** AgentCore 컨테이너는 자연히 격리되고, 로컬 PoC/테스트는 `scratchpad` 같은 clean dir 에서 돌린다(스모크 테스트가 그 예). → 그래서 repo 에 `AGENTS.md` 를 두면 certifier 를 repo dir 에서 실행할 때 *footgun* 이다(반드시 clean dir).

## 무엇을 만들지의 제약 (Inclusion test — 범위를 지키는 가드레일)

어떤 기능/제품 아이디어를 핵심으로 삼을지 판단할 때, 후보는 아래를 **모두** 통과해야 합니다:

1. **두 하니스가 핵심을 담당해야 함** — Codex 를 빼면(또는 한 모델 자가 점검으로 축소하면) 중심 신뢰 속성이 본질적으로 깨질 것.
2. **지속 가능한 외부 도메인** — 진화하는 고유 상태(원장 등)를 소유, 일회성 리포트가 아닐 것.
3. **기본 프리미티브를 넘어설 것** — Skill + WebSearch/WebFetch + `/schedule` + PushNotification 을 쌓아 재현되지 않을 것.

**핵심으로 삼으면 자동 탈락하는 유형:** 뉴스/콘텐츠 브리핑, 범용 딥리서치, 코드 생성·리뷰·PR 어시스턴트, 크론/리마인더 실행기, 스크레이퍼/브라우저 봇, Gmail/Calendar/Drive 어시스턴트, 알림 디스패처, **얇은 LLM 래퍼**(요약/분류/추출/재작성). 이 제약은 협상 불가이며 모든 제품 결정을 지배합니다.

## 설계 문서 지도 (Design docs map) + 현재 결정 상태

| 문서 | 내용 |
|---|---|
| `design/prd/prd.md` | 프로젝트 목표·제약·참조 리소스의 원본 PRD(한국어). 듀얼 하니스로 무엇을 만들지, 어떤 조건을 제외하는지의 출발점. |
| `design/research/research-what-to-build.md` | 31개 에이전트 리서치 워크플로우의 종합 결과. 7개 후보를 3개 심사 관점으로 평가 → **Obligation Ledger(의무 원장)** 를 1위로 추천. 라우팅 전략·MVP 범위·위험 포함. |
| `design/architecture/news-agent-differentiation.md` | **뉴스 브리핑 에이전트** 각도를 별도로 심화한 차별화 보고서. Consequence Ledger / Diff-Since-Last / Prediction Ledger 등 6개 차별화 요소와 verify-before-publish 게이트 설계. |

**현재 결정 상태(읽어야 할 긴장점):** 리서치 문서는 뉴스 에이전트를 제외 집합으로 보고 **Obligation Ledger** 를 추천하지만, 별도 차별화 문서는 뉴스 에이전트가 검증 원장(verify-before-publish ledger)으로 재구성되면 살아날 수 있는 각도를 탐색합니다. **최종 제품은 아직 확정되지 않았습니다** — 작업 전에 사용자에게 현재 방향을 확인하세요.

## 언어 규칙 (Language / 언어)

- **모든 문서·docstring·코드 주석은 한국어 우선(한국어 friendly)** 으로 작성합니다 — 한국어 독자가 쉽게 따라올 수 있도록.
  - **적용 대상:** Markdown 문서(`*.md`), 설계 스펙, README, 모듈/함수/클래스 docstring, 인라인 주석.
  - **코드 자체는 영어 유지:** 식별자, 함수/변수/클래스명, API 명, CLI 플래그, 파일 경로, 로그 메시지는 이식성을 위해 영어로.
  - 정확한 영어 기술 용어가 도움이 될 때는 **이중 언어로** — 예: `검증 후 실행 게이트(verify-before-fire gate)`, `의무 원장(obligation ledger)` — 두 언어에서 의미가 분명해지도록.
