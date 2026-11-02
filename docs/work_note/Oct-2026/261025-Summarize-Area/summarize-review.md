# 주간 영역 산출물 검토 — 인사이트 리포트 → Applied AI 데모 → 대안 (2026-10-25)

> 요구사항: [summarize-prd.md](summarize-prd.md). 1차 아이디어(주간 인사이트 리포트)는 사용자가 기각("not good")했고, 2차 후보(주간 Applied AI 데모 1개)와 "더 있으면" 요청을 이 문서가 다룬다.
> 방법: 저장소 근거 수집 → 8 에이전트 workflow(`wf_70384540-44a`: 재료 타당성 · 실무자 가치 · 하니스 설계 · 비용/법률/운영 → 병합·순위 → 상위 3 후보 각각 반박) → 종합. 모든 수치는 **추정**이면 그렇게 표기했다. 저장소 파일 변경은 이 문서 1개뿐(PRD 미수정).
> 상태: **검토 완료 · 사용자 결정 대기**(§6).

## 0. 요약

- **결론: 제외 규칙 아래에서 "주 1회 영역별 산출물" 슬롯에는 제품 모양의 답이 없다.** 네 가지 형태(인사이트 리포트 · 데모 · 검증된 빌드 브리프 · 재계산 시트)를 모두 시험했고 전부 같은 벽에 부딪혔다. 이 독자층(AWS AI/ML 실무자 7명)에게 가치는 **주간 푸시가 아니라 필요할 때 끌어가는 검증된 증거**다.
- **데모 아이디어의 방향은 맞다**(독자가 읽고 끝나는 산출물이 아니라 자기 과제에 가져다 쓰는 산출물). 그러나 **원안 그대로("Claude 가 데모를 짜고 Codex 가 검토")는 PRD 자신의 예시 문장과 동형**이다 — `design/prd/prd.md` Consideration "(예: Plan/Generate Code: Claude Code, Review : Codex)". 하니스의 네이티브 용법이라 "하니스로 만들 수 있으면 제외" 규칙에 정면으로 걸리고, CLAUDE.md 자동 탈락 유형 "코드 생성·리뷰·PR 어시스턴트"에 해당한다. 평가자 4명과 반박자 3명이 **독립적으로 같은 결론**을 냈다.
- 데모가 약속한 **"비즈니스 가치 검증"은 원리적으로 불가능**하다. 검증하고 싶은 수치(Octave 배포 시간 50%↓, Bayer 질문 80% 자동 해결, W컨셉 공수 90%↓)는 전부 그 조직의 데이터·규모·독점 모델 위에서 나온 **조직 고유 결과**다. 데모가 재현할 수 있는 것은 메커니즘(예산 100% → 429 차단)과 순수 산술(0.8³ ≈ 51%)뿐이다.
- **Codex 가 load-bearing 이 되는 자리가 없다.** 코드 리뷰 = 제외 유형, 테스트 실행 = 결정론 CI(LLM 불필요), 스펙에서 테스트 작성 = 테스트 생성(제외 유형). 저장소 자신의 라이브 측정(AI Day 조사)은 12,996 판정 중 codex 7,474 → BLOCK 1건, Python 5,522 → BLOCK 46건이다.
- **살아남은 것(권고):** ⓐ 데모를 **뒤집는다** — 제품이 데모를 만들어 보내는 대신, 이미 배포된 AgentCore Gateway(MCP)로 **검증된 claims · 동결 원문 · 출처**를 독자의 Claude Code 에 공급하고, 데모는 고객 맥락이 있는 **독자 쪽에서** 만든다(+ 독자용 skill). ⓑ certifier 의 공식 일관성 검사(`certifier.py:122` 가 스스로 적은 "formula 재계산은 후속"의 후속) — 품질 작업이지 주간 산출물이 아니다.
- 비용은 쟁점이 아니다(데모 1개 실청구 ≈ $1~4 추정, 일간 run 주합의 +5~25%). **진짜 쟁점은 실행 경계** — 운영 author 는 지금도 Bash·Write·WebFetch 를 연 채 SES 발송·DDB 쓰기 role 에 닿는다(N2 미구현). 데모 빌더는 그 구멍을 설계상 넓힌다.

## 1. 왜 주간 인사이트 리포트가 기각됐나 (추론 — 사용자의 말이 아님)

사용자는 이유를 말하지 않았다. 기각 직후 낸 제안이 "데모로 자기 과제에 쓰게"였다는 점에서 기준을 **추론**한다: **산출물은 독자의 다음 행동(고객 PoC·제안서·비용 모델)의 입력이어야 하고, 그 자체가 끝이어선 안 된다.**

이 기준으로 보면 인사이트 리포트는 네 겹으로 실패한다(평가자 2명 공통).
1. 장르가 매일 아침 메일과 같다 — 읽고 끝나고, 손에 남는 손잡이가 없다. 같은 입력(그 주 카드)을 두 번 읽는 과제가 생긴다.
2. 게이트가 새로 인증할 것이 없다 — 교차 기사 "인사이트"는 정의상 원문 어디에도 없는 narration 이고, 이 아키텍처가 가장 불신하는 바로 그것이다. 함의 검증은 "원문이 claim 을 함의하나"의 도구라 "기사 7편을 엮은 통찰이 옳나"에 적용되지 않는다.
3. 단일 `claude -p` 세션이 그대로 만든다 — 캐시된 요약 132개를 넣고 "영역별 인사이트를 써라"면 끝. 파이프라인이 더하는 것은 스케줄과 이메일뿐.
4. 이 독자에게 인사이트는 희소하지 않다 — 희소한 것은 고객 앞에서 쓸 수 있는 **검증된 증거**와 **재현된 숫자**다.

→ 기각은 "잘 못 썼다"가 아니라 "산출물의 종류가 틀렸다"이고, 같은 종류(요약·인사이트)를 어떤 포장으로 다시 내도 같은 이유로 떨어진다. **재제안 금지(§7).**

## 2. 데모 아이디어 평가

### 2.1 재료 — "매주 1개"는 어디까지 참인가 (골든셋 10-17~23, 고유 132편 중 Applied AI 28 + AI Agents 30 = 58편)

평가자마다 엄격도가 달라 숫자가 달랐다. 한 숫자를 고르지 않고 **깔때기**로 보인다(전부 요약·제목 기준 손분류, n = 1주, 원문 미열람).

| 단계 | 편/주 | 비고 |
|---|---|---|
| Applied AI + AI Agents 카드 | 58 | 분야 라벨은 run 때만 붙고 **저장되지 않는다**(의도적 결정) |
| demoable = yes (아키텍처가 드러나고 공개 서비스로 핵심 재현 가능) | 18 (31%) | 장르별 yes = 가이드 9 · 큐레이션 5 · 사례 4 · 발표/보도/연구 0 → **재료는 발행처가 결정**(AWS 블로그·PyTorch KR) |
| ∧ small_aws 이하(Trainium·EKS·GPU 제외) | 10 | |
| ∧ 정량 비즈니스 지표 있음 | 4 | 그중 1편 QUARANTINE(요약 미검증 → 근거로 쓰면 안 됨) |
| 깨끗한 후보 | 3 | Bayer(AgentCore 결정 엔진) · Octave(멀티테넌트 Bedrock) · F&F(LiteLLM 게이트웨이) |
| 5조건 엄격 통과(장르 ∧ 정량 ∧ 공개 코드/명시 아키텍처 ∧ AWS 서비스 ∧ 샌드박스 실행) | **1** | F&F — 그런데 재현되는 것은 F&F 의 기여가 아니라 **LiteLLM 의 문서화된 예산 → 429 기능**이다 |

구조적 관찰 두 가지가 숫자보다 중요하다.
- **공급이 AWS 블로그 발행량에 종속**된다(yes ∧ small_aws 10편 중 AWS ML Blog 6 · AWS KR 4). 연휴·re:Invent 전후로 흔들리고, 독자가 AWS 직원이라 "AWS 직원용 AWS 블로그 다이제스트"가 된다.
- **동결 원문에 코드·링크가 없다.** 운영 source_store 의 후보 24편을 직접 조회한 결과 GitHub 링크 0건·코드 블록 거의 0건, **22/24 가 8,000자에서 절단**(`sources.py:274 MAX_SOURCE_CHARS`). 데모는 "기사 코드 포팅"이 아니라 "산문에서 재구현"이 되고, 그 주 막 나온 기능은 API 를 환각할 위험이 핵심 품질 위험이다. AWS ML Blog 사례 4편(Octave·U.S. Hunger·IskayPet·Bayer)은 라이브 원문에도 GitHub 링크가 0 — 원문이 마케팅 수준이라 사용자가 요구한 "구현 방법"이 원문에 없다.

### 2.2 제외 규칙 — 파이프라인이 `claude -p` 한 세션과 다른 점은 무엇인가

- 원안: **없다.** 세션 하나 + Skill + 그 주 기사 URL = 같은 데모. 더해지는 것은 스케줄과 이메일. PRD 예시 문장과 동형.
- 생존 형태(실무자 제안: 1쪽 패턴 카드 + 기사 메커니즘 1개만 재현하는 최소 슬라이스 + 패턴 원장 + 주기 smoke): 세션 하나가 못 갖는 다섯 속성(cross-family 매니페스트 합의 · 격리 실행 재현 판정 · 주 간 패턴 연결 · smoke 의 BROKEN 전이 · 승인 큐)을 내세웠다. 반박자 판정: 그중 넷은 `/schedule` + Skill + Bash + git 리포(= 원장)로 재현되고, 남는 하나(매니페스트 합의)는 추출·함의 과제라 "얇은 LLM 래퍼(추출)" 유형이며 저장소 데이터가 catch-rate ≈ 0 으로 재는 성분이다. 매니페스트 set/diff 의 불일치는 대부분 명명 정규화("Amazon EKS" vs "EKS")에서 나올 것이고, 정규화 계층이 위양성 243건을 만든 전례(numeric normalization)가 있다.

### 2.3 Codex 역할 — 세 가지 모두 막힌다

| codex 역할 | 판정 |
|---|---|
| author 의 코드를 리뷰·테스트 | Harness Engineering 블로그 패턴 = 기준선 그 자체 → 제외 유형. 빼도 산출물 동일 |
| clean dir 에서 pytest · cfn-lint · dry-run 실행 | 결정론 CI — LLM 자리가 아님 |
| 스펙만 보고 독립 테스트 작성 | 가장 쓸모 있어 보이지만 정확히 테스트 생성 = 제외 유형. 코드를 보면 narration 유출(확인 도장), 안 보면 판정 불가 — 텍스트 claim 과 달리 **독립 근거(동결 원문)가 없다** |
| README 숫자가 기사의 검증 claims 안에 있는지 | 가능하지만 **결정론 lint**(`_interp_lint` 이식)다 — 두 번째 하니스가 필요 없다 |

퇴화점 한 문장: **옳음이 "실행 통과"로 판정되기 시작하는 순간**이 코드 생성 어시스턴트로 넘어가는 순간이다. 옳음은 claim 일치로만 판정되어야 하는데, 그 판정은 코드다.

반박자 자신이 남긴 단서(반박이 완전하지 않은 지점): 46:1 은 요약-claim 함의에서 측정됐고 매니페스트 set/diff 는 더 구조화된 과제라 catch-rate 는 **미측정**; 격리 실행이 cross-family 불일치 신호를 만드는 능력은 단일 세션에 진짜 없다; 희소성 집계는 1주·요약 기반이다. 그러나 **제외 규칙 판정은 이 단서들과 무관하게 성립**한다.

### 2.4 비용 · 실행 경계 · 법률

- **비용(추정, 실측 없음):** 데모 1개 실청구 ≈ $1~4(Claude 만; GPT-5.5 는 현재 $0 청구) · 정가 ≈ $1.5~5.5 · 컴퓨트 ≈ $0.06/빌드(별도 런타임 1h) · 주간 재검증 ≈ $0.1~0.2/주. 주합 ≈ $1~5 = 일간 run 주합(≈ $24)의 +5~25%. 에이전트 시간은 데모당 20~50분(꼬리 60~90분). 다턴 루프 1회가 카드 평균 5배($0.75·449초)를 쓴 전례 → 세션당 비용·시간 상한 필수. **비용은 탈락 사유가 아니다.**
- **실행 경계(진짜 쟁점):** 운영 런타임 execution role 은 `bedrock:InvokeModel*` · `bedrock-mantle:CreateInference` · `ses:SendEmail/SendRawEmail` · `dynamodb Get/Put/Query/Scan/Update/BatchGet`(durable ledger·source-store·users 포함)을 가진다. 운영 `claude -p` 호출 플래그는 `--system-prompt` · `--output-format json` · `--effort` 뿐(`author.py:329-335`) — `--allowedTools`/`--permission-mode` 없음(N2, 제안·미구현). 오늘 author 산출은 텍스트지만 데모는 **실행 가능 코드**로 바꾼다 = 제품에 없던 새 리스크 등급. 공유 회사 계정(≈ $950/일 다른 워크로드). 만약 데모를 만든다면 최소선은 협상 불가: **별도 AgentCore 런타임 + 별도 role(Bedrock·S3 데모 prefix 만) + bwrap `--unshare-net` + 자격증명 env 제거 + 로컬·목(mock)만 + 파이프라인 안 AWS 배포 금지(`cdk synth`/`sam validate` 선에서 정지)**. bwrap `--unshare-net` 이 AgentCore microVM 에서 동작한다는 증거는 codex 의 bundled bwrap 동작뿐 — 스모크 1회 전엔 가정.
- **법률:** high = 기사 성과 수치의 데모 귀속 오해(README 에 "50% 단축"이 적히면 데모 성과로 읽힘 → 구조적 lint: 모든 숫자에 `[기사 Cn]`/`[실측]`/`[가정]` 태그, 두 집합 밖 숫자 BLOCK). medium = 고객 실명(사례 9편 전부 실명 기업 → 제목·패키지명에 조직명 금지, 패턴명으로). medium = AWS Site Terms 파생 이용·2011도3599 요약 판례(README 가 기사 요약·번역이면 다시 걸림). low = 코드 라이선스(동결 원문에 코드가 없어 베낄 것이 없음 — 위험은 라이브 fetch 때 생김).

### 2.5 생존 형태(패턴 카드 + 최소 슬라이스 + 패턴 원장)도 반박된 이유 요약

- codex 가 어느 envelope 에서도 load-bearing 이 아니다(§2.3).
- 토이: 유일한 깨끗한 후보(F&F)의 슬라이스는 LiteLLM 튜토리얼이 되고, Bayer 는 22 에이전트 → 2 에이전트 + 목 → "그래서 80% 는요?"에 답이 없다. aws-samples 에 이미 있는 종류.
- rot: 모델 id 가 2주 안에 Haiku 4.5→5.5·Sonnet 4.6→5→5.5, runtime v47→v61. 주 1 × 52 슬라이스 + "고치지 않는 정책" = 원장이 BROKEN 으로 차오르고 fork 하는 독자는 깨진 코드를 받는다. 현 인력이 현 제품의 운영 꼬리(silent-failure 통지 OPEN, dedup 이 v47~v58 조용히 꺼져 있던 사건)도 못 덮는 상태에서 신규 컴포넌트 10개(effort L, 3~5주 추정).
- pattern identity = Diff-Since-Last 의 "단일 최대 약점" thread-identity 를 그대로 상속.
- 독자 7명 전원이 Claude Code + aws-samples 를 가진 실무자 → 범용 데모의 한계효용이 낮고, 고객 맥락 맞춤은 본인 세션이 더 잘한다.
- 게이트가 막는 **비가역 조치가 없다** — 깨진 슬라이스를 BROKEN 으로 표기하고 둔다는 정책이 그것을 자인한다. 2026-10-18 이후 QUARANTINE 도 ⚠ 달아 발송하므로 새 후보의 verify-before-fire 서사는 기댈 BLOCK 권한이 더 적다.

## 3. 대안 후보 10개 → 상위 3 → 반박 결과

실무자·아키텍트 평가자가 각 5개를 **독립적으로** 냈다(서로의 목록 미열람). 병합 심판의 점수 공식: `composite = 1 + 4 × (제외 승수 × Σ 가중 / 10)`, 가중 = 독자 사용 ×4 · codex load-bearing ×3 · 빈 주에도 발행 ×2 · 노력/비용/리스크 ×1, 제외 승수 PASS 1.0 · PARTIAL 0.85 · FAIL 0.5.

| 후보 | 핵심 | composite | 반박 결과(기본값 = 반박) · 가장 강한 반론 |
|---|---|---|---|
| **Claim 재도출 원장**(재계산 시트 + 재현 원장 병합) | 기사의 정량·재현 가능 주장을 author 와 codex 가 서로의 산출물을 보지 않고 각자 재도출(공식 함수 / 독립 구현), 결정론 3자 대조 → 독자가 고객 숫자를 넣어 재계산 | 4.1 | **반박(확신 4).** 손 세기: 입력과 출력이 모두 원문에 있는 formula claim 은 주 **4편**, 4/4 가 순수 상수 산술(Python 판정) → codex 자리 없음. SA 가 고객 숫자를 대입할 수 있는 것은 Uber 1편. 자문용 페이지라 막을 비가역 조치가 없음. CPU 샌드박스에서 실질 주장을 재현하는 claim 은 PyMuPDF import 스모크 1건. "둘 다 틀릴 때 60% 같은 오답"(U3) 적용 |
| **Verified Build Brief**(검증된 빌드 브리프) | 사례·가이드 1편을 구조화 스펙으로, 모든 필드가 VERIFIED claim id 인용, codex 가 누락 구성요소 열거, 조직 고유 지표 "재현 불가" 라벨 → 독자가 본인 Claude Code 프롬프트로 사용 | 3.4 | **반박(확신 4).** 독자의 Claude Code 가 원문 URL 로 같은 브리프를 **원문 전체 컨텍스트로** 만든다 → 브리프는 손실 압축 중간물이고, 차별점 셋(claim id 결박·누락 검사·원장)은 제품이 스스로 만든 압축 손실을 수리하는 장치. 브리프 필드는 **현 카드 요약에 이미 들어 있다**(재표). `gate.py:61` excerpt 가 이미 동결 전문이라 누락 검사 envelope 는 "전문 + 이름 목록" 한 세션 과제. 운영에 장르 분류기가 없다 |
| **주간 Applied AI 데모(사용자 제안) — 생존 형태** | 패턴 카드 + 최소 슬라이스 + 패턴 원장 + smoke | 2.5 (원안 ≈ 1.7~1.9) | **반박(확신 4).** §2 전체 |
| 가이드 재현·rot 원장("오늘도 돈다" 배지) | 가이드 runbook 을 codex 가 샌드박스에서 실행, RUNS/BROKEN/UNRUNNABLE 시계열 | 3.3 | 드롭(병합 단계) — 배지 1개로 가치 간접, 실행 가능 비율 20~30%, 데모와 같은 실행 경계 리스크 |
| 과제별 증거 대장(Task Evidence Dossier) | 독자가 고객 과제 ≤3개 등록 → 매주 VERIFIED claims 를 과제별 so-what 과 함께 누적 | 3.0 | 드롭 → 브리프의 v2 옵션으로 병합 — codex 자리가 오늘의 NLI 와 동일, O(N×T) 비용 회귀(card-layering §7 Q2 보류 사항), 고객 과제 문장은 민감 |
| 검증 사실 피드(Verified Claims Feed) | VERIFIED claims 를 JSON/MD 로 내보내기 | 2.9 | 드롭 — 제품이 아니라 기반(substrate). **§4 권고 ⓐ 의 재료가 됐다** |
| 발표 주장 사후 추적(Did-it-hold) | 발표 기사의 미래형 주장을 T+30/90 에 HELD/CHANGED 판정 | 2.7 | 드롭 — 판정이 entailment 라 codex 미약, 후속 기사가 13개 매체에 없으면 "미확인" 과다, 읽기형 |

평가자 간 불일치 중 결정적인 것 하나: **codex-as-executor 가 load-bearing 인가.** 실무자 — 슬라이스를 격리 실행해 관측값을 내는 역할은 빼면 author 가 자기 기대를 자기 실행(상관)이라 load-bearing. 아키텍트 — 테스트 실행은 결정론 CI 라 LLM 불필요, codex 가 스펙만 보고 테스트를 쓰는 순간 테스트 생성 = 자동 탈락 유형. 반박자 3명 모두 아키텍트 편에 섰다.

## 4. 살아남은 것 — 권고

### 4.1 ⓐ 검증 증거 공급선 (데모를 뒤집는다)

**무엇.** 제품이 데모를 만들어 보내지 않는다. 대신 이미 배포된 AgentCore Gateway(MCP · Cognito CUSTOM_JWT · us-east-1 · 3도구 byte-identical 검증 완료)에 **독자용 읽기 도구**를 더하고, 독자의 Claude Code 가 그것을 붙여 **검증된 증거를 원문 그대로 끌어가** 고객 맥락의 데모를 만든다.

- 도구(읽기 전용): `search_cards(week, headline)` — 그 주 발행 카드 목록(ledger) · `get_verified_claims(card_key)` — VERIFIED claim 만(`gate.verified_claims` 와 같은 seam, provenance 포함) · 동결 원문은 **기존 `get_source(source_id)`** 그대로. 즉 화이트리스트 3 → 5.
- 독자 쪽 skill(공유 파일 1개): "이 MCP 에서 이번 주 Applied AI 카드를 찾고, 검증된 claims 와 원문을 근거로 1쪽 패턴 카드 + 최소 재현 슬라이스를 **내 고객 맥락**으로 만든다 — 모든 숫자는 `[기사 Cn]`/`[실측]`/`[가정]` 태그". 이 skill 이 없으면 인프라일 뿐이고, 있으면 "데모를 만들어 본인 과제에 쓴다"가 **고객 맥락이 있는 자리에서** 충족된다.

**왜 이것이 제외 규칙을 통과하나.** 30일치 **이미 검증된** claims 캐시 + sha256 내용주소 동결 원문 + 원장은 한 세션이 재현할 수 없는 상태다. CLAUDE.md 가 Gateway 의 진짜 가치를 "author 를 MCP-pull 로 바꾸는 v-next · principal-scope"로 이미 지목했고, 독자의 Claude Code 가 새 principal 이 되면 그 scope 가 실제 의미를 얻는다. 사용량이 **도구 호출 로그로 측정된다**(이메일 열람과 달리) — 모든 후보가 안고 있던 "측정 없이 가치 주장 금지" 문제에 유일하게 답하는 형태.

**정직한 단서.**
- codex 는 여기서도 더 load-bearing 해지지 않는다 — 기존 검증 **결과**를 노출하는 것이지 새 검증 자리가 아니다. 두 하니스 논지는 현 제품의 게이트에서 오고, 이 공급선은 그 게이트의 산출을 독자에게 연결할 뿐이다.
- **guardrail 과의 관계:** CLAUDE.md 의 Gateway guardrail 은 "dispatch 화이트리스트 = retrieval 3도구뿐 → gate/certify/author/freeze 미노출(decorrelation 유지)"이다. 추가 도구 2개는 gate 의 **저장된 결과를 읽기만** 하므로 certifier 가 author narration 을 보지 않는다는 decorrelation 과 무관하다. 그러나 화이트리스트 문구 자체를 넓히는 일이라 **사용자 승인 사항**이다.
- **분야(area) 검색은 넣지 않는다** — area 는 캐시하지 않기로 한 결정(2026-07-27 사고)을 다시 열기 때문. v1 은 주차 + 헤드라인(+ 카탈로그 category) 검색.
- **법률 뉘앙스:** 오늘 메일은 7명에게 **요약**을 보낸다. 동결 **전문**을 도구로 노출하면 B 등급 약관(AWS Site Terms "derivative use") 아래 **사내 전문 재배포**가 된다. 권고 = v1 은 claims + span 발췌 + 정본 URL 만 노출하고 전문 노출은 사용자 결정으로 남긴다. (현 `get_source` 는 fabric·author 용이라 독자 principal 에 열지 말고, 발췌 도구를 따로 두는 쪽이 안전.)
- 주간 산출물이 아니라 인프라다. 사용자가 원한 "데모 1개"가 아니므로 "독자가 데모를 만들 때 쓰는 검증 증거 공급선"으로 포지셔닝해야 한다.
- 노력 S~M 추정: Lambda 핸들러에 도구 2개 + deploy_gateway toolSchema + 독자용 Cognito 클라이언트(client_credentials) + skill 파일 + 호출 로그 집계.

### 4.2 ⓑ 공식 일관성 검사 — certifier 꼬리 (품질 작업, 주간 산출물 아님)

`certifier.py:122` 가 스스로 적은 "공식 재계산(45% = 417M/926M)은 안 함 — 값 존재 대조까지. (formula 재계산은 후속.)"의 후속. claim 이 입력과 파생값(비율·분수·거듭제곱·증감%)을 함께 진술하면 추출기 1개(codex, envelope 4필드만)가 수식 1줄을 내고 **Python 이 평가**해 원문 파생값과 상대오차 비교 → 불일치면 DEMOTED "(원문 산술 불일치)". author 공식 없음, 샌드박스 없음, 웹 UI 없음, 새 원장 없음. **기존 arithmetic 경로·eval-set 머지 게이트는 그대로**(새 규칙은 eval set 에 추가해 catch-rate 비협상 유지). 공급은 주 ≈4건이라 제품이 아니지만 공백은 실재하고 값싸게 메울 수 있다. 함정: 요약의 반올림("약 2초"/"약 55ms" → 36.4 vs 기사 34.2)이 false disagree 를 낸다 → 허용오차 설계 필요(F2 의 교훈).

### 4.3 주간 산출물 슬롯 — 정직한 결론

인사이트 리포트·데모·빌드 브리프·재계산 시트 네 형태가 모두 같은 벽(제외 규칙 + codex 비-load-bearing + 읽기형 회귀)에 막혔다. 반박자가 남긴 마지막 salvage(패턴 증거 색인 — VERIFIED claims 에 서비스·메커니즘 태그를 결정론으로 붙여 주 1회 "이 패턴은 기사 X·Y 의 검증 수치 N건이 뒷받침한다")도 결국 **읽는 산출물**이라 사용자 기준을 통과하기 어렵고, 독립 제품이 아니라 Diff-Since-Last 위의 렌더 한 칸으로만 성립한다. **주간 푸시를 억지로 만들지 않는 것을 권고**한다. 이 독자에게 맞는 cadence 는 "필요할 때 끌어가기"다(§4.1).

## 5. 사용자가 원했던 세 가지와 그 귀착

| 데모의 목적(PRD) | 귀착 |
|---|---|
| 비즈니스 가치 검증 | 조직 고유 결과라 어떤 데모도 재현 불가. 가능한 것은 (i) "재현 불가(조직 고유)" 라벨로 **고객에게 약속하면 안 되는 수치를 가려내기**, (ii) 순수 산술 주장의 일관성 검사(§4.2) |
| 기술 아키텍처 학습 | 현 카드 요약이 이미 구성요소·서비스를 담고 있다(Octave 3층·Bayer Supervisor+LangGraph+AgentCore·F&F LiteLLM 2계층 예산). 부족한 것은 요약이 아니라 **구현 세부** — 그런데 그것은 원문에도 없다(사례 4/4 GitHub 0) |
| 구현 방법 → 자기 과제에 사용 | 고객 맥락이 있는 **독자의 Claude Code** 가 검증 증거를 끌어가 만드는 것이 유일하게 제외 규칙을 통과하는 형태(§4.1) |

## 6. 사용자 결정 사항

1. **방향:** 데모를 뒤집어 "검증 증거 공급선 + 독자용 skill"(§4.1)을 다음 설계 대상으로 삼는가. (아니면 제외 규칙을 사이드 산출물에 대해 사용자가 직접 완화해 데모를 만들 것인가 — 사용자가 PRD 의 소유자이므로 가능한 결정이지만, 그 경우 §2.4 실행 경계 최소선은 협상 불가.)
2. Gateway 화이트리스트 3 → 5 확장 승인(guardrail 문구 수정 포함).
3. 독자 도구가 노출하는 범위: claims + span 발췌 + URL 만(권고) vs 동결 전문.
4. §4.2 공식 일관성 검사를 품질 백로그에 넣는가(주간 산출물과 별건).
5. §7 재제안 금지 목록을 CLAUDE.md/메모리에 반영하는가.

## 7. 재제안 금지 목록(이번 검토 결과)

- 주간 영역별 **인사이트/분석 리포트** — 사용자 기각(2026-10-25) + §1.
- **주간 데모 생성기 원안**(Claude 작성 → Codex 리뷰 → 발송) — PRD 예시 문장과 동형, 제외 규칙 직격.
- **Verified Build Brief** 를 이메일 산출물로 — 손실 압축 중간물. (단, 그 재료인 "검증 claims 노출"은 §4.1 로 살림.)
- **재계산 시트/재도출 원장을 제품으로** — 공급 주 ≈4건·상수 산술·자문용. (certifier 꼬리 §4.2 로만.)
- **가이드 "오늘도 돈다" 배지**·**Did-it-hold 원장**·**과제별 증거 대장(단독)** — §3 드롭 사유.

## 8. 별건 발견 (이 검토와 무관하게 전달 — 조치하지 않음)

1. **동결 원문 8,000자 절단:** 후보 24편 중 22편이 `MAX_SOURCE_CHARS = 8000`(`sources.py:274`)에서 잘렸고 코드·링크가 0건이다. 장문 가이드의 **구현 절반을 사실층이 보지 못한다** — 대표성(representativeness) 이슈. 같은 줄의 주석 "원문은 7일 TTL ephemeral"은 2026-08-01 영구 보존 결정 이후 **stale**.
2. **N2(운영 author 도구 제한) 미구현:** `author.py:329-335` 의 `claude -p` 호출에 `--allowedTools`/`--permission-mode` 가 없고, 컨테이너 이미지의 Claude Code 는 Bash·Write·WebFetch 를 연 채 SES 발송·DDB 쓰기 role 자격증명에 닿는다. 데모 여부와 무관하게 지금 열린 구멍. (workflow 하니스가 운영 분석 출력에서 `--dangerously-skip-permissions` 문자열을 감지해 경고를 남겼다 — 분석가가 "금지" 규칙으로 언급한 문구이며 실행 지시가 아니다.)

## 9. 근거·재현

- workflow run `wf_70384540-44a`(8 에이전트 · 도구 호출 159 · 약 37분). 에이전트별 결과: `~/.claude/projects/-home-ubuntu-Agent-Claude-Code-With-Codex/d7b60b48-5875-47db-872f-00e559cd9a92/subagents/workflows/wf_70384540-44a/journal.jsonl`.
- 재료 분류 원본: 골든셋 `scripts/area_eval/golden_7d.json`(138행·고유 132편, 2026-10-24 스냅숏) → 58편 손분류(요약·제목 기준).
- 비용 기준선: `docs/work_note/Oct-2026/261025-cost-analysis/cost-report.md`(평일 실청구 ≈ $4/일, 기사당 Claude $0.15 · 검증 정가 $0.35, GPT-5.5 현재 $0 청구).
- codex load-bearing 실측: `docs/work_note/Oct-2026/261010-AI-Day-Session-Title/01-research/session-research.md` §U1~U4(12,996 판정: codex 7,474 → BLOCK 1 / Python 5,522 → BLOCK 46; 단서 = 최종 판정 기준, attempts=2 인 66장의 1차 차단은 귀속 불가; U2 cross-family φ 0.389 vs same-family 0.437; U3 둘 다 틀릴 때 60% 같은 오답).
- 제외 규칙 원문: `design/prd/prd.md` "Claude Code 와 Codex 의 Harness 를 사용하여 만들 수 있는 것이면 우리가 만드는 대상에서 제외" · Consideration "(예: Plan/Generate Code: Claude Code, Review : Codex)".
- 코드 지점: `src/briefing/core/verification/certifier.py:122`(formula 재계산 후속) · `src/briefing/core/gate.py:45-56`(숫자 claim → arithmetic 강제 재라우팅) · `src/briefing/core/gate.py:61`(excerpt = 동결 전문 TODO) · `src/briefing/gateway/gateway_handler.py:31-40`(3도구 fail-closed 화이트리스트) · `src/briefing/runtime/deploy_runtime.py:200-228`(execution role).
- prior art(실무자 평가자 WebSearch): Paper2Code/PaperCoder · PaperBench · RECLAIM(주장 단위 재현) · Paper2Agent · SOTAVerified(자기 서술) · aws-samples/serverless-patterns · Well-Architected Generative AI Lens · HF Open-Source AI Cookbook · aws-doc-sdk-examples 테스트 프레임워크(샘플을 살려두는 비용의 척도) · ThoughtWorks Tech Radar(합의 없으면 안 올린다). "뉴스레터 → 주간 실행 리포" 호스팅 서비스는 확인되지 않았다(시장 공백 또는 검색 한계).
