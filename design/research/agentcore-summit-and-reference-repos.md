# AgentCore 신기능(AWS Summit NY) + 레퍼런스 리포 2개 — 구현 종합

> **목적:** AWS Summit New York의 **AgentCore 신기능**을 검증하고, 사용자의 레퍼런스 리포 2개([web-search-mcp](https://github.com/gonsoomoon-ml/web-search-mcp) · [aiops-multi-agent-workshop](https://github.com/gonsoomoon-ml/aiops-multi-agent-workshop))를 분석해 **뉴스 브리핑 에이전트 구현**([`../prd/prd.md`](../prd/prd.md) 참조 리소스)으로 연결.
> **방법:** 3-에이전트 병렬 리서치 — ① 로컬 클론 web-search-mcp 분석 · ② 로컬 클론 aiops 스캐폴드 추출 · ③ Summit 발표 1차 자료 검증(상호 비상관). 2026-06-26 · Korean-friendly. 모든 외부 주장 출처 URL 보존.
> **연결 문서:** [`../architecture/retrieval-gateway-analysis.md`](../architecture/retrieval-gateway-analysis.md)(이 발견으로 부분 갱신됨) · [`../architecture/four-component-analysis.md`](../architecture/four-component-analysis.md) · [`briefing-news-agent-spec-research.md`](briefing-news-agent-spec-research.md) · [`../prd/prd_news.md`](../prd/prd_news.md)

---

## 0. 한 줄 결론
**Summit NY의 신기능 = `Web Search on AgentCore`** (관리형 1st-party 웹검색, 2026-06 GA). 이것 + **Browser Tool**이 우리 리트리벌의 두 약점(고정 RSS의 발견 한계 · OpenAI Cloudflare/Anthropic HTML의 fragile 페치)을 *관리형*으로 메운다 — 단 **decorrelation 불변식(권위 페치는 fabric 소유, sha256 source-of-record)은 그대로**. 그리고 **aiops 리포가 구현 스캐폴드를 그대로 제공**(shared/runtime 분리 · UV · 루트 `.env` · Gateway×Strands×Runtime 배선).

## 1. AWS Summit New York — AgentCore 타임라인 & 신기능 (검증)
| 시점 | 사건 | 출처 |
|---|---|---|
| **2025-07-16** | Summit NYC에서 AgentCore **프리뷰 출시**(Swami 키노트). 빌트인 툴 = **Browser Tool + Code Interpreter 뿐, 웹검색 없음** | [preview blog](https://aws.amazon.com/blogs/aws/introducing-amazon-bedrock-agentcore-securely-deploy-and-operate-ai-agents-at-any-scale/) |
| **2025-10-13** | AgentCore **GA**, consumption pricing 가동 | [GA What's New](https://aws.amazon.com/about-aws/whats-new/2025/10/amazon-bedrock-agentcore-available/) · [GA blog](https://aws.amazon.com/blogs/machine-learning/amazon-bedrock-agentcore-is-now-generally-available/) |
| **2026-06-16~17** | **★ Summit NY 2026: `Web Search on AgentCore` 발표(GA day-one)** | [Web Search blog](https://aws.amazon.com/blogs/aws/announcing-web-search-on-amazon-bedrock-agentcore-ground-your-ai-agents-in-current-accurate-web-knowledge/) · [What's New](https://aws.amazon.com/about-aws/whats-new/2026/06/amazon-bedrock-agentcore-web-search/) |

- **프리미티브:** Runtime(세션격리 서버리스 호스팅) · Memory · Identity(OAuth 스코프 자격) · Gateway(API/Lambda/MCP→도구) · Observability · **Browser Tool**(관리형 격리 브라우저) · **Code Interpreter**. 이후 추가: Policy, Evaluations, Optimization, Agent Registry, Payments, Harness. [built-in-tools](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/built-in-tools.html)
- **★ Web Search(핵심 신기능):** 관리형 1st-party, **Gateway managed connector**(`connectorId:"web-search"`), MCP 호환, **Amazon 운영 인덱스(수백억 문서)** — 3rd-party 래퍼 *아님*. [tool doc](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-target-connector-web-search-tool.html)
  - 뉴스에 딱 맞는 속성: **freshness**(인덱스 "분 단위" 갱신, `publishedDate` 반환) · **citations**(title/URL/snippet 반환, **AUP가 출처링크 표시를 의무화** → 우리 verify-before-publish/Tap-to-Source와 정렬) · knowledge graph · semantic snippet · **zero data egress**(쿼리가 AWS 내부) · domain denylist.
  - **제약:** **us-east-1 전용** · 쿼리 200자 cap · 최대 25 results · **~$7 / 1,000 쿼리**(MEDIUM).
- ⚠️ **혼동 금지:** Web Search ≠ Gateway **semantic search**(*자기 도구* 선택용 자연어 검색, 별개·구기능). [semantic-search doc](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-using-mcp-semantic-search.html)

## 2. 리트리벌 판정 갱신 ([`../architecture/retrieval-gateway-analysis.md`](../architecture/retrieval-gateway-analysis.md) 대비)
이전 결론 = "v1엔 Gateway 불필요(공개 RSS 감싸기는 indirection)." → **부분 갱신:** 이제 *관리형 리트리벌 프리미티브 2종*이 GA로 존재한다.
- **Discovery(발견) = 네이티브 Web Search connector** — fresh + cited. 고정 5~7 RSS의 *발견 한계*(펀딩/M&A 공백, 카테고리 빈 날)를 메우고, citation 의무가 verify-before-publish와 정렬.
- **Authoritative full-text fetch = Browser Tool** — 관리형 격리 브라우저가 **OpenAI Cloudflare·Anthropic HTML "fragile fetch"의 관리형 해답**(내가 가정한 "헤드리스 브라우저 Lambda"를 AWS가 대신). [browser-tool doc](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/browser-tool.html)
- **★ 핵심 불변식은 불변:** Web Search/Browser Tool은 *어떻게* 페치하느냐일 뿐 — *누가 권위 사본을 소유하느냐*(**fabric**, content-addressed **sha256** source-of-record)는 그대로. Web Search는 **search-only(snippet)** 라 certifier의 source-of-record엔 여전히 full-text 페치(Browser Tool/HTTP)가 필요.
- **비용/리전 현실:** us-east-1 전용 + $7/1k(Web Search) + Browser Tool 별도 → **v1의 5~7 고정 출처엔 plain RSS/HTTP가 여전히 더 싸다.** Web Search는 *발견 범위를 고정 RSS 너머로 넓힐 때* 값을 번다(→ v1.5/v2 옵션).

## 3. `web-search-mcp` — 관리형 검색을 Gateway + Claude Code로 (실증)
- **두 백엔드:** ① **Tavily**(기본, `server/lambda/web_search/handler.py` → `api.tavily.com/search`, `TAVILY_API_KEY` in `.env`) · ② **네이티브 AgentCore Web Search**(opt-in, `server/setup_native_gateway.py`/`deploy-native.sh`, connector 타깃, Lambda·키 불필요).
- **MCP 노출:** tool `web_search` → 클라이언트엔 `web-search___web_search`(`<target>___<tool>`). in `{query, max_results 1-20}`, out `{title,url,snippet,score}`. Gateway = `protocolType="MCP"`, `authorizerType="CUSTOM_JWT"`(Cognito 3-way verify), outbound=`GATEWAY_IAM_ROLE`.
- **★ Claude Code 연결(확정 — headless 함정 포함):** `clients/claude-code/local_test.sh`가 임시 `.mcp.json` 작성 → `{"mcpServers":{"web-search":{"type":"http","url":GATEWAY_URL,"headers":{"Authorization":"Bearer <jwt>"}}}}` → `claude --mcp-config <file> --strict-mcp-config`. **반드시:** `ENABLE_TOOL_SEARCH=false`(Bedrock가 tool def 선로드, 아니면 "400 Tool reference not found") · `CLAUDE_CODE_USE_BEDROCK=1` · Cognito JWT **~1h 만료**(장기 잡은 재발급).
- **한계:** **search-only — `fetch_url`은 명시적 범위 밖**(`server/README.md`). → 우리에겐 *discovery* 도구. (specced-but-unbuilt: `web_search`+`fetch_url` 2-tool 설계, `design/research-comparison.md` §5.)

## 4. `aiops-multi-agent-workshop` — 구현 스캐폴드 (채택 블루프린트)
- **★ 채택 1순위 = `shared/`(진실) vs `runtime/`(배포 하니스) 분리:** `shared/agent.py`의 `create_agent(tools, system_prompt)` 팩토리 → `runtime/agentcore_runtime.py`가 `BedrockAgentCoreApp()` + `@app.entrypoint`로 감쌈. *동일 코드*를 로컬↔Runtime 양쪽 실행.
- **UV:** 루트 `pyproject.toml`(`[tool.uv] package=false`, `requires-python>=3.12`, dev=[ruff]) + `uv.lock`; `uv sync`/`uv run`. **컨테이너는 uv.lock 미사용 — per-runtime 최소 `requirements.txt`**(`strands-agents`,`strands-agents-tools`,`bedrock-agentcore`).
- **`.env`:** 단일 루트 `.env` + `.env.example` 템플릿; 3방식 로드(shell `set -a;source`, `load_dotenv(override=True)`, 컨테이너엔 `Runtime.launch(env_vars=...)`로 OS-env 주입 — 컨테이너는 `.env` 안 읽음). 각 `deploy.sh`가 prefix 키(`INCIDENT_*` 등)를 루트 `.env`에 sed-update.
- **모델 id:** **inference-profile** `global.anthropic.claude-sonnet-4-6`(`.env.example`) — 우리 분석과 일치.
- **Gateway 배선:** `create_gateway(protocolType="MCP", authorizerType="CUSTOM_JWT", customJWTAuthorizer={discoveryUrl,allowedClients,allowedScopes})` + `create_gateway_target`(Lambda, inline `toolSchema`, `GATEWAY_IAM_ROLE`). Runtime→Gateway = `@requires_access_token(provider, scopes, auth_flow="M2M")` → `MCPClient(streamablehttp_client(GATEWAY_URL, headers={Authorization:Bearer}))`.
- **Dockerfile:** base `ghcr.io/astral-sh/uv:python3.13-bookworm-slim`, non-root, `CMD ["opentelemetry-instrument","python","-m","agentcore_runtime"]`. **ARM64 명시 없음**(toolkit 기본 + CodeBuild가 이미지 빌드).
- **IaC = 하이브리드:** CloudFormation(plumbing: Cognito/Lambda) + **boto3 step-by-step(AgentCore Gateway/Target/Runtime)**. CDK/SAM 아님. `bootstrap.sh`(uv sync→`.env`→region/user→storage→X-Ray) · `pre-requesite.sh`(uv·py3.12·docker·SSM·PowerUser+IAMFull) · `teardown_all.sh`(역순).
- **복사용 폴더 스켈레톤:**
```
pyproject.toml  uv.lock  .env.example  bootstrap.sh  teardown_all.sh
agents/<name>/
  shared/  agent.py  prompts/system_prompt.md  mcp_client.py  env_utils.py
  runtime/ agentcore_runtime.py  deploy_runtime.py  invoke_runtime.py
           Dockerfile  .dockerignore  requirements.txt  teardown.sh
  local/   run.py            # 로컬 baseline, AWS 불필요
infra/<resource>/ deploy.sh  *.yaml(CFN)  setup_*.py(boto3)  teardown.sh
```

## 5. author→certifier 매핑 — 채택 + 한 가지 *교정*
- aiops **Supervisor + A2A** 구조 = 우리 author→certifier 토폴로지의 청사진: 별도 Runtime, 발행 전 호출, 최소-컨텍스트 메시지(A2A `Message`에 claim+source만, narration 금지 — decorrelation과 정렬).
- **★ 교정 2가지(그대로 베끼면 안 됨):**
  1. aiops는 *Supervisor LLM이 라우팅 결정*(author가 sub-agent를 `@tool`로 호출). 우리 [4-컴포넌트 불변식](../architecture/four-component-analysis.md)은 **gate(결정론 코드)가 certifier를 호출**(author 아님) → narration 차단을 *토폴로지로* 강제. 따라서 "author LLM이 certifier 호출" 패턴은 **거부**.
  2. 우리 certifier = **Codex CLI(`codex exec`)**, Strands A2A 에이전트 아님 → certifier는 (a) `codex exec`를 한 Runtime/도구로 감싸거나 (b) **gate가 직접 shell-out**. A2A의 *형태*(별도 실행경계·최소 핸드오프)는 빌리되 *호출 주체 = gate*로 둔다.

## 6. 구현 권고 (→ `prd/prd.md` 방향 결정)
- **v1 스택 확정:** Strands author-agent on **AgentCore Runtime**(`shared/`+`runtime/` 분리) + Claude Code(author, `.mcp.json` 패턴) + Codex(certifier, **gate가 호출**) + (옵션)Gateway.
- **v1 리트리벌:** 5~7 고정 출처는 **plain RSS/HTTP**(fabric 소유 페치) 유지 — 깨지는 출처(OpenAI/Anthropic)만 **Browser Tool**로 관리형 흡수. **Web Search connector는 v1.5 옵션**(발견 확장; us-east-1·$7/1k 감안).
- **스캐폴드:** aiops **Phase 2+3** 채택 — shared/runtime, UV, 루트 `.env`(prefix sed-update), CFN+boto3 하이브리드 IaC, Dockerfile+per-runtime requirements.txt, `/schedule`(또는 Scheduler→Lambda→invoke)로 07:00 발화.
- **리전 결정 영향:** Web Search/Browser Tool = **us-east-1 전용** → 전체 스택 리전을 us-east-1로 정렬할지 결정 필요(model inference-profile 가용성과 함께).
- **de-risk 추가:** Browser Tool로 Cloudflare 흡수 PoC · Web Search citation→Tap-to-Source 연결 PoC.

## 7. 참조 (References)
- Web Search on AgentCore: [blog](https://aws.amazon.com/blogs/aws/announcing-web-search-on-amazon-bedrock-agentcore-ground-your-ai-agents-in-current-accurate-web-knowledge/) · [tool doc](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-target-connector-web-search-tool.html) · [What's New](https://aws.amazon.com/about-aws/whats-new/2026/06/amazon-bedrock-agentcore-web-search/)
- AgentCore preview/GA: [preview](https://aws.amazon.com/blogs/aws/introducing-amazon-bedrock-agentcore-securely-deploy-and-operate-ai-agents-at-any-scale/) · [GA](https://aws.amazon.com/blogs/machine-learning/amazon-bedrock-agentcore-is-now-generally-available/) · [built-in-tools](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/built-in-tools.html) · [browser-tool](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/browser-tool.html) · [pricing](https://aws.amazon.com/bedrock/agentcore/pricing/)
- 레퍼런스 리포: [web-search-mcp](https://github.com/gonsoomoon-ml/web-search-mcp) · [aiops-multi-agent-workshop](https://github.com/gonsoomoon-ml/aiops-multi-agent-workshop)
