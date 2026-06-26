# briefing-news-agent MVP 스펙 — 리서치 종합 보고서 (Research Synthesis)

> **대상 문서:** `gonsoomoon-ml/briefing-news-agent` 의 `design/specs/0001-mvp-spec.md` (v0.1, 2026-05-05 작성)
> **리서치 일자(Research date):** 2026-06-24
> **방법(Method):** 8개 에이전트 워크플로우 — 4개 적대적 웹 검증(출처/스케줄러/Strands·Bedrock/SES) + 2개 분석(MVP 건전성 / 듀얼 하니스 연결) + 종합 + 완전성 비평. 모델 id 검증은 `claude-api` 레퍼런스로 교차 확인.
> **인용 정책:** 모든 외부 주장에 출처 URL 보존. `blocker`/`high` 발견을 전면에 명시.

---

## 1. 요약 (Executive Summary)

**스펙이 무엇인가:** `briefing-news-agent` MVP 스펙 v0.1(문서 0001)은 **단일 Strands 에이전트**가 5개 RSS/HTML 출처를 24시간 윈도우(window)로 수집·한국어 요약해, 매일 **KST 07:00**에 AWS SES로 이메일을 발송하는 **개인용(personal-first)** 뉴스 브리핑 시스템이다. 인프라는 **EventBridge Scheduler universal target**이 Lambda 없이 **AgentCore Runtime**을 직접 invoke하는 2단계 구조다.

**전체 판정: 재작업 필요 (Rework Required).**
- 인프라 골격(EventBridge Scheduler → AgentCore, IAM, cron 시각 매핑)과 기술 스택(Strands `@tool`, AgentCore `@app.entrypoint`, RSS 도구 재사용)의 핵심 주장은 **대체로 1차 자료로 확인(CONFIRMED)**되어 견고하다.
- 그러나 **제품 로직(product logic)이 심각하게 과소명세(under-specified)**되어 있고, 데이터 출처 절반이 깨졌으며(URL 변경/봇 차단), 무엇보다 **스펙 0001이 프로젝트(이 저장소) 자신의 설계 결정과 정면으로 모순(blocker)**된다.

**가장 중요한 3가지 발견 (most critical):**

1. **[BLOCKER] 스펙 0001은 이 저장소(`Agent-Claude-Code-With-Codex`)의 `design/`가 '제외 집합(2.00점)'으로 분류한 바로 그 제품이다.** `research-what-to-build.md`는 뉴스 브리핑 단독을 "Skill + WebSearch/WebFetch + 스케줄러가 약 90%를 이미 제공"한다며 baseline yardstick로 낙인찍었고, `news-agent-differentiation.md`가 본질로 규정한 차별화 축(Claude/Codex **검증 후 발행(verify-before-publish) 게이트**, 영속 원장)이 0001에는 전부 빠져 있다. MEMORY.md도 이 방향을 "PAUSED, 다른 각도로 재개"로 기록했다. 스펙은 자신이 어느 결정을 따르는지 밝히지 않는다 — **이 결정 없이는 다른 모든 발견의 우선순위가 정해지지 않는다.**

2. **[HIGH] 합격 게이트 2개(#3 사실 부합, #4 출처 다양성)가 현재 형태로 측정 불가하거나 달성 불가능하다.** #3은 "수동 spot check"라 7일 무중단 **자동** 판정(#1)과 충돌하고, #4는 에이전트가 통제할 수 없는 외부 발행 여부(aitimes·Anthropic 매일 발행)에 의존하는 결정적 결함(unsatisfiable acceptance criterion)이다. 이 두 가지는 이 저장소의 듀얼 하니스 논제(verify-before-publish 자동화)와 정확히 맞물린다(§5).

3. **[HIGH] 5개 출처 중 2개(OpenAI, DeepMind)의 RSS URL이 스펙대로는 작동하지 않으며, 모델 id도 bare 형태로는 호출 실패 위험이 크다.** OpenAI는 Cloudflare 봇 챌린지로 403, DeepMind는 도메인·경로 모두 이전됨. Bedrock 모델 id `anthropic.claude-sonnet-4-6`는 대부분 리전에서 In-Region 호출이 미지원이라 cross-region inference profile prefix(`us.`/`global.`)가 필요하다. 스펙 그대로 배포하면 매일 실패한다.

---

## 2. 스펙 개요 (Spec Overview)

### briefing-news-agent가 하는 일

| 항목 | 내용 |
|---|---|
| **수집(ingest)** | 5개 출처에서 24시간 윈도우 내 신규 기사 수집 (RSS 4개 + HTML 스크래핑 1개) |
| **요약(summarize)** | Strands 단일 에이전트 + Bedrock `anthropic.claude-sonnet-4-6`로 한국어 요약, 5~10개 항목 |
| **렌더·발송(render/send)** | AWS SES로 단일 수신자(gonsoomoon@gmail.com)에게 이메일 1건 발송 |
| **트리거(trigger)** | EventBridge Scheduler universal target → AgentCore Runtime `InvokeAgentRuntime` 직접 invoke (Lambda 제거, 2단계) |
| **카테고리** | LLM / Infra / Biz·자금조달M&A / AgentCore·Strands main news |
| **발송 시각** | 매일 KST 07:00 (±15분 SLA) |

### 의존성 체인 (BRD → research → ADR → spec)

`briefing-news-agent` 저장소의 상위 결정 문서들이 0001 스펙의 맥락을 규정한다:
- **BRD** (`design/biz_requirement.md`): "매일 아침 AI 뉴스를 이메일로 요약" — Bedrock + Strands + AgentCore 스택 명시. 4단계(탐색/리서치→계획→구현→검증) Spec-Driven, 점진 확장.
- **research 0001** (`spec-driven-development.md`): Superpowers를 척추로, EARS·ADR 표기 채택.
- **research 0002** (`strands-agentcore-news-pattern.md`): `developer-briefing-agent` 답습, 5개 출처, SES sandbox, EventBridge universal target 직접 호출.
- **ADR 0001**: `gonsoomoon-ml/developer-briefing-agent`의 스택·패턴 답습 결정.
- **spec 0001** (MVP v0.1): 위 결정을 종합한 합격 기준 4개.

> **참고 — 두 저장소의 관계:** 이 보고서는 *이* 저장소(`Agent-Claude-Code-With-Codex`, 듀얼 하니스 verify-before-publish 논제)의 관점에서 *별개* 저장소(`briefing-news-agent`, 단일-모델 AWS 구현)의 스펙을 리서치한 것이다. §5가 둘의 결합을 다룬다.

---

## 3. 기술 주장 검증 결과 (Technical Claim Verdicts)

판정 범례: **CONFIRMED** 확인됨 / **CHANGED** 변경됨·주의 / **REFUTED** 반증됨 / **UNCERTAIN** 미입증

### 3.1 클러스터 A — 출처 (5개 RSS/HTML)

| Claim | Verdict | 영향 (Impact) | Severity | 출처 URL |
|---|---|---|---|---|
| aitimes RSS가 정상 resolve | **CONFIRMED** | 스펙 그대로 사용 가능. 유일한 한국어 출처로 정상 동작(item 50개/일, `<language>ko</language>`) | info | `https://www.aitimes.com/rss/allArticle.xml` |
| AWS ML Blog RSS가 정상 resolve | **CONFIRMED** | 스펙 그대로 사용 가능. AgentCore main news 커버에 핵심(샘플 20개 중 5개+ AgentCore 글) | info | `https://aws.amazon.com/blogs/machine-learning/feed/` |
| OpenAI blog RSS는 `openai.com/blog/rss/`에서 작동 | **CHANGED** | **스펙 URL은 HTTP 403 + `cf-mitigated: challenge`(Cloudflare 봇 챌린지)로 매일 실패.** `https://openai.com/news/rss.xml`로 교체 필요. AgentCore Runtime/Lambda의 UA로 가져올 때도 차단 가능 → 브라우저형 UA·헤더 검증 필요 | **high** | `https://openai.com/blog/rss/`, `https://openai.com/news/rss.xml` |
| DeepMind 피드는 `deepmind.com/blog/feed/basic/`에서 제공 | **CHANGED** | **도메인·경로 모두 이전됨**(deepmind.com→deepmind.google, /blog/feed/basic/→/blog/rss.xml). 현재는 리다이렉트로만 작동 → 구 도메인 폐기 시 깨짐. 정식 URL로 직접 명시 필요 | **high** | `https://deepmind.com/blog/feed/basic/`, `https://deepmind.google/blog/rss.xml` |
| Anthropic news는 공식 RSS 부재 → HTML 스크래핑 불가피 | **CONFIRMED** | 스크래핑 결정 유효(후보 URL 7종 모두 404, WebSearch 확인). 단 HTML 구조 변경 시 파서 깨짐 → '구조 변경 모니터링' 안전장치 명시 권장. 비공식 커뮤니티 RSS/RSSHub를 백업으로 고려 가능 | medium | `https://www.anthropic.com/news` |
| 이 5개로 모든 카테고리를 매일 채울 수 있다 | **REFUTED** | **(a) Strands 전용 뉴스**: AWS ML Blog 샘플에 Strands 단독 글 부재(주로 strands-agents GitHub). **(b) 자금조달/M&A**: 전문 펀딩/M&A 소스(TechCrunch 등) 없음. 성공기준 #2(분량)·#4(다양성)에 직접 위험, '비어 있는 날' 발생 가능 | **high** | `https://aws.amazon.com/blogs/machine-learning/feed/`, `https://www.aitimes.com/rss/allArticle.xml` |
| 한국어를 aitimes 한 곳에 의존하는 것은 수용 가능 | **REFUTED** | 5개 중 한국어 1개(aitimes)뿐. 성공기준 #4가 'aitimes 매일 ≥1개'를 명시 → **single point of failure.** 다운 시 즉시 fail. 한국어 백업 0개(ZDNet은 404로 제외됨) | medium | `https://www.aitimes.com/rss/allArticle.xml` |

### 3.2 클러스터 B — 스케줄/트리거 (EventBridge Scheduler → AgentCore)

| Claim | Verdict | 영향 (Impact) | Severity | 출처 URL |
|---|---|---|---|---|
| universal target ARN 형식 `arn:aws:scheduler:::aws-sdk:bedrock-agentcore:invokeAgentRuntime`이 올바름 | **UNCERTAIN** | **형식·케이싱은 타당하나(invoke는 차단 목록에 없음), 'bedrock-agentcore'를 universal target으로 호출한 1차 예제·지원 확인이 없음.** 2024-06 'Bedrock universal target' 공지는 AgentCore 출시 이전(=InvokeModel 지칭). 미지원 시 핵심 아키텍처가 무너짐 → 배포 전 실제 발화 검증, fallback으로 Scheduler→Lambda→`invoke_agent_runtime` 준비(비동기로 타임아웃도 해결) | **high** | `https://docs.aws.amazon.com/scheduler/latest/UserGuide/managing-targets-universal.html`, `https://docs.aws.amazon.com/bedrock-agentcore/latest/APIReference/API_InvokeAgentRuntime.html` |
| `cron(0 22 * * ? *)` UTC == 다음날 KST 07:00 [^cron] | **CONFIRMED** | 시각 매핑 정확(KST=UTC+9, 한국 DST 미관측). 구현 영향 없음 | info | `https://docs.aws.amazon.com/scheduler/latest/UserGuide/schedule-types.html` |
| timezone을 cron 문자열에 붙여 `cron(0 7 * * ? *) Asia/Seoul`로 지정 [^cron] | **REFUTED** | **timezone은 cron 문자열 일부가 아니라 별도 파라미터** `ScheduleExpressionTimezone`. 스펙대로 IaC에 넣으면 cron 파싱 오류로 스케줄 생성 실패. `schedule-expression='cron(0 7 * * ? *)'` + `schedule-expression-timezone='Asia/Seoul'`로 분리 | medium | `https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-scheduler-schedule.html` |
| ±15분 발송 SLA 충족 | **UNCERTAIN** | 기본 정밀도는 60초. ±15분 분산은 `FlexibleTimeWindow` 명시 필요(스펙 미명시). 또한 ±15분은 '발화 시각'일 뿐 '수신' 시각은 실행시간+SES 지연 추가. 측정 대상(발화 vs 수신) 정의 필요 | medium | `https://docs.aws.amazon.com/scheduler/latest/APIReference/API_Target.html` |
| payload `{AgentRuntimeArn, RuntimeSessionId, Payload(base64)}` 형태 | **CHANGED** | **실제 SDK 파라미터는 PascalCase 아님**: `agentRuntimeArn`(URI), `runtimeSessionId`(헤더), `payload`(binary blob). RuntimeSessionId가 'payload JSON 필드'가 아니라 헤더 매핑 파라미터라는 점이 스펙과 어긋남. universal target Input JSON 키를 SDK shape 그대로 맞춰야 발화 성공. 실배포 전 1회 수동 발화로 검증 | **high** | `https://docs.aws.amazon.com/bedrock-agentcore/latest/APIReference/API_InvokeAgentRuntime.html`, `https://docs.aws.amazon.com/boto3/latest/reference/services/bedrock-agentcore/client/invoke_agent_runtime.html` |
| RuntimeSessionId로 daily uuid 사용 (최소 33자 제약?) | **CONFIRMED** | 제약은 최소 33자·최대 256자. 표준 UUID(36자)는 충족. **주의: 'YYYY-MM-DD'(10자) 같은 짧은 ID를 세션ID로 직접 쓰면 ValidationException** | low | `https://docs.aws.amazon.com/bedrock-agentcore/latest/APIReference/API_InvokeAgentRuntime.html` |
| fire-and-forget — 장시간 실행 타임아웃이 관리됨 | **UNCERTAIN** | **InvokeAgentRuntime은 동기·스트리밍 API.** 뉴스 수집+LLM 요약이 길면 Scheduler 동기 응답 창 초과 위험, 스트리밍/바이너리 응답 처리 미문서화. (DLQ+RetryPolicy 주장은 타당하나 '지수 백오프'는 문서 미명시) → Scheduler→Lambda(비동기 Event) 1단계 추가 권장 | **high** | `https://docs.aws.amazon.com/scheduler/latest/UserGuide/managing-targets.html` |
| IAM 액션 `bedrock-agentcore:InvokeAgentRuntime` + `scheduler.amazonaws.com` 신뢰 | **CONFIRMED** | 액션명·신뢰주체 정확. 단 Resource에 runtime + runtime-endpoint ARN 2종 포함, condition으로 SourceArn/SourceAccount(confused-deputy 방지) 추가 권장 | info | `https://docs.aws.amazon.com/service-authorization/latest/reference/list_amazonbedrockagentcore.html` |

[^cron]: cron 행은 **층위가 다른 두 판정**이다 — 시각 *의미*("UTC 22:00 = KST 07:00")는 **CONFIRMED**(산술적으로 정확)이고, 표기 *방식*("cron 문자열 안에 `Asia/Seoul`을 넣는다")은 **REFUTED**(timezone은 별도 `ScheduleExpressionTimezone` 파라미터). 즉 의도는 맞고 표기만 틀렸다.

### 3.3 클러스터 C — 기술 스택 (Strands / Bedrock / AgentCore)

| Claim | Verdict | 영향 (Impact) | Severity | 출처 URL |
|---|---|---|---|---|
| Bedrock 모델 id `anthropic.claude-sonnet-4-6`가 유효 | **CHANGED** | **문자열 자체는 유효한 base id(Sonnet 4.6, 2026-02-17 출시)이나, us-east-1 등 대부분 리전에서 In-Region=No.** Strands `BedrockModel`은 **레거시 `bedrock-runtime`(Converse/InvokeModel) 경로**를 쓰므로 bare id로 호출 시 ValidationException 위험 → `us.anthropic.claude-sonnet-4-6` 또는 `global.anthropic.claude-sonnet-4-6` **inference profile** 필요(global이 ~10% 저렴). 리전/profile 요건 명문화 + 가용성 게이트 추가 [^bedrock] | **high** | `https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-sonnet-4-6.html`, `https://docs.aws.amazon.com/bedrock/latest/userguide/global-cross-region-inference.html`, `https://strandsagents.com/docs/user-guide/concepts/model-providers/amazon-bedrock/` |
| Strands `Agent(tools=[...])` + `@tool` 패턴 실재 | **CONFIRMED** | 패턴 정확. 영향 없음 | info | `https://strandsagents.com/docs/api/python/strands.agent.agent/` |
| AgentCore `@app.entrypoint`, local↔runtime 동일 로직, `boto3 invoke_agent_runtime` | **CONFIRMED** | 패턴 정확(8080 포트, `/invocations` POST, `/ping` GET). 영향 없음 | info | `https://dev.to/aws-heroes/strands-agents-agentcore-runtime-a-perfect-match-3a51` |
| `SlidingWindowConversationManager(window_size=20)` 실재 | **CONFIRMED** | 정확(기본값 40에서 줄인 유효 설정). 영향 없음 | info | `https://github.com/strands-agents/sdk-python/blob/main/src/strands/agent/conversation_manager/sliding_window_conversation_manager.py` |
| strands-agents/tools에 RSS 도구 실재(path-traversal fix 포함) | **CONFIRMED** | 재사용 가능, 직접 작성 불필요(8개 액션, feedparser 기반). 단 24h 윈도우 필터링은 에이전트/프롬프트 레벨 처리 필요 | info | `https://github.com/strands-agents/tools/blob/main/src/strands_tools/rss.py` |
| Anthropic 스크래핑에 strands RSS 도구 활용 가능 | **REFUTED** | **rss.py는 RSS/XML 전용(feedparser), HTML 페이지 스크래핑 불가.** 별도 HTTP fetch + HTML 파서(http_request + BeautifulSoup, 또는 web/browser 도구) 필요 → 출처 다양성 성공기준(#4) 위협 | **high** | `https://github.com/strands-agents/tools/blob/main/src/strands_tools/rss.py` |
| Strands prompt caching이 3-layer(tools/system/messages)로 실재 | **CONFIRMED** | 메커니즘 실재. 구현 시 `cache_prompt`가 deprecated → `cache_config` 사용 권장(코드 업데이트 필요) | low | `https://docs.aws.amazon.com/bedrock/latest/userguide/prompt-caching.html` |
| Prompt Caching 3-layer로 ~52% 비용 절감 | **UNCERTAIN** | 52%는 워크로드 의존(캐시 hit율·프리픽스 크기에 좌우), 공개 1차 자료로 미검증(리포 내부 측정 추정). 마케팅성 단일 수치로 취급, 자체 측정 재검증 권장 | low | `https://docs.aws.amazon.com/bedrock/latest/userguide/prompt-caching.html` |

[^bedrock]: **Bedrock 이중 경로 주의.** 신형 Anthropic **Mantle**(Messages-API Bedrock) 클라이언트는 bare `anthropic.claude-sonnet-4-6`를 그대로 받는다. 그러나 이 프로젝트의 Strands `BedrockModel`은 **레거시 `bedrock-runtime`** 경로라서, 리전 가용성에 따라 cross-region inference profile(`us.`/`global.` prefix)이 필요하다. 따라서 model_id 검증은 *호출 경로*를 함께 명시해야 한다.

### 3.4 클러스터 D — 이메일 (AWS SES sandbox)

| Claim | Verdict | 영향 (Impact) | Severity | 출처 URL |
|---|---|---|---|---|
| sandbox에서 발신자+수신자 모두 verify 필요 | **CONFIRMED** | sandbox 기준 정확. 수신자 Gmail도 사전 verify(확인 메일 클릭) 필요 → 셋업 체크리스트에 명시 권장 | info | `https://docs.aws.amazon.com/ses/latest/dg/request-production-access.html` |
| sandbox 한도 200건/24h, 1건/초 — 1일 1건에 충분 | **CONFIRMED** | 정확(1일 1건 = 한도의 0.5%). sandbox로 MVP 운영 가능, 스펙 수정 불필요 | info | `https://docs.aws.amazon.com/ses/latest/dg/quotas.html` |
| AWS 내부 발신 시 월 62,000건 무료 → 1일 1건 완전(영구) 무료 | **REFUTED** | **이 무료 등급은 2023-08-01 폐지됨.** 현재는 출처 무관 '최초 12개월 월 3,000건'으로 대체, 이후 $0.10/1,000건. '완전/영구 무료'는 거짓 → '최초 12개월 월 3,000건 무료, 이후 극저비용(연 ~$0.04)'으로 교체. MVP 채택 결정 자체에는 영향 없음(근거만 갱신) | medium | `https://aws.amazon.com/blogs/messaging-and-targeting/amazon-simple-email-service-adds-email-delivery-analysis-features-to-revised-free-tier/`, `https://aws.amazon.com/ses/pricing/` |
| AgentCore Runtime 발신이 'AWS 내부 발신 무료'에 해당 | **REFUTED** | 전제(EC2/Beanstalk 발신 무료)가 폐지로 소멸 → 질문 자체가 무의미(출처 조건 없어짐). '호스팅 위치 덕분에 무료' 논리 불성립. SES 요금은 호스팅 무관 동일 | low | `https://aws.amazon.com/ses/pricing/` |
| gmail.com deliverability 위험 낮음 | **UNCERTAIN** | 1일 1건은 벌크 임계치(5,000/일) 아래라 차단 대상 아님. 그러나 **커스텀 도메인 없이 주소만 verify하면 SPF/DKIM/DMARC 정렬 불완전 → 스팸함 위험 실재.** 도메인 identity + Easy DKIM 권장. 첫 발송 후 도달 여부를 spot check에 포함 | medium | `https://docs.aws.amazon.com/ses/latest/dg/send-email-authentication-dmarc.html` |
| sandbox→production 전환 트리거(다중 수신자)와 소요 시간 | **CONFIRMED** | 단일 verified 수신자 MVP에는 production 전환 불필요. 전환 트리거는 '미검증/임의 수신자 발송', 리드타임 ~24시간. 백로그에 기록 권장 | info | `https://docs.aws.amazon.com/ses/latest/dg/request-production-access.html` |

---

## 4. MVP 건전성·갭 (Soundness & Gaps) — severity 순

### 🔴 BLOCKER

- **B1. 스펙 0001이 프로젝트(이 저장소) 자신의 결정과 모순.** `research-what-to-build.md`가 뉴스 브리핑 단독을 '제외 집합·2.00점'으로 분류했고, `news-agent-differentiation.md`의 차별화 축(검증 게이트·원장)이 전부 빠졌으며, MEMORY.md는 'PAUSED'로 기록. 스펙 상단에 **'의도(intent)' 절**을 추가해 해소 필요: (옵션 A) 'walking-skeleton — 차별화는 0002+에서 추가, 성공기준에서 deferred 명시', (옵션 B) baseline 폐기 후 design/ 결정(verify-before-publish 뉴스)을 따름. **이 결정 없이는 다른 모든 finding의 우선순위가 정해지지 않는다.**

### 🟠 HIGH (severity 순)

- **H1. 성공기준 #3(사실 부합)이 수동·주관 게이트라 측정 불가.** '수동 spot check'는 비결정론적·비반복적이며 통과 임계값 부재 → #1(7일 자동 무중단)과 충돌. 자동 entailment 채점(NLI/LLM-judge with rubric) 또는 30~50건 라벨 회귀셋으로 객관화 필요. design/ 문서가 이미 'adversarial eval set' 해법을 제시했으나 0001이 미채택.
- **H2. 성공기준 #4(aitimes+Anthropic 매일 ≥1)는 외부 발행에 의존 → 달성 불가능한(unsatisfiable) 수용 기준.** 두 출처의 24h 내 발행 여부는 외생 변수. EARS로 '입력이 존재할 때의 조건부 보장'으로 재서술, '발행한 날 중 포함률 ≥95%' 비율 지표로 전환, 절대적 '매일' 제거.
- **H3. dedup/신디케이션 중복 제거 로직 전무.** 5개 출처가 같은 릴리스를 동시 보도하거나 aitimes가 영어를 재보도 → '5~10개' 슬롯이 중복으로 채워져 #4·읽기 가치 동시 훼손. URL canonical화 + 제목/임베딩 유사도 클러스터링 + 'seen' 캐시 명세 필요. (design 문서가 table stakes로 규정)
- **H4. 분량 미달 폴백 부재.** 한가한 날 5개 출처 24h 합산이 5건 미만 → #2 fail. 윈도우 확장(24h→48h→72h) 또는 'N건뿐' 라벨 발송 등 하한·상한 양방향 폴백 명세 필요.
- **H5. 출처 다운/오류 시 부분 실패 격리 미정의.** 한 피드 장애(특히 Anthropic HTML 스크래핑)가 전체 발송을 막아 #1 깨짐. per-source try/except + 타임아웃 + 재시도 + fail-soft('최소 K개 성공 시 진행') 명세 필요.
- **H6. 멱등성(idempotency) 부재.** Scheduler at-least-once 의미 + DLQ 재처리 시 같은 날 중복 발송 가능. 매번 랜덤 uuid는 중복 구분 불가. 날짜 기반 멱등 키(DynamoDB conditional put 등) + 발송 전 'sent-today' 게이트 명세 필요.
- **H7. (출처) OpenAI·DeepMind RSS URL이 스펙대로 깨짐** — §3.1. 스펙 그대로 배포 시 매일 빈 피드.
- **H8. (스택) Anthropic HTML 스크래핑에 strands RSS 도구 사용 불가** — §3.3. 별도 HTML 파서 추가 필요, 아니면 #4 위협.
- **H9. (스택) Bedrock 모델 id bare 형태 호출 실패 위험** — §3.3. Strands→bedrock-runtime 경로라 inference profile prefix 필요.
- **H10. (트리거) universal target의 bedrock-agentcore 지원 미입증 + 동기·스트리밍 API 타임아웃 위험** — §3.2. 가장 큰 미해결 인프라 리스크. 배포 전 실증 + Lambda fallback.
- **H11. (트리거) InvokeAgentRuntime payload 키 케이싱/구조가 SDK shape와 불일치** — §3.2. `AgentRuntimeArn/RuntimeSessionId/Payload`(PascalCase) vs 실제 `agentRuntimeArn`(URI)/`runtimeSessionId`(헤더)/`payload`(blob). 스펙대로 Input JSON을 구성하면 발화 실패. 실배포 전 1회 수동 발화로 정확한 스키마 확정 필요. *(H10의 타임아웃과 별개의 독립 HIGH — 표 §3.2에만 있던 항목을 우선순위 목록에 명시.)*

### 🟡 MEDIUM

- 'main news' 선별(중요도 랭킹) 로직 부재 → 출력 비결정적, 테스트 불가. 명시적 랭킹 신호(토픽 적합도+recency+출처 가중치+한국어 가산점) + '#4 보장 출처 강제 pin' 정의.
- 관측가능성·실패 알림 미정의 → '7일 무중단' 검증·운영 수단 없음(invoke 성공이나 0건 발송/이메일 실패를 못 잡음). heartbeat + 구조화 로그/메트릭 + 0건 시 알림 명세.
- 토큰/콘텐츠 길이 한도 미정의 → 대형 런칭일 컨텍스트 초과·비용 급증. per-article truncation + 입력 토큰 예산 명세.
- 비용 상한·검증되지 않은 무료 주장(월 62,000건, ~52%) ADR 없이 사실로 박힘. 실제 비용 대부분은 SES가 아니라 **LLM 추론 토큰** — 일일 토큰 예산·경보 정의.
- 검증되지 않은 전제(Anthropic RSS 부재, RSS URL 경로)가 사실로 박힘. 각 출처에 'last-verified 날짜 + 폴백' 명세, '검증된 사실' vs '미검증 가정' 구분 표기.
- EARS/ADR 추적성 부재 — 요구사항이 검증 가능한 EARS 문장이 아니고, 핵심 설계 선택(Lambda 제거, fire-and-forget, Memory 미사용)이 ADR로 기록 안 됨.
- timezone 표기 오류(`cron(...) Asia/Seoul`) — §3.2. cron 파싱 실패.
- ±15분 SLA의 측정 대상(발화 vs 수신) 미정의 + FlexibleTimeWindow 미명시 — §3.2.
- SES 무료 등급 outdated('월 62,000건' → '12개월 월 3,000건') — §3.4.
- Gmail deliverability(SPF/DKIM/DMARC) 위험 — §3.4.
- 한국어 출처 single point of failure(aitimes 단일) — §3.1.
- Anthropic HTML 구조 변경 모니터링 안전장치 부재 — §3.1.

### 🟢 LOW / INFO

- payload RuntimeSessionId 33자 하한 주의(날짜 문자열 직접 사용 금지) — §3.2.
- `cache_prompt` deprecated → `cache_config` — §3.3.
- AgentCore Runtime 발신 무료 논리 불성립(요금 호스팅 무관) — §3.4.
- SES sandbox verify 만료/계정 검토 시 #1 깨질 수 있음 — 모니터링 권장.

---

## 5. 듀얼 하니스 verify-before-publish 연결 (Dual-Harness Coupling)

### 이 저장소 논제와의 결합 분석

0001의 합격 기준 4개를 자동화 가능성으로 분류하면 **비대칭(asymmetry)**이 드러난다:

| 합격 기준 | 자동화 | 비고 |
|---|---|---|
| #1 정시 발송 (KST 07:00 ±15분) | ✅ 결정론적 | EventBridge invocation 타임스탬프 |
| #2 분량 (5~10 기사) | ✅ 결정론적 | 기사 수 카운트 |
| #4 출처 다양성 (aitimes+Anthropic 각 ≥1) | ✅ 결정론적 | 출처 set 검사 |
| **#3 사실 부합 (hallucination 없음)** | ❌ **수동 spot check** | **유일한 수동 게이트** |

즉 이 저장소의 차별화는 **정확히 #3을 자동화하는 verify-before-publish 게이트 하나에 집중**된다. 단일-모델 아키텍처의 구조적 약점: 요약을 쓴 모델이 그 요약의 사실 여부를 스스로 판정할 수 없다(no marking its own homework).

**Codex-인증자(certifier)는 #3 안에 세 갈래로 삽입된다** (`news-agent-differentiation.md` 5-2 게이트 설계와 정렬):
- **(a) 함의 게이트 (entailment/NLI)** — 가장 핵심. Claude가 쓴 각 요약 문장을 Codex가 원문 구절에 대해 문장 단위 NLI로 독립 재검사("원문이 이 문장을 entail하는가?"). 실패 시 강등/드롭.
- **(b) 숫자/날짜/% 재도출** — 정량 주장('매출 30% 증가', '$2B 펀딩')을 Codex가 결정론적 실행 코드로 재추출·재계산(byte-stable 산술 게이트). 미재현 시 드롭.
- **(c) 출처 grounding/귀속** — 인용 URL이 실제 본문을 담는지, 귀속이 정확한지 독립 재페치 검증. Anthropic HTML 스크래핑 경로는 특히 grounding 오류 위험 높음.

**핵심 원칙:** Codex는 Claude의 narration/추론을 절대 받지 않고 최소 컨텍스트(원문 구절+주장 문자열+스키마)만 받는다 — 이것이 상관 오류(correlated error)를 끊는 메커니즘이다.

> **수치 출처 주의(provenance):** 아래 본문에서 인용하는 "출처 결함 31% > 정확도 결함 20%(EBU/BBC)", "Gemini ungrounded 56%" 등은 **이 저장소의 내부 리서치 문서(`news-agent-differentiation.md`)에 기록된 값**이며, 본 리서치에서 독립적으로 재검증하지는 않았다. 게이트 설계의 *동기*로만 사용하고, 마케팅 수치로 인용 시 1차 출처 재확인 권장.

### 게이트 부재 시 구체적 실패 모드

0001은 fire-and-forget이라 발송은 모니터링되나 **내용 사실성은 발송 시점에 아무도 보지 않는다.** 수동 spot-check는 7일 자동 무중단(#1)과 정면 충돌해 사실상 검증이 일어나지 않는다. 단일 Claude Sonnet이 과신하는 지점:
1. **환각된 수치** ($2B→$20B) — single-model이 가장 쉽게 confabulate
2. **잘못된 귀속(misattribution)** — 신디케이션 중복 섞이면 위험 증폭
3. **함의 실패 요약** ('출시 검토 중'→'출시 확정')
4. **superseded/stale 사실** — 오전 보도가 오후 정정됐는데 07:00 발송본은 옛 사실
5. **번역 왜곡** — 영어→한국어 요약의 이중 언어 변환이 함의 오류 추가 표면
   → 이메일은 회수 불가(비가역). 사용자가 신뢰해 의사결정하면 피해가 실세계로.

### 결합이 둘 다 살린다 (baseline 2.0 → 차별화 4.0)

- **briefing-news-agent가 이 저장소에 주는 것:** 검증 게이트가 얹힐 **작동하는 AWS 실구현 경로**(Bedrock+Strands+AgentCore, ingest/render/SES/scheduler — table stakes 전부). 이 저장소엔 design 문서만 있고 코드가 없다(README 31바이트).
- **이 저장소가 briefing-news-agent에 주는 것:** baseline 2.0을 탈출시키는 단 하나의 빠진 조각 — **구현된(가설 아닌) verify-before-publish 게이트.** `research-what-to-build.md`가 뉴스 브리핑을 죽인 이유가 정확히 "유일한 차별점(검증 원장)이 구현이 아니라 가설에 그쳤다"는 것. 이것이 #3 수동 spot-check를 자동 직무 분리(separation of duties)로 대체한다.

이는 MEMORY의 '다른 각도에서 재개'에 정확히 해당한다.

### ⚠️ 구현 함정 1: '같은 Bedrock 모델 2-pass'는 진짜 독립성을 주지 못한다

같은 `claude-sonnet-4-6`를 두 번 호출(author/certifier)하는 것은 **가짜 독립성** — 같은 weights는 같은 맹점 공유, author가 환각한 '$20B'를 certifier도 통과(correlated error). 진짜 비상관(uncorrelated) 독립성은 셋을 동시에 요구:
1. **다른 모델 패밀리** — author=Claude(Bedrock), certifier=Codex(GPT 계열)
2. **narration 차단** — Codex에 최소 컨텍스트만(Claude의 추론을 보면 confirmation pass로 퇴화/앵커링)
3. **결정론적 코어** — 산술=샌드박스 실행 코드, 함의=pinned NLI 모델(SummaC/FENICE류). "두 모델 = 신뢰"가 아니라 **"결정론 게이트 = 신뢰"**를 헤드라인으로.

**Strands 구현 토폴로지:** Strands는 Bedrock 중심이라 Codex(GPT)를 같은 `Agent(tools=[...])` 그래프에 네이티브로 넣기 어렵다 → author는 Strands/AgentCore 안에, certifier는 그 바깥 별도 하니스에 두는 **cross-harness 경계**가 자연스럽다(이 저장소 CLAUDE.md의 'Claude=author, Codex=certifier' 직무 분리와 일치). 이것이 v1 최대 엔지니어링 리스크 → 가장 먼저 PoC.

### ⚠️ 구현 함정 2: 결합 리스크(지연/비용/복잡도/법무)와 MVP 적정 범위

- **지연(latency):** 0001은 비동기 일일 브리핑(breaking-news SLA 없음)이라 주장당 NLI + 코드 실행 추가가 일일 배치에서 수용 가능 — 이 저장소 design 문서가 명시한 완화책('breaking-news SLA 포기')이 0001에 이미 내장.
- **비용:** 개인용·1일 1건이라 절대 비용 작음. 단 prompt caching은 author 측에만 적용되니 certifier 측 별도 최적화. 게이트를 정량 주장 문장·변경된 기사에만 선택 적용.
- **법무(Bartz/Ross):** 가장 큰 잠재 리스크. **지속적 풀텍스트 재페치(grounding·정정 추적)는 Bartz/Ross 판례 이후 가장 방어하기 어려운 접근 패턴**이다(고빈도·비유입·verbatim 다중 저장). 완화: **스냅샷은 사실(facts)-only, 원문 verbatim 저장 금지**로 변형성 유지 · robots/ToS/EU Art.4(3) TDM per-user-agent 존중 · 지속 재페치는 **협력/오픈 RSS 매체로 한정**. v1 grounding은 *이미 가져온* 원문 구절에만 적용해 신규 수집 표면을 0으로.
- **복잡도:** 가장 큰 실질 리스크. 0001의 깔끔한 2단계(Lambda 제거) 가정을 cross-harness 경계가 깬다.
- **MVP 적정 범위(과욕 금지):** 6개 원장 차별화(Consequence/Diff-Since-Last/Prediction/Corrections/Q&A/Dispute)를 한꺼번에 시도하지 말 것 — 풀텍스트 의존·법적 리스크·스토리 스레드 동일성 같은 미해결 의존을 끌고 옴. **v1 = 0001의 5개 출처(ingest 비용 0) + 검증 후 발행 게이트(함의 NLI + 산술 재도출 + grounding) + verdict 칩.** 원장(영속 상태)은 게이트가 작동함을 증명한 다음 슬라이스로.

### 성공기준 #3 자동화 지점

#3을 '수동 spot check'에서 '자동 verify-before-publish 게이트'로 교체:
- 세 갈래(함의/산술/grounding)를 분리해 각각 독립 PASS/FAIL 산출
- 발행 전 모든 요약 문장이 게이트 통과(또는 DEMOTE/BLOCK) 강제
- 출력 상태 3종(**VERIFIED / DEMOTED-TO-UNCERTAIN / BLOCKED**)을 이메일에 verdict 칩으로 노출(show your work)
- 발행을 fire-and-forget → **verify-then-fire**로 전환. BLOCK된 문장은 제거하거나 라벨 강등. 게이트가 0개 BLOCK해도 손해 없고, 1개라도 BLOCK하면 spot-check가 못 잡았을 오류를 잡는다.

---

## 6. 권장 다음 단계 (Recommended Next Steps) — 우선순위 순

1. **[BLOCKER 해소] 스펙 0001 상단에 '의도(intent)' 절 추가.** baseline walking-skeleton인지 / design 결정(verify-before-publish)을 따르는지 ADR로 명시. design/ 3개 문서 + MEMORY 'PAUSED'와 정합성 기록. **이것이 다른 모든 작업의 선행 조건.**

2. **[데이터 출처 즉시 수정]** OpenAI → `https://openai.com/news/rss.xml`, DeepMind → `https://deepmind.google/blog/rss.xml`로 교체. 각 출처에 'last-verified 날짜 + 폴백' 명세. 모든 RSS fetch를 브라우저형 UA로 실제 probe 검증.

3. **[모델 id 수정]** `model_id`를 inference profile id(`us.anthropic.claude-sonnet-4-6` 또는 `global.`)로 변경. 배포 리전 가용성(In-Region/Geo/Global) 사전 확인 게이트 추가. base 답습 코드의 구형/신형 id 혼재 리뷰. (Strands=bedrock-runtime 경로 기준)

4. **[인프라 PoC]** 배포 전 (a) universal target `bedrock-agentcore:invokeAgentRuntime` 실제 발화 검증, (b) 동기·스트리밍 API 실행시간 측정. 실패 시 Scheduler→Lambda(비동기 Event)→`invoke_agent_runtime` fallback 채택. timezone을 `ScheduleExpressionTimezone`로 분리. payload 키를 SDK shape(`agentRuntimeArn`/`runtimeSessionId`/`payload`)로 1회 수동 발화 검증.

5. **[합격 기준 재정의 — EARS]** #3을 자동 게이트(함의 NLI + 산술 재도출 + grounding)로, #4를 조건부 비율 SLO(≥95%)로 재작성. 모든 요구사항을 측정 임계값 내장 EARS 문장으로.

6. **[verify-before-publish v1 슬라이스 구현]** 범위 고정 = **0001의 5개 출처(ingest 비용 0) + 검증 게이트 3갈래 + verdict 칩.** 6개 원장 차별화·영속 상태는 v2로 명시 분리. author=Claude(Strands), certifier=Codex(별도 하니스, narration 차단), 게이트 코어=결정론 코드. **cross-harness 경계를 가장 먼저 PoC.**

7. **[적대적 평가셋]** 라벨된 환각 수치/잘못된 귀속 ~30~50건 회귀셋을 v1 수용 게이트로 동시 제작. 게이트가 rubber-stamp가 아님을 '존재'가 아니라 **catch-rate(포착률)**로 보고.

8. **[운영 필수 항목 추가]** dedup(클러스터링+seen 캐시), 멱등성(날짜 기반 키 + sent-today 게이트), fail-soft(per-source 격리), 관측가능성(heartbeat+0건 알림), 토큰/비용 예산을 v0.1에 포함(YAGNI로 미룰 항목 아님).

9. **[출처·비용 보강]** Strands 전용(strands-agents releases/blog) + 펀딩/M&A 전문 피드 + 한국어 백업 1~2개 추가, 또는 '매일 모든 카테고리'를 best-effort로 완화. SES 무료 문구를 '12개월 월 3,000건'으로 갱신, Easy DKIM+SPF+DMARC를 deliverability 권장사항으로.

---

**참조 문서(이 저장소):** `design/news-agent-differentiation.md`, `design/research-what-to-build.md`, `design/prd.md`, `CLAUDE.md`, `MEMORY.md`
**참조 문서(briefing-news-agent):** `design/specs/0001-mvp-spec.md`, `design/biz_requirement.md`, `design/research/0002-strands-agentcore-news-pattern.md`, `design/decisions/0001-adopt-strands-agentcore-from-base-repo.md`

*리서치 워크플로우(8개 에이전트)로 생성. 상세 클러스터별 verdict·증거는 워크플로우 트랜스크립트에 보관.*
