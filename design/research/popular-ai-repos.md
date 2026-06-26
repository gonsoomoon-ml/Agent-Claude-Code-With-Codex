# 최근 인기 AI Agent / AI Application GitHub 레포 리포트 (2025-2026)

> 본 리포트는 deduped 랭킹과 검증(verification) 결과를 바탕으로 작성되었습니다. **스타(⭐) 수는 모두 근사치**이며, 검증된 수치를 우선했습니다. verification에서 `not-found`로 표시된 항목은 없었으나, `sst/opencode`는 현재 `anomalyco/opencode`로 이전/리네임(redirect)되었다는 점을 표에 명시했습니다.

---

## 1. 요약 (Executive Summary)

2025-2026년 오픈소스 AI 에이전트 생태계는 "라이브러리"에서 **배포 가능한 end-user 제품 + 검증 가능한 오케스트레이션(verifiable orchestration)** 으로 빠르게 무게중심을 옮겼습니다. n8n(~194k), opencode(~178k), Langflow(~150k), Dify(~146k), Open WebUI(~143k) 같은 **워크플로/앱 플랫폼**이 최상위 스타 구간을 차지했고, 동시에 `mini-swe-agent`(~100줄로 SWE-bench Verified 74%+)와 `dzhng/deep-research` 같은 **미니멀 하네스(minimal harness)** 가 "작고 투명한 스캐폴드가 거대한 시스템과 견줄 수 있다"는 명제로 바이럴이 되었습니다.

### 2025-2026 핵심 트렌드

1. **듀얼/멀티 하네스 레이어링이 독립 카테고리로 부상** — `wshobson/agents`, `bradAGI/awesome-cli-coding-agents`는 Claude Code + Codex (+ Cursor/Gemini/Copilot)를 한꺼번에 다루는 것을 목적으로 존재. 이 프로젝트가 정조준하는 고도(altitude)와 정확히 일치.
2. **MCP가 cross-vendor 커넥터 표준으로 확립** — Anthropic·OpenAI·Google·Microsoft·GitHub·Brave가 모두 first-party MCP 서버를 출시. 두 awesome-mcp-servers 카탈로그가 88-90k 스타를 돌파하며, 에이전트는 이제 bespoke 통합 대신 **MCP 도구 계층(tool layer)** 을 전제로 함.
3. **벤더 공식 에이전트 SDK 본격 등장** — OpenAI(`openai-agents-python`, Swarm 후속)와 Google(`adk-python`)이 first-party 키트를 출시. 프레임워크 논의가 third-party 라이브러리에서 provider-backed primitives(agents, handoffs, guardrails, evals)로 이동.
4. **"미니멀 하네스"가 경쟁 논제로** — `mini-swe-agent`, `dzhng/deep-research`가 바이럴. 하네스가 네이티브로 하는 일을 중복하지 말고 **앱을 lean하게 유지**하라는 강한 신호.
5. **상태 기반·감사 가능한(stateful, auditable) 오케스트레이션이 프로덕션 기본값** — LangGraph의 checkpointed graphs와 OpenHands의 event-sourced Software Agent SDK는 rollback·audit trail·human-approval 게이트 수요를 반영. 이는 프로젝트의 **검증 후 실행 게이트(verify-before-fire gate)** 및 **의무 원장(obligation ledger)** 과 직접 대응.
6. **딥리서치/뉴스-브리핑이 공통 청사진(blueprint)을 가진 하위 장르로 성숙** — planner -> 멀티소스 search+scrape -> 적대적 비평(adversarial critique) -> 출처 인용 합성(cited synthesis), 점차 supervisor-delegates-to-subagents 패턴으로 실행(gpt-researcher, STORM, open_deep_research, gpt-newspaper).
7. **Privacy-first / local-first 배포가 지속적 반대 흐름** — Open WebUI, anything-llm, local-deep-research 류는 telemetry 없이 오프라인으로 전체 에이전트 루프를 돌리려는 수요를 보여줌.
8. **Type-safe + code-as-action 실행 모델 수렴** — `pydantic-ai`/`mastra`는 validated·typed I/O를, `smolagents`/Codex류 하네스는 code-as-action을 추진. 둘 다 에이전트 출력을 **검증 가능하고 발사(fire)하기 안전하게** 만드는 게 목표.
9. **통합·제도화(consolidation, institutionalization) 진행** — Continue가 Cursor에 인수(OSS repo read-only)되고, Goose가 Linux Foundation 산하 Agentic AI Foundation으로 거버넌스 이전. 실험에서 거버넌스/엔터프라이즈 인프라로 성숙 중.
10. **브라우저/웹 액션이 독립 역량으로 폭발** — `browser-use`가 100k 스타 돌파, Microsoft `playwright-mcp`가 accessibility-tree 기반 브라우저 제어를 표준화. 리서치·뉴스 에이전트에게 실제 웹 상호작용이 near-default 도구 표면(tool surface)으로 정착.

---

## 2. 카테고리별 인기 레포

### 2-1. Agent 프레임워크 / 오케스트레이션 라이브러리

| 레포 (owner/repo) | ⭐ 대략 스타 | 한 줄 설명 | 모멘텀 / 인기 이유 | 언어 |
|---|---|---|---|---|
| microsoft/autogen | ~59.2k | 자율 또는 human-in-the-loop 멀티 에이전트 앱 프레임워크 | 0.4+ 재작성으로 event-driven async actor 아키텍처 + AgentChat/AutoGen Studio 도입 | Python |
| crewAIInc/crewAI | ~54.3k | 역할 기반(role-playing) 자율 에이전트 협업 오케스트레이션 | Fortune 500 60%+ 채택, LangChain 독립 lean 런타임; Crews+Flows(자율+결정론적 제어) | Python |
| run-llama/llama_index | ~50.4k | 사적 데이터 위 agentic·RAG·문서 이해 앱용 데이터 프레임워크 | 순수 RAG에서 agentic workflows/document agents(LlamaParse/LlamaCloud)로 전환 | Python |
| agno-agi/agno | ~40.8k | 풀스택 멀티 에이전트 런타임 + 컨트롤 플레인(AgentOS) | 가장 빠르게 상승한 프레임워크 중 하나(Phidata 후신); 저지연/저메모리 강조 | Python |
| langchain-ai/langgraph | ~36k | stateful·graph 기반 에이전트용 저수준 오케스트레이션 | graph 기반 stateful 에이전트의 프로덕션 기본값; 2026 초 CrewAI 모멘텀 추월 보도 | Python |
| huggingface/smolagents | ~28k | "코드로 사고하는" 에이전트용 barebones 라이브러리(code-as-action) | JSON tool-calling 대안으로 강한 traction | Python |
| openai/openai-agents-python | ~27k | provider-agnostic 멀티 에이전트 워크플로(Swarm GA 후속) | minimal primitives(agents, handoffs, guardrails, sessions) + 100+ LLM | Python |
| mastra-ai/mastra | ~25k | 모던 스택 기반 TypeScript 에이전트/앱 프레임워크 | 2025-2026 대표 TS/JS 에이전트 프레임워크(Gatsby 팀); workflows·memory·RAG·evals 네이티브 | TypeScript |
| google/adk-python | ~20k | 코드 우선 Python Agent Development Kit(빌드·평가·배포) | Google first-party SDK; Gemini/Vertex 연동 + 내장 evaluation | Python |
| pydantic/pydantic-ai | ~18k | type-safe·프로덕션급 에이전트 프레임워크(FastAPI-style DX) | 2025 말 1.x 안정 API; typed·validated I/O 기본 선택지 | Python |

### 2-2. 코딩 에이전트 · 하네스 (Autonomous coding agents & dev harnesses)

| 레포 (owner/repo) | ⭐ 대략 스타 | 한 줄 설명 | 모멘텀 / 인기 이유 | 언어 |
|---|---|---|---|---|
| sst/opencode ⚠️ | ~178k | 터미널 네이티브 오픈소스 코딩 에이전트(75+ provider, LSP, privacy-first) | 2025-2026 최고 급상승. ⚠️ 현재 `anomalyco/opencode`로 이전/리네임(redirect) | TypeScript/Go |
| OpenHands/OpenHands | ~78.2k | 코드베이스 전반을 plan/write/apply하는 model-agnostic 자율 SWE 에이전트(구 OpenDevin) | 2025.11 V1 재설계(event-sourced Software Agent SDK), $18.8M 펀딩 | Python |
| cline/cline | ~63.9k | SDK/IDE 확장/CLI로 제공되는 자율 코딩 에이전트 | 5M+ 설치; JetBrains·Cursor·Zed·Neovim 확장 + 공개 SDK; Roo/Kilo의 upstream | TypeScript |
| block/goose | ~50.1k | MCP로 코드 설치·실행·편집·테스트하는 on-device 에이전트 | Block(Square) 후원; Linux Foundation Agentic AI Foundation으로 거버넌스 이전 | Rust |
| Aider-AI/aider | ~46.7k | diff/patch로 파일을 편집하는 터미널 AI 페어 프로그래밍 도구 | 터미널/Git 네이티브 픽; 자체 edit-format 리더보드 | Python |
| continuedev/continue | ~33k | CLI/VS Code/JetBrains로 제공되는 설정성 높은 코딩 에이전트 | 2026 Cursor에 인수, 2.0.0 최종 릴리스 후 OSS read-only 전환 | TypeScript |
| SWE-agent/SWE-agent | ~19k | GitHub 이슈를 받아 자동 수정(NeurIPS 2024) | agent-computer interface를 대중화한 학술 레퍼런스; SWE-agent 2.0 라인 | Python |
| SWE-agent/mini-swe-agent | ~7k | ~100줄짜리 radically simple 에이전트 | ~100줄로 SWE-bench Verified 74%+ 기록하며 바이럴 | Python |
| gptme/gptme | ~4k | 로컬 도구를 갖춘 터미널 개인 AI 에이전트(코드/셸/웹/vision) | ActivityWatch 제작자; 24/7 자율 'Bob' 에이전트로 주목 | Python |

### 2-3. End-user AI 앱 (chat / RAG / agent 플랫폼)

| 레포 (owner/repo) | ⭐ 대략 스타 | 한 줄 설명 | 모멘텀 / 인기 이유 | 언어 |
|---|---|---|---|---|
| n8n-io/n8n | ~194k | 네이티브 AI + 400+ 통합의 fair-code 워크플로 자동화 플랫폼 | GitHub 최다 스타 개발 도구급; AI-agent 워크플로로 전환 후 모멘텀 리더 | TypeScript |
| langflow-ai/langflow | ~150k | 드래그앤드롭 비주얼 빌더(프로덕션 Python으로 컴파일) | no-code 에이전트 프로토타이핑 선두로 150k 구간 진입 | Python |
| langgenius/dify | ~146k | 비주얼 워크플로+RAG+API/서빙을 한 서비스로 묶은 agentic 플랫폼 | "직접 만들어 배포" 제품의 de facto 레퍼런스 | TypeScript/Python |
| open-webui/open-webui | ~143k | 완전 셀프호스트 ChatGPT-style UI(오프라인, Ollama/OpenAI 호환, RAG) | 124k->143k, 280M+ 다운로드; 셀프호스팅 커뮤니티 기본 UI | Svelte/Python |
| infiniflow/ragflow | ~83.5k | deep document understanding + agentic retrieval + 인용 grounding RAG 엔진 | 문서 중심 엔터프라이즈 KB에서 선호; 가장 빠르게 상승한 RAG | Python/TS |
| lobehub/lobehub | ~79k | 디자인 중심 멀티 에이전트 chat/프레임워크(구 lobe-chat, PWA) | lobe-chat에서 리브랜딩, 'agent operations'로 전환 | TypeScript |
| Mintplex-Labs/anything-llm | ~62k | RAG+에이전트+no-code 파이프라인+네이티브 MCP의 local-first 올인원 앱 | 45k->62k; 'own your intelligence' 선두, 초기 MCP 호환 | JavaScript |
| FlowiseAI/Flowise | ~54k | no-code 드래그앤드롭 비주얼 에이전트/워크플로 빌더 | no-code AI 빌더 mainstay; flow 위에 agent/assistant primitive 추가 | TypeScript |
| danny-avila/LibreChat | ~39.8k | 에이전트·MCP·code interpreter·멀티 provider·멀티유저 auth의 ChatGPT 클론 | 가장 기능 완비된 셀프호스트 멀티유저 chat | TypeScript |

### 2-4. 딥리서치 · 뉴스 에이전트 (Deep-research, news & briefing)

| 레포 (owner/repo) | ⭐ 대략 스타 | 한 줄 설명 | 모멘텀 / 인기 이유 | 언어 |
|---|---|---|---|---|
| stanford-oval/storm | ~29k | 토픽을 리서치해 인용 포함 Wikipedia-style 장문 생성 | Stanford OVAL; Co-STORM(협업 멀티 에이전트 담론) 추가, 학술 gold-standard | Python |
| assafelovic/gpt-researcher | ~28k | 임의 토픽/데이터를 deep research해 인용 리포트 생성 | 레퍼런스 deep-research 프레임워크; recursive 'Deep Research' 추가(Tavily 팀) | Python |
| dzhng/deep-research | ~19k | 검색+스크래핑+LLM으로 스스로 방향을 다듬는 minimal iterative 에이전트 | OpenAI Deep Research 직후 '가장 단순한 구현'으로 바이럴 | TypeScript |
| langchain-ai/open_deep_research | ~12k | provider/검색/MCP 전반에서 동작하는 오픈 deep research 에이전트 | LangGraph supervisor/sub-agent 아키텍처로 재구축, teaching 레퍼런스 | Python |
| langchain-ai/local-deep-researcher | ~9k | 로컬 LLM(Ollama/LMStudio)로 반복 리서치+리포트 작성 | privacy-first run-it-yourself 흐름; LangGraph Studio 연동, TS 포트 | Python |
| LearningCircuit/local-deep-research | ~6.6k | SimpleQA ~95%, 10+ 소스(arXiv/PubMed/web/사적 문서) 로컬·암호화 | 강한 SimpleQA 수치 + zero-telemetry/encrypted 입장 | Python |
| rotemweiss57/gpt-newspaper | ~1.5k | 6개 협업 에이전트로 개인화 신문을 큐레이트·작성·디자인·편집 | 스타는 적지만 high-signal(Tavily/gpt-researcher 팀, LangChain flagship LangGraph 데모) | Python |

### 2-5. MCP 생태계 (servers & tool/connector)

| 레포 (owner/repo) | ⭐ 대략 스타 | 한 줄 설명 | 모멘텀 / 인기 이유 | 언어 |
|---|---|---|---|---|
| punkpeye/awesome-mcp-servers | ~89.7k | 최다 스타 커뮤니티 MCP 서버 카탈로그(30+ 카테고리, Glama 연계) | MCP 채택 폭발로 ~90k 돌파; 주 discovery surface | (list) |
| modelcontextprotocol/servers | ~87.7k | MCP 서버 공식 reference 구현(secure tool/data 접근) | Anthropic-stewarded canonical repo; cross-vendor 표준화로 상승 | Python/TS |
| upstash/context7 | ~58k | version-accurate 코드 문서를 LLM/에디터에 주입하는 MCP 서버 | 가장 빠르게 상승한 MCP 서버; Cursor/Claude Code에서 널리 채택(본 환경에 plugin 번들) | TypeScript |
| microsoft/playwright-mcp | ~34k | Playwright 기반 구조화 브라우저 자동화 MCP(accessibility-tree, 스크린샷 불필요) | Microsoft 후원; 에이전트 웹 상호작용 표준(본 환경 plugin) | TypeScript |
| github/github-mcp-server | ~31k | repos/issues/PR/workflows에 연결하는 GitHub 공식 MCP 서버 | first-party 출시 후 top 공식 MCP; Go 재작성으로 엔터프라이즈 신호 | Go |
| mendableai/firecrawl-mcp-server | ~7k | 웹 스크래핑/크롤/검색을 더하는 Firecrawl 공식 MCP 서버 | clean web-to-markdown 추출의 go-to(리서치 에이전트) | TypeScript |
| exa-labs/exa-mcp-server | ~5k | semantic/neural 웹 검색·코드 검색·기업 리서치 MCP | embeddings 기반 검색; agentic 리서치 확산으로 상승 | TypeScript |
| wong2/awesome-mcp-servers | ~4k | reference/official/community MCP 서버 디렉터리(mcp.so 연계) | punkpeye 다음의 보조 인덱스, 지속 업데이트 | (list) |
| spences10/mcp-omnisearch | ~500 (rough) | 다중 검색/추출 provider(Tavily·Brave·Kagi·Exa·Firecrawl·Perplexity) 통합 MCP | provider-agnostic 'meta' 검색 MCP 흐름; best-web-search 라운드업 단골 | TypeScript |
| brave/brave-search-mcp-server | ~500 (rough) | Brave의 독립 privacy-first 웹 검색 인덱스를 노출하는 공식 MCP | Google/Bing 비의존 독립 인덱스; 엔터프라이즈 privacy 포지셔닝 | TypeScript |

### 2-6. 트렌딩 / awesome-list 브레이크아웃 (보너스)

| 레포 (owner/repo) | ⭐ 대략 스타 | 한 줄 설명 | 모멘텀 / 인기 이유 | 언어 |
|---|---|---|---|---|
| Shubhamsaboo/awesome-llm-apps | ~115k | clone-and-ship 가능한 100+ AI Agent & RAG 앱 모음 | runnable agent/RAG 앱 큐레이션의 지배적 리스트 | (list) |
| browser-use/browser-use | ~101k | AI 에이전트용 웹사이트 접근/브라우저 작업 자동화 | 역사상 가장 빠른 OSS 성장 중 하나로 인용, 수개월 내 100k 돌파 | Python |
| wshobson/agents | ~37.1k | Claude Code·Codex·Cursor·OpenCode·Copilot·Gemini용 멀티 하네스 플러그인 마켓 | 단일 Markdown 소스 -> 6개 하네스 네이티브 artifact(192 agents/156 skills/102 commands) | (Markdown) |
| bradAGI/awesome-cli-coding-agents | ~600 (rough) | 90+ 터미널 코딩 에이전트 + 오케스트레이션/샌드박스 하네스 디렉터리 | Claude Code/Codex 하네스 지형을 직접 매핑한 fresh 브레이크아웃 | (list) |

---

## 3. 내 News Briefing Agent에 시사점 (Implications)

이 프로젝트는 **Claude Code + Codex 듀얼 하네스(dual-harness)** 위에서 동작하며, 핵심 테마는 **검증 후 실행 게이트(verify-before-fire gate)** 와 **의무 원장(obligation ledger)** 입니다. 아래 레포들은 참고/재사용 가치가 높습니다.

### A. 리서치·합성 엔진 (가장 직접적)

- **assafelovic/gpt-researcher (~28k)** — News Briefing Agent의 코어 엔진 패턴: `planner -> 멀티소스 web research -> cited synthesis`. 인용(citation) 처리 구조가 "주장은 출처로 정당화한다"는 verify-before-fire 게이트에 그대로 매핑됩니다. recursive Deep Research 워크플로는 deep-dive 토픽에 재사용 가능.
- **rotemweiss57/gpt-newspaper (~1.5k)** — **사용자 프로젝트에 가장 가까운 직접 아키텍처 템플릿.** Search/Curator/Writer/Critique/Designer/Editor 6개 협업 에이전트가 개인화 신문을 생성. Critique 단계는 적대적 검증(adversarial critique) = 의무 원장의 검증 항목으로 차용 가능. LangGraph 기반이라 상태/체크포인트도 함께 참고.
- **stanford-oval/storm (~29k)** — perspective-guided question asking + 전문가 대화 시뮬레이션으로 **단일 출처 요약이 아닌 균형 잡힌 다각도 브리핑**을 만드는 템플릿. 편향 줄이기에 유용.
- **langchain-ai/open_deep_research (~12k)** — supervisor가 sub-agent에게 위임하는 패턴 + pluggable search/MCP 도구. **토픽별 병렬 뉴스 수집**과 깔끔한 report-writing 단계에 직접 재사용. LangGraph의 checkpoint/approval 게이트는 verify-before-fire와 1:1 대응.
- **dzhng/deep-research (~19k)** — ~수백 줄의 readable한 iterative search+scrape+reason 루프. lean한 리서치 백본으로 fork하기 좋음(미니멀 하네스 철학과 일치).

### B. MCP 뉴스/검색/스크래핑 커넥터 (도구 표면)

Claude Code와 Codex 모두 MCP를 말하므로, 뉴스 수집 도구 계층은 bespoke 통합 대신 MCP로 구성하는 것이 유리합니다.

- **spences10/mcp-omnisearch (~500)** — Tavily·Brave·Kagi·Exa·Firecrawl·Perplexity를 **하나의 인터페이스 + fallback**으로 통합. 뉴스 에이전트가 한 API에 lock-in되지 않게 하는 검색 계층 아키텍처 레퍼런스(또는 직접 커넥터).
- **exa-labs/exa-mcp-server (~5k)** — semantic/neural 검색. 키워드가 실패하는 리서치형 질의에 강점, 뉴스/리서치 코어 역량.
- **mendableai/firecrawl-mcp-server (~7k)** — clean web-to-markdown 스크래핑+검색. 단순 fetch 이상으로 기사 본문 추출이 필요할 때.
- **brave/brave-search-mcp-server (~500)** — 독립 인덱스 + privacy-first. 사적 코퍼스/오프라인 요구가 있을 때 privacy 백엔드로 적합.
- **microsoft/playwright-mcp (~34k)** — accessibility-tree 기반 브라우저 제어. 검색/fetch로 닿지 않는 라이브 페이지 navigate/추출에 필요(본 환경에 plugin으로 이미 존재).
- **modelcontextprotocol/servers (~87.7k)** — 공식 Fetch 서버 등 기본 ingestion 빌딩 블록.
- 카탈로그(**punkpeye/awesome-mcp-servers ~89.7k**, **wong2/... ~4k**)는 새 뉴스/검색 커넥터를 발굴하는 living 디렉터리로 주기적 참조.

### C. 듀얼 하네스 & verify-before-fire 구조적 선행 사례

- **wshobson/agents (~37.1k)** — **Claude Code AND Codex를 명시적으로 span하는 멀티 하네스 레이어.** 단일 Markdown 소스로 하네스별 artifact를 생성하는 패턴은 이 프로젝트의 cross-harness sync에 강력한 prior art.
- **langchain-ai/langgraph (~36k)** — checkpoint·rollback point·approval gate를 가진 stateful graph. **verify-before-fire 게이트 + 의무 원장**의 직접적 유사물.
- **OpenHands/OpenHands (~78.2k)** — event-sourced Software Agent SDK + 샌드박싱 + task tracking. 가장 가까운 아키텍처 peer.
- **pydantic/pydantic-ai (~18k)** — type-safe·schema-validated 출력. 구조화된 의무(obligation)와 검증 가능한 contract 강제에 부합.
- **SWE-agent/mini-swe-agent (~7k)** — ~100줄 하네스 청사진. 하네스가 네이티브로 하는 일을 중복하지 말고 **앱을 lean하게 유지**하라는 설계 지침.

### D. End-user UX / 배포 참고

- **open-webui (~143k)**, **lobehub (~79k)** — 에이전트 스케줄·리포팅·**의무 대시보드(obligation dashboard)** 를 비개발자에게 보여줄 UX 바.
- **Dify (~146k)**, **anything-llm (~62k)** — RAG+에이전트+MCP를 단일 배포 제품으로 패키징하는 close analog.

---

## 4. 주의 (Caveats)

- **모든 스타(⭐) 수는 근사치**입니다. verification에서 확인된 수치를 우선 반영했으며, 일부는 반올림 차이가 있습니다(예: Goose는 청구 ~48k 대비 실제 ~50.1k로 다소 높음).
- **`not-found`로 표시된 항목은 없었습니다.** 모든 레포가 confirmed 상태였으므로 제외 항목은 없습니다. 다만 **`sst/opencode`는 현재 `anomalyco/opencode`로 이전/리네임(redirect)** 되었으니 링크 사용 시 유의하세요.
- `~500`/`~600 (rough)`로 표시된 소규모 레포는 verification 리스트에 포함되지 않은 rough 추정치이므로 특히 변동 가능성이 큽니다.
- 언어(Language) 컬럼은 각 레포의 주력 구현 언어 기준이며, awesome-list류는 `(list)`/`(Markdown)`으로 표기했습니다.

---

*9개 에이전트 리서치 워크플로우로 생성(6개 카테고리 병렬 웹 리서치 → 중복 제거·랭킹 → 상위 24개 실존 웹 재검증 → 한국어 종합). 검증 단계에서 not-found 0건. 작성일: 2026-06-24.*
