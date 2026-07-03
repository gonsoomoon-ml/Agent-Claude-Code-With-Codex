# 4-컴포넌트 분석 — Strands · AgentCore · Claude Code headless · Codex headless

> **목적:** 뉴스 브리핑 에이전트를 *어떤 4개 컴포넌트로, 누가 무엇을, 언제 무엇을 쓰며, 어떻게 어울리게* 구성할지 — 효과적 레버리지 분석. (구현 스텝·인프라 세부는 별도 구현 플랜.)
> **방법:** 5-렌즈 동적 워크플로우(직무분리·중복/YAGNI·신뢰무결성·비용/지연·배포) + 종합·정직성 비평 + 탐색(Strands/AgentCore 패턴, Claude Code/Codex 헤드리스). 2026-06-25 · Korean-friendly.
> **연결 문서:** [`prd_news.md`](../prd/prd_news.md) · [`harness-to-verify-before-publish-mapping.md`](harness-to-verify-before-publish-mapping.md) · [`briefing-news-agent-spec-research.md`](../research/briefing-news-agent-spec-research.md) · [`value-roadmap.md`](value-roadmap.md)

---

## 0. 한 줄 결론
**4개는 co-equal peer가 아니다.** 효과적 레버리지 = *자율 하니스(Claude Code·Codex)는 두 모델-직무에, 프로그램된 코드는 신뢰-치명 제어에, AgentCore는 호스트에* 못박고 — **오케스트레이션(특히 비가역 발송 결정)은 자율 하니스가 아니라 결정론 게이트 코드가 소유**한다. Strands는 *능력상 필수가 아니라* AgentCore-정규 패키징·제어 평면을 원할 때의 *구조 선택*이다.

## 1. 핵심 축 — 세 가지 *종류* (capability가 아니라 *궤적 통제*)
| 종류 | 컴포넌트 | 성질 |
|---|---|---|
| **자율 하니스(model-driven 궤적)** | `claude -p`, `codex exec` | 목표 주면 *모델이* 계획·도구사용·실행. 적응력 최고, *비결정적*. |
| **프로그램된 오케스트레이션(code-driven 궤적)** | Strands tool / plain Python | *당신이 코드로* 단계·게이트를 못박음. 결정론·감사성·통제. |
| **관리형 호스트** | AgentCore | 누가 일하든 *어디서 도느냐*. 직교. |

> **"claude/codex가 Strands를 대체 가능?" → capability상 *예*** (블로그 `collab.sh` = 스크립트 + 2 CLI, Strands 0). 진짜 차이는 capability가 아니라 **궤적 통제 + decorrelation**. *비가역 발송* 제품에선 "이걸 보낼까?"라는 신뢰-치명 결정의 궤적이 반드시 **code-driven**이어야 한다(자율 하니스에 맡기면 게이트를 합리화·우회).

## 2. 4직무 1:1 + 토폴로지 (가장 큰 교정)
| 컴포넌트 | 직무 | 절대 금지 |
|---|---|---|
| **AgentCore** | host substrate(author 측): 컨테이너·egress·07:00 착지점 | 오케스트레이션 두뇌 오해 / certifier 동거 |
| **Strands** | AgentCore-상주 fabric + 에이전트형 큐레이션(수집·HTML 스크래핑·thread-id 클러스터링·PROFILE 랭킹·렌더·SES) + 하니스 배선 + **영속 원장 소유** | LLM *요약*(=author 중복) / certifier에 envelope 외 전달 |
| **Claude Code (`claude -p`)** | **author/생성자**: Skill(TYPE/DEPTH/PROFILE)·종합·원자적 claim 분해 | 자기 채점 / certifier 직접 호출 |
| **Codex (`codex exec`)** | **독립 인증자**: 최소컨텍스트 함의·산술 독립 재도출, BLOCK권만 | 콘텐츠 편집 / prose 반환 |
| **gate (plain code)** | **오케스트레이터** | — |

- **토폴로지 = Specialized + 단방향 Relay(파일 핸드오프 1회), Ping-pong 금지**(인증자에 편집권 주면 '자기 채점 금지' 붕괴 + 두 모델 같은 오답 수렴).
- **흐름:** `gate → Claude(초안+claims) → gate가 envelope sanitize → Codex(판정) → gate가 VERIFIED/DEMOTED/BLOCKED 적용 → SES`.
- **핵심:** certifier 호출 주체가 author(Claude)가 아니라 **게이트** → narration 차단을 *프롬프트 선의*가 아니라 *토폴로지*로 강제.

## 3. 언제 무엇을 쓰나 (when to use each — 실전)
| 작업 성격 | 쓸 것 | 이유 |
|---|---|---|
| 개인화 오서링(Skill 필요) · *깨지기 쉬운 적응* 작업(가변 HTML 스크래핑·애매한 클러스터 머지) | **Claude Code headless** | Skill=유일 레버; 스크립트가 깨지는 곳을 에이전트가 적응 |
| 비상관 검증(함의/산술), 검증 *코드 작성·실행* | **Codex headless** | 다른 계열=신뢰 속성, 코드 실행 |
| 신뢰-치명 *결정론* 제어: verify-then-fire 게이트·envelope·원장·스케줄·**비가역 발송 결정** | **프로그램된 코드**(Strands tool 또는 plain Python) | *자율 에이전트에 발송 결정 위임 금지* |
| 관리형 일일 호스트 + IAM→Bedrock | **AgentCore** | 호스팅(직무 직교) |

**각 컴포넌트의 유일 레버:**
- **Claude Code** = Skill(개인화/워크플로 패키징) + 최고 에이전트형 오서링.
- **Codex** = *다른 모델 계열*(decorrelation) + 검증 *코드 실행*.
- **AgentCore** = 관리형 일일 호스트(IAM→Bedrock·egress·장수 실행).
- **Strands** = AgentCore-정규 패키징 + typed 제어 평면(*단 plain Python 대체 가능 — capability 필수 아님*).

**효과 원칙:** ① 신뢰-치명 단계는 *code-driven*(자율 하니스 금지) · ② Claude Code 적응력은 *깨지기 쉬운 부분에만* scoped(전 파이프라인 자율 실행 금지 — 결정론·비용·감사성 손해) · ③ Codex는 *검증만* 순수 유지 · ④ Strands는 *AgentCore 패키징/관측성*을 원하면 채택, 미니멀하면 *script(collab.sh)+2 CLI*로 충분.

## 4. 중복·load-bearing 판정 (솔직)
- **제거 불가:** **Codex**(overlap 0, 빼면 verify-before-publish의 decorrelation 붕괴 = 제품 폐기) · **Claude Code**(author 슬롯 승자 — Skill은 Strands에 등가물 없는 1급 기능).
- **조건부:** **AgentCore**(host — *ECS Fargate+EventBridge cron이 self-managed 대체재*. "overlap 0"이 아니라 "대체재 존재하나 노동 더 듦"; U1로 증명).
- **재평가 — Strands:** author로 쓰면 Claude Code와 *정면 중복*(같은 Bedrock 두 경로). **그러나 author를 *안 하면* 비-중복 fabric으로 생존.** → §5.
- **유효 구성 스펙트럼:** 4(풀) / **유효-3**(AgentCore + Claude + Codex, Strands=fabric) / (미니멀)**유효-2**(Claude + Codex + ECS·cron, plain-code 오케스트레이션). *목표는 "4개를 효과적으로"이지 "4개 전부 동시에"가 아니다.*

## 5. Strands는 셋과 *어떻게 어울리나* (공존)
Strands가 약한 고리였던 *유일한 이유*는 "LLM 요약(author)을 하면 Claude Code와 겹친다"였다. **요약을 Claude Code에 전담**시키면 Strands는 비-중복 *결합 조직(connective tissue)*이 된다.
- **↔ AgentCore = 공생.** Strands는 AgentCore의 1급 시민(`BedrockAgentCoreApp`·`@app.entrypoint`) — AgentCore Runtime 에이전트의 *정규 작성법*. 호스트와 한 몸. (developer-briefing-agent가 이 구조.)
- **↔ Claude Code = 분업.** Strands가 *큐레이션*(어떤 기사를·어떻게 묶어·어떤 순서로), Claude Code가 *오서링*(요약·What is Important). Strands는 `claude -p`를 subprocess 도구로 호출하고 한 문장도 요약하지 않음 → 중복 소멸.
- **↔ Codex = 게이트로 매개.** Strands가 verify-then-fire 게이트를 *스키마 강제 도구*로 호스팅해 envelope만 `codex exec`에 전달. certifier 호출을 LLM 에이전트 루프가 아니라 *결정론 도구*가 함 → "두 CLI를 동격으로 부르면 narration 샌다"는 우려가 *스키마*로 닫힘.
- **입양하는 두 orphan(약한 고리 → 결합 조직):** ① **thread-identity**(상류 단일 병목 — 결정론 후보생성 + 에이전트형 ambiguous-merge 판정) · ② **영속 원장**(inclusion-test #2 — SQLite, certifier 출력 amortization의 토대).
- **불변식:** *요약 금지*(author=Claude Code) · certifier는 envelope 스키마만 · verify-then-fire는 결정론 코드 · 큐레이션이 모델 쓰면 싼 모델(Haiku).
- **정직한 잔여:** 큐레이션의 *에이전트형* 가치는 fallback·ambiguous-merge·랭킹에 집중 — 수집/dedup이 trivial하면 Strands 가치는 "앱 fabric"으로 수렴(그래도 AgentCore-정규라 정당). 즉 Strands는 *항상* load-bearing은 아니고 *thread-id·원장·하니스 배선*에서 load-bearing.

## 5.5 Strands Graph vs plain-code gate — 확장 진화 (generate/decide 경계)
> v1은 plain code(2 에이전트). LLM 에이전트가 *늘면* Strands Graph가 **생성/평가 층**에서 값을 번다 — 단 **결정 층(gate)은 plain code 유지**. 둘은 경쟁이 아니라 *층*. (Self-Correcting-Explainable-Translation-Agent 가 증명: agents in graph + **decision in Python SOP**.)

- **★ 경계 = generate/decide.** Strands Graph = *생성/평가*(병렬·관측·재시도). plain-code gate = *비가역 발행 결정*(결정론·감사). 비가역 "발행?"은 절대 그래프 라우팅(LLM 라우팅 허용 = 부채)에 두지 않는다.
- **Strands가 빛나는 *미래* 지점(2→N 에이전트):** 다중 평가자(정확성·신선도·grounding) 병렬 · 큐레이션 클러스터(클러스터→랭킹) · backtranslator · Cross-Source Reconcile·Diff-Since-Last·Q&A(v2). 이점 = 선언적 병렬 · 에이전트별 OTEL/비용 · 노드별 retry/timeout · tools/memory/A2A · AgentCore-native.
- **plain code가 trust-critical인 이유(불변):** 결정론·감사·테스트(DI)·trust 불변식 *국소화*·typed-args(다중 사용자 동시 fan-out 레이스 없음). 그래프의 **노드-입력 자동 전파**(선행 node 의 최종 답변을 `_build_node_input` 이 다음 node 에 무조건 주입 — §5.5.1 검증)·LLM-라우팅 유연성은 *결정 층엔 부채*.
- **Runtime ≠ Graph(오해 해소):** AgentCore Runtime(`@app.entrypoint`)은 *아무 Python*이나 호스팅 → **그래프 없이도 배포·관측·스케줄 누림**. 그래프 미채택 ≠ AgentCore 포기.
- **★ 스캐폴드가 이미 진화 준비됨 — DI seam:** `gate.produce_card(..., draft_fn/revise_fn/verify_fn)`. 지금=plain author 함수, 나중=Strands-graph-backed로 *주입만 교체* → **gate 결정 로직 무변경**. "지금 단순, 나중 graph"를 리팩터 없이.
- **staging:** v1 plain(조기 graph 금지) → 에이전트 증가 시 *생성/평가 층만* graph, gate plain 유지.

### 5.5.1 검증 — Strands Graph 데이터 흐름 (2026-06-26, adversarial 9-agent 웹 리서치)
**판정: 핵심 결론 HOLDS (소스 확인) + 정밀 정정 4건.** "gate = plain code, Graph 는 gate *아래*" 유지 — 단 근거를 소스 확인된 형태로 조이고 두 보조논거(hidden-CoT 누출·루프 어색함)는 버린다.

- **소스 확인 메커니즘(decisive):** Strands `_build_node_input` 이 선행 node 의 **최종 답변**을 무조건 append — `From {dep_id}:` + `  - {agent}: {str(AgentResult)}` (공식 Graph 가이드: "Dependent nodes receive … Results from all dependency nodes"). → `author → certifier` edge 를 그냥 그으면 **author 의 최종 답변이 certifier 입력에 자동 주입** → decorrelation 이 *조용히* 깨진다. per-edge/node 입력-scoping 노브 **없음**(`add_node` 입력-필터 없음; `add_edge` 는 boolean `condition`=route-or-drop 만; Issue #544: node 는 Agent/MultiAgentBase). → **격리가 더 쉽지 않음** = plain code 의 명시적 4필드 경계 논거 *강화*.
- **정정 1 — 누출 = 최종 답변 텍스트, hidden CoT 아님.** `str(AgentResult)` = 최종 message(text/structured JSON)만; `reasoningContent`(extended thinking)·`toolUse`·이전 turn 은 SKIP. "narration 누출"은 *author 가 최종 답변에 써넣은* 부분에 한해 정확("모델 추론 trace 가 샌다"는 과장). 그래도 author 최종 초안 누출 = 정확히 막으려는 대상.
- **정정 2 — 루프는 Graph 회피 이유가 아님.** Graph 가 `max_node_executions`/`timeout` 으로 bounded loop 를 native 지원 → Maker-Checker 루프 자체는 plain code 근거가 못 됨. 진짜 근거 = envelope 경계 + 비가역 결정.
- **정정 3 — decorrelation 은 *유일*이 아니라 *결정적 이유 중 하나*.** 누출을 완전히 풀어도 비가역 PUBLISH/QUARANTINE 결정은 LLM-routed edge 뒤 금지 — 결정론·감사·test-injectable(독립 제2근거).
- **정정 4 — "Graph 격리 불가"는 과장.** edge 생략 + envelope 를 task/공유 `invocation_state`("without exposing it to the LLM") 또는 custom MultiAgentBase node 로 격리 *가능*. 정확히: "자연 배선이 조용히 샌다 — 격리는 의도적·비자명·덜 감사가능."
- **출처:** SDK `_build_node_input`(strands-agents/sdk-python) · 공식 Graph 가이드(strandsagents.com) · Issue #544 · LLM-judge bias(arXiv 2412.05579) · 상관오류 "Great Models Think Alike"(2502.04313) · anchoring(2412.06593) · self-refine bias(2402.11436).

### 5.5.2 그림 — 흐름(dynamic) + 아키텍처(static)
> **정본·확장판 = [`pipeline-flow.md`](./pipeline-flow.md)**(legend·핵심 불변식·테스트 매핑 포함). 아래는 동일 그림의 인라인 사본 — 수정 시 양쪽 동기화.

**(a) 흐름 — 한 카드가 만들어지는 순서 (verify-before-publish):**
```
[1] fabric/Graph │ collect · cluster · rank · 기사별 fan-out
                 └ 생성 층 — Graph 가 적합 (병렬 · 관측 · retry)
      │
[2] fabric       │ freeze source → sha256 → ledger
                 └ 권위 페치 = fabric 소유 (author 가 증거 자체를 통제 못함)
      │
[3] gate         │ draft_fn ─▶ Claude author   (claude -p, Bedrock)
[4] Claude       │ 초안 + atomic claims 반환    (gate 로 가는 건 최종 답변만)
      │
═════ decorrelation 경계 — gate 가 envelope 를 손으로 작성 ═════
[5] gate         │ envelope = 정확히 4필드
                 │   { source_excerpt, claim_text, claim_type, schema }
                 └ narration / reasoning / confidence = 필드 자체 부재
      │  envelope 만 건너감
[6] gate         │ verify_fn ─▶ Codex certifier (codex exec, Bedrock)
[7] Codex        │ claim별 독립 재도출 → verdict (cross-family · CoT 안봄)
      │
[8] gate         │ 실패 claim 있으면 → revise_fn(실패분만) ↺ [3]–[7]
                 └ Maker-Checker, cap 2회 (Graph 도 가능하나 코드가 단순·감사)
      │
[9] gate         │ verdict 적용: VERIFIED / DEMOTED / BLOCKED
      │
[10] gate        │ AND-gate 결정 (코드, LLM 아님) ── 비가역 = 결정론 · 감사
                 ├─ 전부 통과 ─▶ PUBLISH ─▶ SES → 이메일 (07:00 KST)
                 └─ 소진/불일치 ─▶ QUARANTINE ─▶ 사람 검토 큐
```

**(b) 아키텍처 — 층 · 소유 · 신뢰 경계 (static):**
```
┌─ AgentCore Runtime ── 관리형 호스트 (컨테이너 · egress · 07:00 KST 트리거)
│
│  ◆ Strands curation fabric ── [생성/평가 층 — Graph 가 빛나는 곳]
│      Graph: collect → scrape → thread-cluster → rank → 기사별 fan-out
│      (조건 edge · bounded loop · 병렬 · 중첩 = 모두 native)
│          │ frozen + sha256
│          ▼
│  ◆ source_store ── content-addressed source-of-record + durable ledger
│          │ 동결본 read
│          ▼
│  ◆ gate (plain Python) ── [신뢰 경계 · 비가역 결정 소유 · 오케스트레이터]
│      produce_card:  draft → envelope(4f) → verify → verdict → decide
│          │ draft_fn/revise_fn                    │ verify_fn
│          │ (build_system_prompt 만)               │ (4필드 envelope 만)
│          ▼                                        ▼
│      ╔═ Claude author ════╗   ┊   ╔═ Codex certifier ═══╗
│      ║ claude -p, Bedrock ║   ┊   ║ codex exec, Bedrock ║
│      ║ Sonnet 4.6         ║   ┊   ║ gpt-5.5             ║
│      ║ clean dir          ║   ┊   ║ clean dir           ║
│      ╚════════════════════╝   ┊   ╚═════════════════════╝
│        author ≠ certifier     ┊     certifier: narration · user 안봄
│        (import 구조적 차단)   decorrelation 경계
│                                                  │ GateDecision
└──────────────────────────────────────────────────┼───────────────
                                        PUBLISH ────┴──── QUARANTINE
                                           ▼                 ▼
                                      SES → 이메일       사람 검토 큐

※ certifier 가 Graph node 가 *아닌* 이유: Graph 의 `_build_node_input` 이
  선행 node(author) 의 최종 답변을 다음 node 입력에 자동 주입 → certifier 가
  envelope 대신 author 답변을 보게 됨(decorrelation 붕괴). gate 가 envelope 를
  손으로 작성하면 그 경계가 구조적으로 자명 · 테스트로 assert 가능.
```

## 5.6 옵션 B 구현 — all-Strands 런타임 + subprocess certifier (2026-06-27)

> **정정(2026-06-27):** author 를 Strands Agent 에서 **headless `claude -p`(Claude Code)로 복원**. "모든 걸 Strands 로"는 author 에서 Claude Code 의 *고유 레버*(Skill·CLI 하니스)를 잃기에 원래 듀얼 하니스 전제(**Claude Code author + Codex certifier**)로 회귀. 둘 다 별도 subprocess + clean dir(대칭). Strands 는 v1 코드에서 **미사용**(향후 curation graph 예약). 아래 "all-Strands" 서술은 *탐색 기록*으로 보존 — 현 구현 author=`claude -p`(`--system-prompt` 로 build_system_prompt 가 유일 통제).

**결정:** "Strands 가 모든 것을 덮되" 신뢰 경계는 보존 — **AgentCore Runtime host + Strands author `Agent` + 결정론 gate SOP + *subprocess* codex certifier + 결정론 curation**. certifier 만 별도 프로세스(물리 격리 + cross-family). (A안=완전 in-process 는 누설 0 PoC 전제라 보류.)

- **비협상 규칙(구조로 강제):** ① 오케스트레이션·비가역 결정은 *결정론 Python*(gate SOP + entrypoint 핸들러)이 소유 — 어떤 에이전트도 "발행?"을 정하지 않음. ② **author→certifier graph edge 없음**(애초에 그래프 밖에서 gate 가 certify 직접 호출 → Strands `_build_node_input` 누설 표면 0). ③ certifier 는 **clean dir 에서 envelope 4필드만** (`_build_codex_prompt` + `tempfile.mkdtemp`). ④ author 는 certifier 를 import 안 함.
- **레퍼런스 적용:** *Self-Correcting-Translation-Agent* → SOP=순수 Python(`sops/`)·status-only 노드·루프 종료 3중 방어(우리 gate 가 동형). *Deep Insight* → `BedrockAgentCoreApp`+`@app.entrypoint`(async gen → SSE dict)·`BedrockModel` 주의(Opus 4.7+ 는 `temperature` 금지 → 400; Sonnet 4.6 만 허용)·toolkit `Runtime.configure().launch()` 배포. 둘 다 **brace-safe 로더는 우리 것 유지**(Deep Insight 는 `str.format` 으로 깨짐).
- **구현된 파일:** `shared/certifier.py`(codex subprocess + 결정론 산술 byte-stable) · `shared/author.py`(Strands `Agent`, JSON 파서는 순수·테스트가능, certifier 미import) · `shared/render.py`(PUBLISH-only + verdict chip) · `runtime/curation.py`(결정론 + DI fetch seam) · `runtime/agentcore_runtime.py`(실 `@app.entrypoint`). 검증: ruff 통과 · pytest 35 통과(결정론 산술·codex-프롬프트-envelope-only·파서 가드 신설) · BedrockModel/Agent/BedrockAgentCoreApp 생성자 kwargs 실검증.
- **통합 — 2026-06-27 라이브 e2e 검증 ✓:** 실 RSS(`fetch_clean_rss` feedparser 구현) → freeze(sha256) → Strands author(Sonnet 4.6, KO/engineer lens) → envelope → `codex exec`(gpt-5.5, **cross-family**, clean dir, envelope-only) → **PUBLISH** → render 전체가 실동작(aws-ml 기사: 4 claim 全 VERIFIED). decorrelation 유지(codex 는 envelope 만 봄). fail-closed 확인(거짓 entailment→DEMOTED). **codex gotcha:** 비-git clean dir 실행엔 `--skip-git-repo-check` + `stdin=DEVNULL` 필수. gate DI seam 으로 unit 테스트는 결정론 유지(35 통과).
- **§5.5 staging 일치:** v1 curation = 결정론 Python(조기 graph 금지). 출처↑·LLM 클러스터/랭킹 생기면 `curate()` 를 Strands `GraphBuilder`(FunctionNode 노드)로 승격 — gate 무변경. 흐름·아키텍처 그림 = [`pipeline-flow.md`](./pipeline-flow.md).

## 5.7 Strands supervisor 오케스트레이션 — trust-preserving (2026-06-27)

**요청:** "Strands 가 *지금* 오케스트레이션"(Deep Insight `self-hosted/src/prompts/supervisor.md` 참조). 구현+라이브 검증.

- **핵심:** supervisor(Strands `Agent`, LLM)는 **순서만 통제** — 도구를 올바른 순서로 호출, **발행 결정은 절대 안 함**(Deep Insight `supervisor.md` L49 verbatim: "Let tools do the work - focus on orchestration, not execution"; "never makes final decisions"는 우리 패러프레이즈). 도구 3개(`curate_sources`/`verify_and_produce_card`/`render_briefing`) = 결정론 Python 을 `@tool` 로 감쌈 → **LLM 은 supervisor 하나뿐.**
- **비협상 보존:** verify-before-publish(author→envelope→certifier→**결정론 decide**)는 `verify_and_produce_card` *도구 안*. supervisor 는 verdict reach/override 불가 + author↔certifier 사이에 *안 앉음*(핸드오프=도구 내부 → decorrelation 유지). 규칙은 `supervisor.md`의 "절대 규칙" + 각 `@tool` docstring 에 **이중 인코딩**.
- **라이브 e2e ✓(2026-06-27):** supervisor 가 curate_sources→verify_and_produce_card→render_briefing 을 정확한 순서로 호출 — aws-ml 1기사 → `claude -p` author 7 claim → `codex` 全 VERIFIED → **PUBLISH** → render. **supervisor 가 스스로 "발행은 도구의 결정론 게이트가 판정, 나는 verdict 미개입"이라 트랜스크립트에 보고.**
- **파일:** `runtime/supervisor.py`(Agent + 3 `@tool` + `run_supervisor`) · `core/prompts/supervisor.md` · `scripts/supervisor_smoke.py`. ruff·pytest 35 통과.
- **언제 이 경로?** 워크플로가 *가변/적응적*(fragile 페치 우회·동적 출처)일 때 supervisor 가 값. 현 고정 파이프라인엔 LLM 오케스트레이션이 *오버헤드* → 결정론 entrypoint 와 **병존**(둘 다 같은 SOP·도구 호출 → 신뢰 동일, 차이는 궤적 통제자뿐).

## 6. 신뢰 배선 — decorrelation을 *경계*로 강제
- certifier 입력 = **화이트리스트 4필드 envelope `{source_excerpt, claim_text, claim_type, schema}`만**(narration/reasoning/confidence 존재 자체 금지 — 블랙리스트 아닌 화이트리스트). author 작업 디렉토리 미마운트.
- certifier = **별도 실행 경계 기본**(같은 AgentCore 컨테이너 동거는 '한 호스트=한 신뢰 도메인'으로 물리 격리 약화 → PoC로 "envelope 외 누설 0" 입증 시에만 동거).
- **"두 모델=신뢰"가 아니라 "결정론 게이트=신뢰"**: 산술/날짜=샌드박스 코드(byte-stable), 함의=pinned NLI(가능 시). verdict 산출은 LLM 아닌 코드. AND 게이트(비가역 이메일이라 둘 다 통과해야 VERIFIED).
- certifier 권한 = **BLOCK권만**(편집·생성 0). 재생성 필요 시 certifier가 고치지 않고 *게이트가 author를 다시 부른다*.

## 7. 비용/지연
- author=**Sonnet 4.6**(Opus over-spec — 아침 본편이 Smart Brevity), certifier=**gpt-oss-120b**(결정론 게이트가 신뢰원천이라 frontier 불필요).
- **Bedrock = Batches·auto prompt caching 미지원**(first-party 전용) → "50% 배치 할인" 전제 금지. caching은 *기사별 fan-out에서 공유 system/Skill 프리픽스*일 때만 이득(단발 1회는 write 프리미엄만 = 순손해).
- 5~7 기사 **병렬 fan-out**으로 07:00 데드라인 안 지연 흡수. certifier는 *정량 주장·변경 기사에만* 선택 적용(amortize).

## 8. "4개" 프레임이 *가린* 것 (비평 발견 — 반드시 포함)
- **certifier *출력* amortization** — verdict 로그·BLOCKED 더미·NO_CHANGE를 수확([`value-roadmap.md`]: Diff-Since-Last·Withheld-and-Why). Codex는 "덜 호출"만이 아니라 "출력을 더 짜내기".
- **영속 원장 소유자** — inclusion-test #2 → Strands fabric(SQLite).
- **cross-lingual NLI** — 영어 원문 ↔ 한국어 요약 함의. pinned NLI 대부분 영어 모노링구얼 → envelope에 *원문(영어) 구절 + 한국어 claim* 동봉, catch-rate로 공백 측정.
- **dedup/thread-identity** — 4개 *어디에도 안 속하는* 결정론 전처리가 신뢰 병목 → Strands 큐레이션이 소유, 양방향 catch-rate 회귀셋으로 튜닝.

## 9. 배포 미지 (요약 — 상세·de-risk는 구현 플랜)
- **U1(컨테이너 CLI 실행):** AgentCore가 임의 커스텀 ARM64 컨테이너 허용(`/invocations`+`/ping`, 8080)+TCP/443 egress → "플랫폼 차단"이 아니라 "우리 Dockerfile" 문제. 잔여 = install·IAM→Bedrock·no-TTY PoC.
- **U2(스케줄링):** `Scheduler → Lambda(async) → invoke_agent_runtime` 권장(async 최대 8h; 멀티-분 파이프라인엔 직접 동기 invoke 부적합). PoC 발화 검증 전 확정 금지.

---

*5-렌즈 워크플로우 + 정직성 비평 + 탐색으로 작성. 구현 스텝·PoC 순서는 별도 구현 플랜(.claude/plans) 참조.*
