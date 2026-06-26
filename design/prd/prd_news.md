# 뉴스 브리핑 에이전트 — 제품 요구사항 (PRD)

> 제품 요구사항(무엇/왜/누구/범위/성공기준/차별점)만 다룬다. 스택·아키텍처·스키마·코드 등 *구현(how)은 후속 별도 단계*에서 다룬다(이 문서 범위 아님).
> 반영한 논의: [`research-what-to-build.md`](../research/research-what-to-build.md) · [`news-agent-differentiation.md`](../architecture/news-agent-differentiation.md) · [`personalized-morning-briefing-research.md`](../research/personalized-morning-briefing-research.md) · [`briefing-news-agent-spec-research.md`](../research/briefing-news-agent-spec-research.md) · [`harness-to-verify-before-publish-mapping.md`](../architecture/harness-to-verify-before-publish-mapping.md) · [`value-roadmap.md`](../architecture/value-roadmap.md), 그리고 Bedrock에서 실제로 돌린 2-모델(Sonnet author + gpt-oss-120b certifier) 검증 데모(환각 3/3 차단).

## 0. 한 줄 정의
**Claude(작성자) + Codex(독립 인증자) 듀얼 하니스 위에서 동작하는, 커스터마이즈 가능한 개인용 *매일 아침 뉴스 브리핑* — 차별점은 "검증 후 발행(verify-before-publish)" 신뢰 게이트.**

## 1. 목표 (Goal)
- Claude Code와 Codex를 결합해 *매일 쓰는* 실용 AI 애플리케이션을 만든다.
- 단순 요약기가 아니라, **요약을 쓴 모델이 그 요약을 스스로 채점하지 못한다**는 직무 분리(separation of duties)를 제품의 본질로 삼는다 — 이것이 "왜 하니스가 둘이어야 하는가"의 답.

## 2. 문제 (Why)
- **과부하·회피:** 성인 40%가 뉴스 회피(과부하 31%·무력감 20%, Reuters DNR 2025). → 짧고 차분하고 *끝나는* 브리핑.
- **AI 요약 과신:** AI 뉴스 응답 45%에 유의미한 결함·31% 출처/귀속 문제(EBU/BBC 2025); 프론티어 모델도 요약 환각 10%대(Vectara). "정확하다"는 *주장*으로는 차별화 불가 → **검증을 눈에 보이게**.
- **단일 모델 한계:** 90% 충실해도 나머지를 *확신*하며 내보내고, 같은 weights가 그 오류를 그럴듯하다고 평가해 스스로 못 잡는다(correlated error) → 비상관 두 번째 검증 필요.

## 3. 제품 정의 (What)
커스터마이즈 가능한 **개인용(personal-first)** 뉴스 브리핑 에이전트. 커스터마이즈 표면은 **Skill로 정의**. *v1 MVP 노브 = TYPE · DEPTH · PROFILE* (BRAND는 v1 고정):
- **TYPE(뉴스 종류):** AI News / Stock News 등 — 출처·어휘 결정.
- **DEPTH(요약 정도):** 제목+링크만 / +간결 요약 / +"What is Important". **v1 기본값 = 풀(제목 + 요약 + What is Important + 신뢰 칩).** 같은 검증을 다른 밀도로 렌더.
- **PROFILE(개인화 프로필):** *명시적* 1~3줄 — `역할`(예: AWS·AI 에이전트 실무자) · `관심 기술/토픽`(LLM/Bedrock/AgentCore/Strands) · (선택)`가벼운 벤더`. "What is Important"는 이 프로필에 대해 작성되고, 그 *정량/인과 주장*을 인증자가 검증. (보유종목 등 금융 *노출(exposure)* 신호는 Stock 타입 확장 시.)
- **BRAND(편집 보이스):** v1은 **고정 기본 보이스**(차분·anti-doomscroll·한국어친화). 설정 노브화는 후속.

## 4. 사용자 & 사용 방식 (Who & How)
- **대상:** 본인(매일 아침 AI 뉴스 빠른 확인). 유용성 확정 후 타인 권유.
- **전달:** 매일 새벽 *고정 시각*(예: KST 07:00)에 **이메일 1통**. 고정 시각 = 습관(리텐션)의 핵심.
- **이메일 — 기사별 카드:**
  - **제목 (Title)**
  - **URL (원문 링크)**
  - **간결 요약 (1문단, 3~5문장)**
  - **What is Important (왜 중요한가, 간결)** — 독자의 역할·관심에 묶인 영향 한 줄.
  - **신뢰 칩:** `VERIFIED` / `DEMOTED-TO-UNCERTAIN` — 이 카드가 검증을 통과했는지 가시화(show your work).
- **분량·톤:** 기사 5~10개, Smart Brevity(스캔 가능·완결감), 차분.

## 5. 핵심 차별점 (Verify-before-publish)
- **Claude = 작성자:** 클러스터링·요약·"What is Important" 작성.
- **Codex = 인증자 (`codex exec` on Bedrock):** 작성자 추론을 *보지 않고*(최소 컨텍스트) 발행 *전에* 독립 재도출. **v1 게이트 = (a) 함의(NLI) 요약↔원문 + (b) 숫자/날짜/% 산술 재도출**, *이미 가져온 원문 텍스트에만* 적용(신규 fetch 없음 → 법적 리스크 회피). (c) liveness/superseded(정정을 잡는 *재페치* grounding)는 **v2**.
- **출력 3종·실패 정책:** VERIFIED(발행) / **DEMOTED → "(미확인)" 라벨로 *남김*** / **BLOCKED → 발행 제외.** *조용한 드롭 금지(거짓 안심 방지).*
- **근거:** Harness 블로그가 코드 협업에서 실증(46:1, 다른 계열이 같은 계열 못 본 결함 포착) → 본 프로젝트는 *사실 콘텐츠*로 옮기고 narration 차단으로 강화. **라이브 데모에서 환각 3/3 실제 차단 확인**(Anthropic 서울 기사, Bedrock 2-모델). v1 인증자 = **Codex on Bedrock**(모델: GPT-5.5 Bedrock 액세스 시 / 아니면 gpt-oss-120b — 둘 다 *다른 계열*).
- **왜 중요:** 이 게이트가 "What is Important"(추론이 섞여 가장 틀리기 쉬운 줄)를 *믿을 수 있게* 만든다. 게이트 없으면 차별점이 곧 책임.

## 6. 범위 (Scope)
**MVP 포함(v1):** 단일 사용자 · 매일 아침 이메일 · **출처 5~7개**(briefing-news-agent 5개 베이스 + 한국어 백업 1개; 영어=모델사 공식 블로그 중심; 카테고리 공백은 best-effort)+dedup · 기사별 요약+"What is Important"(PROFILE 기준)+신뢰 칩 · **검증 후 발행 게이트 = 함의+산술**(Codex on Bedrock, 가져온 원문에만; *수동 점검이 아니라 자동*) · **소형 적대적 평가셋(~20~30건)** 수용 게이트 · TYPE/DEPTH/PROFILE 커스터마이즈(BRAND는 v1 고정).

**MVP 제외 / 로드맵 parked(v2+, ref [`value-roadmap.md`](../architecture/value-roadmap.md)):** **Tap-to-Source(영수증) — 선택됨, 다음 슬라이스** · grounding 재페치/liveness·superseded(정정 추적) · Diff-Since-Last · Withheld-and-Why · Cross-Source Reconcile · Self-Calibration · Prediction Ledger · Verified Q&A · 오디오/멀티채널 · BRAND 노브화 · 다중 수신자/구독/인증/실시간 push.

## 7. 성공 기준 (MVP 합격)
1. **정시 발송** — 고정 시각 ±15분, 7일 연속 무중단.
2. **분량·포맷** — 매 발송 5~10 기사, §4 카드 포맷 준수.
3. **사실 부합(자동)** — 요약·"What is Important"의 정량/인과 주장이 인증자(Codex) 게이트 통과. *수동 spot-check가 아니라* 게이트가 책임. 측정 = 라벨된 **소형 적대적 평가셋 ~20~30건**의 **catch-rate**(게이트가 rubber-stamp 아님 증명).
4. **출처 다양성** — TYPE에 맞는 출처에서 다양하게(특정 출처 강제는 입력 존재 *조건부*로).
5. **manageability** — 짧고 완결적(읽기 ~10분 내), 차분.

## 8. 제품 차원 제약·리스크
- **뉴스 피로 설계:** de-clickbait·차분·"오늘은 이게 다"로 회피 동인 완화.
- **인증자 독립성:** certifier는 *다른 계열* + *최소 컨텍스트*라야 진짜 비상관(같은 모델 2-pass=가짜 독립). **v1 인증자 = Codex(`codex exec` on Bedrock)** — 블로그의 진짜 두 번째 하니스. 모델 = GPT-5.5(Bedrock 모델 액세스 시) 또는 gpt-oss-120b. (현재 이 계정엔 gpt-oss만 켜져 있어, GPT-5.5 사용엔 Bedrock 액세스 요청이 필요할 수 있음.)
- **합법적 수집 태세:** robots/ToS/TDM 존중 · 사실-only(verbatim 영속 저장 금지) · 변형적 출처 링크(Bartz/Ross 류 회피).
- **출처 드리프트:** 피드 URL·구조 변동 가정(주기 검증·폴백) — 스펙 리뷰가 OpenAI/DeepMind 피드 변경 이미 적발.

## 9. 참조 (References)
- Harness Engineering 블로그(듀얼 하니스 on Bedrock): https://aws.amazon.com/ko/blogs/tech/codex-claudecode-harness/
- briefing-news-agent(참조 구현·Skill 패턴): https://github.com/gonsoomoon-ml/briefing-news-agent
- 본 저장소 design/ 문서 6종(위 머리말).

## 10. 언어 규칙
- 문서·산출물은 한국어 우선(기술 용어 영어 병기); 코드 식별자/로그는 영어(이식성).
