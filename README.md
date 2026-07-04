# Agent-Claude-Code-With-Codex

**검증 후 발행(verify-before-publish) AI 뉴스 브리핑 에이전트** — **듀얼 하니스**(Claude Code 작성자 + Codex 인증자)를 Amazon Bedrock 위에서 함께 써서, *발행 전에 독립 검증*된 개인화 모닝 브리핑을 매일 이메일로 보냅니다.

> 진실의 원천은 **`design/`**(설계 문서)와 **`CLAUDE.md`**(개발 가이드)입니다. 이 README 는 빠른 개요·실행법.

## 무엇인가 (The one concept)

핵심은 **직무 분리(separation of duties) + 검증 후 발행 게이트**:

- **Claude Code = 작성자(author).** 원문 기사를 사용자의 **관점(lens)** 으로 요약하고, 산출물·실행·지속 상태를 소유.
- **Codex = 독립 인증자(certifier).** 요약을 **발행 전에 차단(BLOCK)** 할 권한. 결정론 코드로 재도출(산술·함의/NLI·스키마).
- **상관관계 끊기(decorrelation).** 인증자는 **최소 컨텍스트**(원문 구절 + 주장 + 스키마)만 받고 *작성자의 추론은 절대 못 봄* → 확인 도장이 아니라 진짜 **독립 재도출**. **Codex 를 빼면 중심 신뢰 속성이 붕괴**합니다.
- 결정론 **gate** 가 오케스트레이션을 소유(Maker-Checker 루프; 모델이 불일치하면 발행 안 하고 QUARANTINE).

원문 기사를 *쓰지* 않고 **요약 + 검증**합니다.

## 제품

가벼운 **개인화 데일리 모닝 AI-뉴스 브리핑**(딥리서치 아님). 사용자가 매체(출처)와 관점을 고르면, 매일 정해진 시각에 검증된 카드들을 이메일로 받습니다.

- **관점(lens):** `general / engineer / business / researcher` — 요약의 강조·어휘를 바꿈(사실은 못 바꿈; certifier 미열람).
- **검증 명세서(Verified Dispatch) 메일:** 헤더 인장 `✓ AI 에이전트 원문 대조` → 카드마다 `요약 · {관점}` → `나에게 왜 중요한가(해석)` → 한 줄 검증줄 `✓ 다른 AI 에이전트가 사실 N건 검증 [· 미확인 M · 제외 K]`. 출처 **분야 밴드** · 다크모드 · `depth`(title-only/summary/full). 설계: `design/ux/email-ux-mockup.md`.
- **관련성 필터:** 종합지 피드(예 AI Times)는 AI 무관 기사를 요약·검증 *전* 에 컷(`Source.require_ai`).

## 빌드 & 실행 (UV)

```bash
uv sync                                        # 의존성
uv run ruff check src tests                    # 린트
uv run pytest                                  # 테스트(현재 176 passed + 3 skipped)

uv run python -m briefing.local.run            # AWS-free 베이스라인(무지출·결정론)
DEBUG=1 uv run python -m briefing.local.run    # + 파이프라인 디버그 추적(stderr)
DEBUG=1 uv run python scripts/e2e_smoke.py     # 실 e2e: RSS→claude author→codex certifier→render(과금)
```

`DEBUG=1` 이 `_debug` 추적을 켭니다 — 출력은 **stderr**(stdout 의 이메일/JSON 비오염). envelope→certifier 핸드오프, gate PUBLISH/QUARANTINE 결정, author/certifier rc 등이 보입니다.

## 레포 구조

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

## 하니스 라우팅 (어느 하니스가 무엇을)

| 단계 | 도구 | 이유 |
|---|---|---|
| 계획·생성(요약) | **Claude Code** (`claude -p`) | 장문 종합·브랜드/톤/관할 |
| 검증 | **Codex** (`codex exec`) | envelope 4필드만 — 결정론 독립 재도출(decorrelation) |
| 전달 | **Claude Code** | 사용자 대면 실행; gate 가 비가역 결정 소유 |

**런타임 격리(비협상):** headless author/certifier 는 **깨끗한 작업 디렉토리**에서 실행 — repo 의 `CLAUDE.md`/`AGENTS.md` 자동 로드 금지(certifier 오염 = decorrelation 붕괴).

## 배포 (AWS us-east-1)

- **② Runtime:** AgentCore(`briefing_agent`) — 컨테이너에 듀얼 하니스(claude+codex) 번들. `uv run python -m briefing.runtime.deploy_runtime`. render/curation/lens 변경은 컨테이너에 baked → **재배포해야 라이브**.
- **③ DB:** DynamoDB(card-cache · ledger · source-store · users).
- **⑤ Scheduler:** EventBridge → Lambda(fire-and-return) → runtime async(≤8h) → SES, **매일 07:00 KST**.
- **④ Web UI:** S3 + CloudFront(SPA) + HTTP API(Lambda/FastAPI) — 체험(trial) · 구독(Cognito PKCE).
- **① Gateway:** retrieval 3도구를 AgentCore Gateway(MCP)로 승격 — **기본 off**(`GATEWAY_ENABLED=1` 일 때만).
- ⚠️ 외부 이메일 배달엔 **소유 도메인 + SES DKIM** 필요(현재는 검증 주소로 데모; 외부 발신은 DMARC 차단).
- `.env` = 통합 버스(루트). ★ 재배포 전 **`SES_SENDER` 등 키 존재 확인** — 비면 발송이 조용히 실패.

## 더 보기

- **`CLAUDE.md`** — 개발 가이드(아키텍처·하니스 규칙·범위 제약·언어 규칙).
- **`design/`** — PRD · 외부 리서치 · 아키텍처 분석 · `design/ux/email-ux-mockup.md`(메일 UX 스펙).

## 언어 규칙

문서·docstring·주석은 **한국어 우선(한국어 friendly)**, 코드(식별자·API·CLI 플래그·로그)는 이식성을 위해 **영어**. 정확한 영어 기술 용어는 이중 언어로(예: 검증 후 발행(verify-before-publish)).
