# 뉴스 리트리벌 × AgentCore Gateway × headless Claude Code — 분석

> **목적:** 기사/블로그 *리트리벌(retrieval)* 에지를 **Amazon Bedrock AgentCore Gateway** 로 구성할 가치가 있는지, 그리고 그것이 **headless Claude Code(`claude -p`)** 와 어떻게 "어울리는지(get along)" 분석. (인프라 배포 스텝은 별도 구현 플랜.)
> **방법:** 리트리벌 baseline 재확인([`../research/briefing-news-agent-spec-research.md`](../research/briefing-news-agent-spec-research.md) §3.1) + AgentCore Gateway 1차 자료 검증(리서치 에이전트, 출처 URL 보존) + [`four-component-analysis.md`](four-component-analysis.md) 의 decorrelation 불변식과 정합. 2026-06-26 · Korean-friendly.
> **연결 문서:** [`four-component-analysis.md`](four-component-analysis.md) · [`harness-to-verify-before-publish-mapping.md`](harness-to-verify-before-publish-mapping.md) · [`value-roadmap.md`](value-roadmap.md) · [`../prd/prd_news.md`](../prd/prd_news.md)

---

> **⚠️ 갱신(2026-06-26):** 이 분석 이후, **AWS Summit NY 2026에서 `Web Search on AgentCore`(관리형 1st-party 웹검색)가 GA**되었음을 확인 — 추가로 **Browser Tool**(관리형 격리 브라우저)이 Cloudflare/HTML "fragile fetch"의 관리형 해답이 된다. 즉 *관리형 리트리벌 프리미티브가 존재*하므로 아래 "v1엔 불필요" 결론은 **discovery·fragile-fetch 측면에서 부분 갱신**된다. **단 핵심 불변식(권위 페치=fabric 소유, content-addressed source-of-record, certifier=tool-starved)은 불변.** 상세 = [`../research/agentcore-summit-and-reference-repos.md`](../research/agentcore-summit-and-reference-repos.md) §2.

## 0. 한 줄 결론
**리트리벌에 한해 Gateway는 *어댑터*이지 *페처(fetcher)*가 아니다.** 공개 RSS/블로그 5~7개(무인증)엔 과하다(순수 indirection). Gateway가 값을 버는 건 **v2** — 인증 API·여러 하니스가 공유하는 도구 카탈로그·중앙 관측성. 그리고 가장 중요한 것: **Gateway를 author(Claude Code) 손에 쥐여주면 안 된다** — *권위(authoritative) 페치는 fabric이 소유*하고 content-addressed(해시)로 고정해야 verify-before-publish의 decorrelation이 유지된다.

## 1. 리트리벌 문제의 두 갈래 (baseline 재확인)
| 갈래 | 출처 | 성격 |
|---|---|---|
| **클린 RSS** | aitimes · AWS ML Blog · OpenAI* · DeepMind | feedparser, 무인증·무스키마 → plain `http_request`/`rss` 도구로 충분(결정론) |
| **깨지기 쉬운 페치** | **OpenAI**=Cloudflare 봇 챌린지(403, 서버 UA 차단) · **Anthropic**=공식 RSS 없음 → HTML 스크래핑(구조변경 취약) | `rss.py`=HTML 불가 → *적응(adaptation)* 필요 |

→ 리트리벌은 *한 가지 일*이 아니라 **두 가지**다. 어떤 리트리벌 레이어든 가치를 증명해야 하는 곳은 *깨지기 쉬운 절반*이다.

## 2. AgentCore Gateway가 *실제로* 하는 일 (1차 자료 확인 — GA)
| 항목 | 확인된 사실 | 출처 |
|---|---|---|
| 정체 | 관리형 **MCP 서버 엔드포인트**, transport=**streamable HTTP**(`tools/call` 시 SSE). API/Lambda/Smithy → MCP 도구로 변환 | [gateway.html](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway.html), [runtime-mcp-protocol-contract.html](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-mcp-protocol-contract.html) |
| **타깃 종류(핵심)** | **MCP 타깃**(OpenAPI 3.x/Smithy/Lambda) · **HTTP 타깃**(passthrough/Runtime) · **Inference 타깃**. OpenAPI는 `operationId`+정적 server URL 요구 | [gateway-supported-targets.html](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-supported-targets.html), [gateway-schema-openapi.html](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-schema-openapi.html) |
| **공개 RSS/HTML 직접 등록?** | **불가.** raw GET은 1급 타깃 아님 → OpenAPI/Lambda 래퍼 필요. **"HTTP passthrough" 타깃조차 *알려진* 엔드포인트로의 투명 프록시(path 기반)일 뿐 — tool listing·semantic search 미지원** → 에이전트가 부를 *명명된 도구*를 노출하지 않음 | [gateway-target-http-passthrough.html](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-target-http-passthrough.html) |
| inbound auth(에이전트→GW) | **필수.** JWT/OAuth(OIDC, Cognito 기본) · IAM SigV4 · `AUTHENTICATE_ONLY`/`NONE`. bearer 토큰 | [gateway-inbound-auth.html](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-inbound-auth.html) |
| outbound auth(GW→타깃) | per-target 자격 주입 via **AgentCore Identity 볼트**: API key · OAuth2(2/3-legged·OBO·passthrough) · IAM SigV4 → *인증 뉴스 API의 실가치* | [gateway-outbound-auth.html](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-outbound-auth.html) |
| semantic tool search | 빌트인(opt-in), `x_amz_bedrock_agentcore_search` 도구. 수백~수천 도구 규모에서 의미(5~7개엔 무의미) | [gateway-using-mcp-semantic-search.html](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-using-mcp-semantic-search.html) |
| Gateway vs Runtime | **상보적**(Runtime=에이전트 *호스팅/실행*, Gateway=에이전트에 *도구 제공*). 대체재 아님 | [agents-tools-runtime.html](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/agents-tools-runtime.html) |
| 가격(global rate card, MEDIUM) | ~$0.005/1k API invocations · ~$0.025/1k search · ~$0.02/100 tools·월 indexing · VPC egress ~$0.006/GB. 리전 목록 미확인 → 배포 전 확인 | [pricing](https://aws.amazon.com/bedrock/agentcore/pricing/) |

## 3. ★ 핵심 재프레임 — Gateway는 *웹 페처*가 아니라 *API→MCP 어댑터*
공개 RSS/HTML을 Gateway 도구로 쓰려면 반드시 **Lambda(`fetch_feed`/`fetch_article`)나 OpenAPI 스키마로 감싸야** 한다. 즉 "Gateway over RSS/HTML" = *Lambda/OpenAPI-백드 MCP 도구* — **Gateway 자신이 페치하는 게 아니다.** passthrough 타깃조차 명명 도구를 안 주므로 빠져나갈 길이 없다. → 무인증 공개 GET을 이렇게 감싸면 *강제 inbound auth + per-call 비용 + 셋업*만 추가되고 `WebFetch`/plain HTTP 대비 이득 0.

## 4. "headless Claude Code와 어울리기" 메커니즘 (확인)
- Claude Code = **MCP 클라이언트.** `.mcp.json`/`--mcp-config` 에 `type:"http"`(streamable-http) 서버 + `headers:{Authorization:"Bearer <token>"}` 등록 → `claude -p` 가 `fetch_*`/`search_news` 를 도구로 호출. [code.claude.com/docs/en/mcp](https://code.claude.com/docs/en/mcp)
- **headless 함정 2개:**
  1. 대화형 OAuth(`/mcp` 브라우저 인증)는 **no-TTY 에서 불가** → **JWT를 사전 발급해 정적 헤더로 주입**(client-credentials grant, AgentCore Identity).
  2. streamable-HTTP `Accept` 헤더 **406 버그** 보고 있음([claude-agent-sdk #202](https://github.com/anthropics/claude-agent-sdk-typescript/issues/202)) → 사용 CLI 버전에서 실제 검증.

## 5. ★ 핵심 긴장 — decorrelation (4-컴포넌트 분석 불변식과 직결)
verify-before-publish는 certifier가 author의 주장을 **source 구절**에 대해 채점한다. 그런데 Gateway 도구를 **author가 자율로 불러 *자기 source를 직접 페치*하면, author가 채점당할 증거를 스스로 통제**하게 되어 grounding decorrelation이 약해진다("증거를 쓴 사람이 증거도 만든" 꼴).

**해법 — 권위 페치는 fabric 소유 + content-addressed source-of-record:**

```
        ┌─────────────────────────────────────────────┐
        │  fabric (Strands/gate)  — 권위 페치 1회        │
        │  fetch_article(url) → 정본 텍스트              │
        │  → sha256(정본) = source_id  → ledger 기록     │
        └───────────────┬─────────────────────────────┘
                        │  같은 동결·해시된 source
            ┌───────────┴───────────┐
            ▼                       ▼
   author (Claude Code)     certifier (Codex)
   동결본에서 *요약만*       *같은 해시* source-of-record로 검증
   (자기 권위 사본 페치 X)   (author·certifier 동일 바이트 보장)
```

- author의 추가 페치(DEPTH=deep, 링크 따라가기)는 **비권위 enrichment 로만** — certifier의 source-of-record는 *항상* fabric의 첫 정본 해시.
- **certifier 는 도구 없음(tool-starved) 유지** — Gateway 공유 도구 평면은 fabric+author 용, certifier 엔 절대 안 줌(최소 envelope 불변식, [`four-component-analysis.md`](four-component-analysis.md) §6).
- **content-addressing = 안티치트:** certifier가 `sha256(정본)` 에 대해 검증하므로 author가 더 편한 source로 바꿔치기 불가 — 두 하니스가 *바이트 단위로 같은 source* 를 봤음이 증명된다.

## 6. 적응(fragile) 페치 배치
- 정본 페치 = **결정론 Lambda 도구**(필요 시 헤드리스 브라우저/헤더 회전으로 OpenAI Cloudflare·Anthropic HTML 흡수), **fabric 소유**.
- Claude Code 적응(model-driven)은 *그 도구가 깨질 때의 **repair 폴백*** 으로만 scoped → 산출물은 **fabric이 재-동결/해시** 해야 certifier의 source-of-record가 된다(author가 *나중에 grade받을 증거* 의 유일·미검증 출처가 되지 않게). [`four-component-analysis.md`](four-component-analysis.md) 의 "적응은 깨지기 쉬운 부분에만 scoped" 원칙과 일치.

## 7. 판정 — v1 vs v2
| | 쓸 것 | 이유 |
|---|---|---|
| **v1**(공개 5~7 출처, 무인증) | **Gateway 불필요.** fabric 소유 plain `http_request`/`rss`(또는 `WebFetch`) + 깨지는 출처용 scoped Claude Code repair | 공개 GET을 OpenAPI-wrap/Lambda-behind-Gateway 로 감싸면 순수 indirection + 강제 inbound auth + per-call 비용 |
| **v2+**(Gateway가 값을 범) | **Gateway 채택** | ① 인증/유료 뉴스 API(outbound auth=AgentCore Identity 볼트 실가치) · ② **두 하니스(+미래 에이전트)가 공유하는 감사·버전드 리트리벌 도구 카탈로그**(이 설계엔 *가장 그럴듯한* 정당화) · ③ 중앙 auth/관측성/guardrail(provenance — verify-before-publish 감사 테마와 정렬) · ④ 도구 많을 때 semantic search |

## 8. getting-along 한 줄 요약
**Gateway = 관리형 MCP 도구서버 · Claude Code = MCP 클라이언트.** 단 *권위* 리트리벌은 **fabric(content-addressed source-of-record)** 이 소유하고, author의 Gateway 접근은 **비권위 enrichment** 로 scoped, **certifier는 tool-starved.** 이렇게 두면 Gateway를 (v2에서) 도입해도 verify-before-publish의 decorrelation이 깨지지 않는다.

## ★ 확장 — retrieval을 'identical channel'로 (content-addressed Gateway 채널)
> v1.5 업그레이드 아이디어: §5의 content-addressed source-of-record를 *규약(convention)* 에서 *메커니즘(plumbing)* 으로 끌어올린다.

- **무엇:** Gateway에 단일 MCP 타깃을 두고 연산을 분리 — `fetch_and_freeze(url) → {source_id=sha256, text}`(권위·동결·1회) · `get_source(source_id) → frozen text`(read-only) · `search(query) → candidates`(발견·비권위). backing store(S3/DDB) = **durable ledger**(4-컴포넌트 orphan #2와 동일). fragile URL(OpenAI Cloudflare·Anthropic HTML)은 **Browser Tool** 경유.
- **scope(principal별):** `fabric/gate = {fetch_and_freeze, get_source, search}` · `author = {get_source}`(읽기만) · `certifier = {}`(도구 없음 — envelope-fed). Gateway inbound auth(Cognito 스코프)로 강제.
- **왜 사는가:**
  - ① **바이트 동일성이 *구성적*으로 보장** — 채널이 동결 스냅샷만 주므로 같은 `source_id`면 author 요약 바이트 = certifier 검증 바이트. anti-cheat가 *규약*(모두 같은 해시 신뢰)이 아니라 *배관*(채널이 같은 것만 줄 수 있음).
  - ② **★ 정규화 드리프트(normalization drift) 제거** — fabric·author가 공백/인코딩/보일러플레이트를 다르게 처리하면 NLI가 *author가 본 것과 다른 텍스트* 를 검사해 위양성/위음성 발생. 단일 채널 = 단일 정규화 → certifier가 author가 본 *바로 그 바이트* 를 검사(게이트 정확성 직결).
  - ③ **감사 경계 1개** — 모든 페치가 로깅되는 MCP 호출(provenance), backing store = ledger.
- **가드레일(불변식 *강화*):**
  - **certifier는 채널 미접근 — envelope-fed 유지.** gate가 `get_source`로 읽어 envelope `source_excerpt`에 담음; certifier는 채널을 안 봄(최소 envelope 누수 방지).
  - **originate vs read 구분.** author의 *동결본 read*(`get_source`)는 허용(증거를 *읽음*), *권위 페치 originate*(`fetch_and_freeze`)는 fabric만(증거를 *만들지* 못함).
  - **discovery ≠ source-of-record.** `search`(Web Search snippet)는 발견에만; 동결 source-of-record는 항상 `fetch_and_freeze` full-text(snippet이 증거로 새지 않게).
- **단계:** content-addressed *규율*은 **v1**(plain `source_store`, sha256 키 — Gateway 불필요). *채널화(Gateway)* 는 **v1.5** — 단일 정규화·감사·공유 surface·scope 강제를 살 때. **us-east-1 전용 + per-call 비용**이라 v1 5~7 고정 출처엔 plain store가 쌈 → 리전/비용이 타이밍 결정.

---

## 9. 참조 (References)
- AgentCore Gateway 문서: [gateway.html](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway.html) · [supported-targets](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-supported-targets.html) · [openapi schema](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-schema-openapi.html) · [http-passthrough](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-target-http-passthrough.html) · [inbound-auth](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-inbound-auth.html) · [outbound-auth](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-outbound-auth.html) · [semantic-search](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-using-mcp-semantic-search.html) · [agents-tools-runtime](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/agents-tools-runtime.html) · [pricing](https://aws.amazon.com/bedrock/agentcore/pricing/)
- Claude Code MCP 클라이언트: [code.claude.com/docs/en/mcp](https://code.claude.com/docs/en/mcp) · [claude-agent-sdk #202(406 버그)](https://github.com/anthropics/claude-agent-sdk-typescript/issues/202)
- 리트리벌 baseline: [`../research/briefing-news-agent-spec-research.md`](../research/briefing-news-agent-spec-research.md) §3.1
