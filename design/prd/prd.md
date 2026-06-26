## Goal
Claude Code 와 Codex 를 같이 사용을 합니다.
두개의 코딩 툴을 장점을 결합하여 실용적인 AI Agent or AI Application 을 만드는 것이 목표 입니다.


## What AI Agent or AI Application to be build
- 어떠한 실용적인 AI Agent or AI Application 만들지를 깊이 리서치 해야 합니다. 
- Claude Code 와 Codex 의 Harness 를 사용하여 ,만들 수 있는 것이면 우리가 만드는 대상에서 제외 입니다. 이 조건이 아주 중요합니다. 깊이 리서치가 필요 합니다.
- 커스터마이징이 가능한 News 브리핑 에이전트를 고려해보세요. Skill 등을 통해 News 의 종류 (얘: AI News, Stock News 등)를 정의할 수 있고, 또한 뉴스 브랜드 (예: AI Times ) 를 정할 수 있고, 뉴스의 요약 정도 (예: 뉴스 제목 및 링크만 제공 혹은 요약까지 같이 제공) 등의 설정도 할 수 있습니다.

## How to use
- AI Agent or Application 이 일상적으로 유용하다면, 다른 사람들이 사용을 권장을 할 수 있습니다.
만약 뉴스 브리핑에 초점을 맞춘다면, 나 개인의 사용에 초점을 두고, 유용성이 확정이 되면, 다른사람에게 사용을 권장을 할 수 있다.

## Consideration
- Claude Code 와 Codex 의 장점과 단점을 리서치해서, 구현시에 어떠한 부분은 Claude Code 혹은 Codex 를 사용할지를 결정할 수 있습니다. (예: Plan/Generate Code: Claude Code, Review : Codex)


## 방향 결정

> `design/` 분석(리서치·아키텍처)을 거쳐 **확정된 v1 방향**. 근거·상세는 각 링크 문서 참조. 제품 요구사항 상세 = [`prd_news.md`](prd_news.md).

**1) 제품 (What).** 커스터마이즈 가능한 **개인용 매일 아침 뉴스 브리핑** + 핵심 차별점 **검증 후 발행(verify-before-publish) 게이트.** Claude=작성자, Codex=독립 인증자. → [`prd_news.md`](prd_news.md)

**2) 스택 (How).** **Strands(author 에이전트) + Bedrock AgentCore Runtime(호스트) + Claude Code(author 하니스) + Codex(certifier 하니스).** 오케스트레이션·비가역 발송 결정은 **얇은 결정론 게이트 코드**가 소유하고, **게이트가 certifier를 호출**(author 아님 — narration 차단을 토폴로지로 강제). → [`../architecture/four-component-analysis.md`](../architecture/four-component-analysis.md)

**3) 리전 (Region).** **us-east-1 정렬.** 신규 관리형 리트리벌(Web Search·Browser Tool)이 us-east-1 전용이고, 모델은 inference-profile(`global.`/`us.` prefix) 사용. → [`../research/agentcore-summit-and-reference-repos.md`](../research/agentcore-summit-and-reference-repos.md)

**4) 리트리벌 (Retrieval).** v1 = **고정 5~7 출처 plain RSS/HTTP**(fabric 소유 페치 → **sha256 content-addressed source-of-record**). 깨지는 출처(OpenAI Cloudflare·Anthropic HTML)는 **Browser Tool**(관리형 격리 브라우저)로 흡수. 네이티브 **Web Search**(Summit NY 2026 신기능)는 *발견(discovery) 확장* **v1.5 옵션**(us-east-1·$7/1k). **불변식:** *권위 페치는 fabric만 originate* · author는 동결본 **read만**(자기 source originate 금지) · certifier는 **tool-starved(envelope-fed)**. **v1.5:** 이 source-of-record를 **Gateway 'identical channel'**(`fetch_and_freeze`/`get_source` + principal별 scope)로 구조화 → 바이트 동일성·정규화 단일화를 *메커니즘*으로 강제. → [`../architecture/retrieval-gateway-analysis.md`](../architecture/retrieval-gateway-analysis.md)

**5) 검증 게이트 (Verify-before-publish).** v1 = **(a) 함의(NLI) + (b) 숫자/날짜/% 산술 재도출**, *이미 가져온 원문 텍스트에만*(신규 fetch 없음 → 법적 리스크 회피). 출력 3종 **VERIFIED / DEMOTED-TO-UNCERTAIN / BLOCKED**(조용한 드롭 금지). certifier = Codex(`codex exec`), **최소 컨텍스트**(narration 차단). → [`prd_news.md`](prd_news.md) §5

**6) 구현 스캐폴드 (Scaffold).** [aiops-multi-agent-workshop](https://github.com/gonsoomoon-ml/aiops-multi-agent-workshop) **Phase 2+3** 채택 — `shared/`(진실) vs `runtime/`(배포) 분리 · UV(`[tool.uv] package=false`, 컨테이너는 per-runtime `requirements.txt`) · 단일 루트 `.env` · Gateway(MCP+CUSTOM_JWT) + Runtime(`BedrockAgentCoreApp`+`@app.entrypoint`) · IaC 하이브리드(CFN plumbing + boto3 AgentCore) · `/schedule`(또는 Scheduler→Lambda→invoke)로 **KST 07:00** 발화. A2A·멀티테넌트·storage-dual은 생략. Claude Code MCP 연결·headless 패턴 = [web-search-mcp](https://github.com/gonsoomoon-ml/web-search-mcp). → [`../research/agentcore-summit-and-reference-repos.md`](../research/agentcore-summit-and-reference-repos.md) §4·6


## 참조 리소스
- Amazon Bedrock 위에서 Codex와 Claude Code 함께 쓰기: Harness Engineering으로 구현해보기
    - https://aws.amazon.com/ko/blogs/tech/codex-claudecode-harness/
- briefing-news-agent
    - https://github.com/gonsoomoon-ml/briefing-news-agent
- web-search-mcp
    - keyword: AgentCore Gateway, Web Search Tool, Search API
    - https://github.com/gonsoomoon-ml/web-search-mcp
- aiops-multi-agent-workshop
    - keyword: AgentCore Gateway, Strands Agent, AgentCore Runtime, Project Setting Environment(UV, .env, folder structure )
    - https://github.com/gonsoomoon-ml/aiops-multi-agent-workshop    