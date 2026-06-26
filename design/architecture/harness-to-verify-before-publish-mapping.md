# Harness Engineering → 검증 후 발행(verify-before-publish) 매핑

> **목적:** PRD 참조 블로그(AWS "Harness Engineering")의 *코딩 하네스* 실증 결과를, 이 저장소의 *제품 신뢰 게이트*(verify-before-publish)로 **요소별 매핑**한다. "왜 두 하니스인가"의 근거가 가설이 아니라 **실측에서 왔음**을 고정하고, briefing-news-agent에 붙일 구체적 배선을 제시한다.
> **원천:** [Amazon Bedrock 위에서 Codex와 Claude Code 함께 쓰기](https://aws.amazon.com/ko/blogs/tech/codex-claudecode-harness/)
> **연결 문서:** [`news-agent-differentiation.md`](news-agent-differentiation.md)(게이트 설계) · [`research-what-to-build.md`](../research/research-what-to-build.md)(직무분리 논제) · [`briefing-news-agent-spec-research.md`](../research/briefing-news-agent-spec-research.md)(스펙 리뷰) · [`personalized-morning-briefing-research.md`](../research/personalized-morning-briefing-research.md)(제품 UX)
> **작성일:** 2026-06-25 · 언어: 한국어 우선(영어 병기)

---

## 1. 한 문장 요약 (TL;DR)

블로그는 *코드 협업*에서 **"개발자가 자기 결과물을 자기가 채점하지 않는다 + 다른 모델 계열이 같은 계열이 못 본 버그를 잡는다"** 를 48런으로 실증했다. 이 저장소의 **검증 후 발행(verify-before-publish)** 은 그 동일한 메커니즘을 *코드*에서 *사실 콘텐츠(뉴스 요약·"왜 중요한가" 주장)* 로 옮기고, **인증자에게 작성자의 추론(narration)을 숨겨 최소 컨텍스트만 주는 방식으로 한 단계 더 조인(decorrelation 강화)** 버전이다.

---

## 2. 블로그가 실증한 것 (The empirical seed)

| 블로그의 발견 | 근거(원문) |
|---|---|
| **모델보다 하네스가 견고함을 결정** | "점수보다는 모델이 아니라 하네스" — 산출물 전달·리뷰 보관·피드백 연결·계측 설계가 결과를 좌우 |
| **직무분리 = 자기 채점 금지** | "개발자가 자기 결과물을 자기가 채점하지 않는다" → 2-채점관 패널(Claude judge + Codex judge) |
| **다른 계열 교차검증이 진짜 신호** | 46번 비교 중 *유일한 신호*가, 다른 모델 계열 채점관이 같은 계열이 못 본 실제 버그를 잡은 지점 |
| **결정론적 게이트는 토큰 0** | JS 구문검사·무의존성 확인 = `validate_index`로 "게임이 아예 안 만들어진" 케이스를 토큰 한 푼 없이 정직하게 걸러냄 |
| **리뷰어는 리뷰만, 작성은 안정적 쪽** | P2(Codex 편집)는 컷오프로 불안정 → "Codex=리뷰 / Claude=편집"이 안정적 |
| **둘 다 Bedrock 한 계정** | `codex exec`(`openai.gpt-5.5`)와 `claude -p`(`global.anthropic.claude-opus-4-8`)가 같은 Bedrock(us-east-2)으로 추론 — 자격증명·리전·VPC·로깅·비용 통일 |

> **핵심:** [`research-what-to-build.md`](../research/research-what-to-build.md)의 포함 테스트("Codex를 빼면 중심 신뢰 속성이 본질적으로 깨진다")는 **추측이 아니라 이 46:1 실측에서 정당화된다.**

---

## 3. 요소별 매핑 (Element-by-element mapping)

| # | 블로그 — 코딩 하네스 | 프로젝트 — verify-before-publish 브리핑 |
|---|---|---|
| 1 | 산출물 = `index.html` 게임 코드 | 산출물 = 기사 요약 + **"왜 중요한가(why it matters)" 주장** + 델타 라벨 |
| 2 | **Claude = 단일패스 작성자**(700~800줄 한 번에) | **Claude = 작성자/author** — 클러스터링·원자적 주장 분해·요약·"왜 나에게" 작성, 영속 원장 소유 |
| 3 | **Codex = 리뷰어/도달성 버그 헌터** | **Codex = 인증자/certifier** — 함의·산술·grounding 독립 재도출, **발행 차단(BLOCK) 권한** |
| 4 | 리뷰 대상 = 코드 도달성/폴리시 결함 | 검증 대상 = 요약↔원문 **함의(NLI)** · 숫자/날짜/% **산술 재도출** · 인용 **출처 grounding/귀속** |
| 5 | 결정론적 stage gate = JS 구문검사(토큰 0) | 결정론적 게이트 = JSON 스키마 검증 + (가능시) **pinned NLI 모델/산술 실행 코드**(토큰 0~소량) |
| 6 | 2-채점관 패널, **자기 채점 금지** | 직무분리: **요약을 쓴 모델이 그 요약의 사실성을 스스로 판정 못 함**(no marking own homework) |
| 7 | 다른 계열이 같은 계열 못 본 **버그** 포착(46:1) | 다른 계열이 **환각 수치($2B→$20B)·잘못된 귀속·함의 실패 요약** 포착 |
| 8 | 리뷰어가 **코드 전체(전체 컨텍스트)** 를 봄 | 🔒 **인증자는 narration 차단 — 최소 컨텍스트만**(원문 구절 + 주장 문자열 + 스키마). *블로그보다 강화* |
| 9 | FAIL/PARTIAL → 1회 개선 라운드 | FAIL → **1회 제한 재생성**, 아니면 **QUARANTINE**(사람 검토). 불일치 시 아무것도 발행 안 함 |
| 10 | 출력: 코드 + 리뷰 `reviewN.md` | 출력 상태 **3종 칩: VERIFIED / DEMOTED-TO-UNCERTAIN / BLOCKED** (사용자에게 노출) |
| 11 | 모델 ID 어서트 / retry+backoff / STATUS 재개 / 증거 보존 | 동일 차용 + **감사 레코드**(provenance, 두 모델 판정, 승인자) = 영속 원장 |

> **8번이 이 프로젝트의 고유성.** 블로그 리뷰어는 산출물을 다 보지만, 우리 인증자는 작성자의 추론을 못 본다 → "확인 도장(confirmation pass)"이 아니라 진짜 **독립 재도출(independent re-derivation)** 강제. 이것이 상관 오류(correlated error)를 끊는 메커니즘.

---

## 4. 어느 토폴로지인가 (Topology decision)

블로그의 4개 토폴로지(특화/릴레이 R1·R2/핑퐁 P1·P2/위임) 중 verify-before-publish는 **릴레이 R1의 "차단·강화형 변형"** 이다.

| 블로그 R1 | verify-before-publish |
|---|---|
| Claude 개발 → Codex 리뷰 → Claude 개선 | Claude 작성 → Codex **인증(차단권)** → (FAIL시) Claude 재생성 |
| 리뷰어는 전체 산출물 봄 | 인증자는 **최소 컨텍스트만** |
| 리뷰는 지적만(차단 없음) | 인증자는 **BLOCK/DEMOTE 권한** |
| 리뷰어가 편집 안 함(R 계열) | 인증자가 작성물을 **고치지 않음**(고치면 직무분리 붕괴) |

**핑퐁(P) 배제 이유:** 블로그가 P2(Codex 편집)는 컷오프로 불안정, "Codex=리뷰/Claude=편집"이 안정적이라 결론. 우리는 한발 더 나아가 **Codex=인증만(편집 0)/Claude=작성·재생성**으로 고정 — 인증자가 콘텐츠를 만지면 "자기 채점 금지" 원칙이 깨지기 때문. 블로그의 실측 결론과 정합.

---

## 5. Bedrock 배선 — cross-harness 경계 (Wiring)

[`briefing-news-agent-spec-research.md`](../research/briefing-news-agent-spec-research.md)가 v1 최대 리스크로 본 "Codex를 Strands 밖 별도 하니스에" 문제를, 블로그가 직접 해소한다: **Codex도 Bedrock 위에서 돈다.**

```
┌──────────────── 같은 AWS 계정 / 같은 Bedrock 리전 ────────────────┐
│                                                                  │
│  [AUTHOR] Claude (Strands/AgentCore)                             │
│   ANTHROPIC_MODEL = global.anthropic.claude-opus-4-8 [^infprof]  │
│   · 5개 출처 클러스터링 · 요약 · "왜 중요한가" 주장               │
│        │                                                         │
│        │  최소 컨텍스트 핸드오프(파일):                          │
│        │  {원문 구절, 주장 문자열, 스키마}  ← narration 제거      │
│        ▼                                                         │
│  [CERTIFIER] Codex  (codex exec, model_provider=amazon-bedrock)  │
│   model = openai.gpt-5.5 · reasoning_effort = xhigh             │
│   · (a) 함의 NLI  (b) 산술 재도출  (c) grounding 재페치          │
│        │                                                         │
│        ▼  결정론적 게이트(스키마 + pinned NLI/산술 코드)         │
│   판정: VERIFIED / DEMOTED-TO-UNCERTAIN / BLOCKED                │
│        │                                                         │
│        ▼  verify-then-fire (AND 게이트: 합의 시에만 발행)        │
│  [DELIVER] Claude → SES 이메일(07:00 KST) · verdict 칩 노출       │
│            BLOCK/불일치 → QUARANTINE(사람 검토)                   │
│                                                                  │
│  지속 상태: 사실-only 스냅샷 + 감사 레코드(두 모델 판정·승인자)   │
└──────────────────────────────────────────────────────────────────┘
```

[^infprof]: 블로그가 `global.anthropic.claude-opus-4-8`(=`global.` **inference-profile prefix**)을 쓰는 게, 스펙 리뷰의 "bare `anthropic.claude-sonnet-4-6`는 In-Region 미지원 → `us.`/`global.` 프로파일 필요" 발견을 **그대로 입증**한다. author/certifier 모두 프로파일 id 사용.

**경계 구현:** AgentCore Runtime 안에서 author가 돌고, 검증 단계에서 **subprocess로 `codex exec` 호출**(또는 Codex를 도구로 래핑). 자격증명·리전·VPC·로깅·비용이 한 계정으로 통일되어, "별도 클라우드 인증자"보다 운영이 단순. (Codex 설정 `~/.codex/config.toml`: `model_provider = "amazon-bedrock"`, `profile`, `region`.)

---

## 6. 블로그에서 그대로 가져올 운영 안전장치 (Scaffolding transfer)

블로그의 안전장치 4종 + 증거 보존을 그대로 차용한다 — 이미 검증된 패턴이다:

1. **모델 ID 어서트** — 정말 `global.anthropic.claude-opus-4-8` / `openai.gpt-5.5`로 돌았는지 확인(별칭 다운그레이드 방지). 잘못된 모델로 발송되는 사고 차단.
2. **재시도 + 지수 백오프** — Bedrock throttle 대비 최대 N회. 일일 배치라 여유.
3. **stage gate** — 각 단계 기대 산출물 검사 후 진행("브리핑이 아예 안 만들어진" 케이스를 토큰 0으로 정직하게 걸러냄 — `validate_index`의 사실콘텐츠판).
4. **STATUS 기반 재개** — `DONE/FAILED` 기록으로 중단 시 완료분 건너뛰기(멱등성과 연결, 스펙 리뷰 H6).
5. **증거 보존 = 감사 레코드** — "모든 산출물이 증거로 보존" → 의무 원장 철학과 동일. 출처·두 모델 판정·승인자를 재-diff 가능한 상태로.

---

## 7. 블로그를 넘어서는 지점 + 정직한 간극 (Extensions & honest gaps)

**우리가 강화하는 것:**
- **최소 컨텍스트 인증**(§3-8) — 블로그 리뷰어는 전체를 보지만 우리 인증자는 narration 차단 → 진짜 비상관.
- **AND 게이트 / 비가역 대응** — 이메일은 회수 불가. 블로그는 1회 개선으로 끝이지만 우리는 **두 모델 합의 시에만 발행**(precision 우선, recall 희생) + QUARANTINE.
- **3-상태 출력**(VERIFIED/DEMOTED/BLOCKED)을 **사용자에게 칩으로 노출**("show your work") — 블로그는 내부 리뷰 파일.

**정직한 간극:**
- **함의는 코드 구문만큼 결정론적이지 않다.** 블로그의 JS 구문검사는 byte-stable이지만, 사실 함의는 본질적으로 모호. → 가능한 부분(산술·스키마)은 실행 코드로 결정론화, 함의는 pinned NLI(SummaC/FENICE류)로 최대한 결정론화, 나머지만 LLM-judge. "두 모델 = 신뢰"가 아니라 **"결정론 게이트 = 신뢰"** 를 헤드라인으로([`news-agent-differentiation.md`] 234행).
- **법무(Bartz/Ross)** — grounding용 지속 재페치는 방어 어려운 접근 패턴. 스냅샷은 **사실-only(verbatim 저장 금지)**, robots/ToS 존중, 협력/오픈 RSS 한정(스펙 리뷰 §5).
- **비용/지연** — 블로그는 단발 실험. 우리는 일일 배치(breaking-news SLA 없음)라 주장당 NLI+산술이 수용 가능. 단 certifier 측은 author의 prompt caching 혜택 밖이라 별도 최적화.

---

## 8. v1 적용 한 줄 정리 (Bottom line)

> **briefing-news-agent v1 = R1-강화형 토폴로지.** Claude(author, Strands/AgentCore, `global.` 프로파일) → 최소 컨텍스트 핸드오프 → Codex(certifier, 같은 Bedrock 계정 `codex exec`, 편집 0) → 결정론적 게이트(함의/산술/grounding) → verify-then-fire(07:00 발송) + verdict 칩 + QUARANTINE. 블로그의 모델-ID 어서트·백오프·stage gate·STATUS 재개·증거 보존을 그대로 차용. 검증 게이트는 **백엔드 신뢰 장치**이고, 사용자에게는 [`personalized-morning-briefing-research.md`]의 **짧고 차분한 아침 브리핑**으로만 보인다.
