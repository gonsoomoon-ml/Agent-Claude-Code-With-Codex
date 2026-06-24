# 뉴스 브리핑 에이전트 — 컨셉 & 차별화 보고서

> Claude + Codex 검증 후 발행(verify-before-publish) 하네스 위의, 전문가용 예약 발송형 멀티채널 뉴스 브리핑 에이전트

---

## 1. 요약 (Executive Summary)

### 한 줄 포지셔닝

금융·정책·AI/테크 **전문가**를 위한 **예약 발송형 멀티채널 뉴스 브리핑 에이전트**로, **직무 분리(separation of duties)** 를 품질 보정이 아니라 **제품의 본질**로 삼는다.

- **Claude** = 작성자(author). 보도를 클러스터링하고 원자적 주장(atomic claim)으로 분해해 브리핑을 작성하며, 사용자별 **영속 원장(durable ledger)** 을 소유한다.
- **Codex** = 인증자(certifier). Claude의 추론을 **절대 보지 않고** 원문 구절 + 주장 문자열 + 스키마라는 **최소 컨텍스트**만으로 함의(entailment)·산술·diff·판정을 **독립 재도출**하고, 발행되는 모든 것에 대해 **발행 차단(BLOCK)** 권한을 가진다.

### 무엇이 다른가

리서치가 일관되게 가리키는 단 하나의 미해결 축은 **정확도가 아니라 출처 근거화(source-grounding)·귀속(attribution)** 이다(EBU/BBC: 응답의 45%가 유의미한 결함, **31%가 출처 결함** > 20%가 정확도 결함). 기존 업체는 이 지점에서 모두 무너진다.

| 우리가 하는 것 | 기존 업체가 못 하는 것 |
|---|---|
| **주장 단위(claim-level)** 검증 | Ground News는 **매체(outlet)** 를 좌/중/우로 평가 — 균형 잡혀 보이는 클러스터에도 거짓 주장이 숨을 수 있음 |
| 두 번째 **비상관(uncorrelated) 모델**이 발행 전 모든 엣지를 인증 | Perplexity/Gemini는 문장을 **함의하지 않는 장식적 인용**(37~56% ungrounded, 소송 중) |
| 브리핑을 가로지르는 **재diff 주장/정정/예측 원장** 영속화 | 'Skill + WebSearch + scheduler' 베이스라인이 **구조적으로 가질 수 없는** 자체 진화 상태 |
| **합법적 수집 태세**(GDELT + robots/ToS/EU Art.4(3) TDM 존중 RSS, 변형적 출처 링크) | Bartz/Ross 판례 이후 스크래핑 우선 업체가 **주장할 수 없는** '퍼블리셔 친화적' 포지션 |

핵심 통찰: **신뢰는 마케팅이 아니라 검증 가능한 속성(verifiable property)** 이어야 한다. "우리가 정확하다"로는 차별화할 수 없다(이미 42%가 ~45% 오류율의 AI 요약을 과신함). 대신 **검증을 눈에 보이고 감사 가능하게(audit-first)** 만들어야 하며, 그 메커니즘이 바로 "주장을 쓴 모델이 그 주장을 채점하지 못한다(no marking its own homework)"는 Claude/Codex 분리다.

---

## 2. 경쟁 지형 (Landscape)

| 제품 | 강점 | 공략 가능한 격차 |
|---|---|---|
| **Particle** (2026 best-in-class) | 멀티소스 합성, 'Opposite Sides' + 스펙트럼 차트, 스토리별 Q&A, 출처 링크 노출 | 함의 검증 없음 · **사용자별 메모리 없음**(열 때마다 새것처럼 보임) · 매체 단위 편향만 |
| **Perplexity Discover** | 인라인 인용 UX, 20~50 쿼리 클러스터링으로 스토리 추적 | **인용이 장식적**(문장 미함의) · 환각 귀속 · NYT/News Corp/BBC **소송 진행 중** |
| **Gemini AI Overviews** | 규모·배포 우위 | ungrounded 답변 **37%→56%로 악화** · 전문 'Daily Brief'는 $100/mo Ultra에 잠김 |
| **Ground News** | 5만+ 출처 클러스터링, Blindspot, 편향/팩트성 라벨 | **매체 평가지 주장 평가 아님** · US 중심 좌/중/우 축은 CJR 비판 대상 |
| **Bulletin** | $3.99/mo, AI de-clickbait, Apple 생태계 | 단일 피드 요약기(직접 큐레이션 필요) · 편향 도구 없음 · 합성 아님 |
| **Newsletters** (TLDR AI 등) | 밀도·신뢰·무료 | 대형 런칭일에 리드 스토리 **~80% 중복** — 차별화는 더 많은 recap이 아니라 **POV/개인화** |
| **agentic-news.ai / DIY** | 24/7 모니터링, 'lenses', 인용 Q&A | **검증 없음** · 복잡 작업 30분+ · 우승작 부재 |
| **Artifact** (2024 폐업) | 엘리트 팀, ML 피드, 중복 제거 | **수익 모델 없음** · ~100K 사용자 못 넘김 → 교훈: 깔끔한 요약은 table stakes, 생존은 **지불하는 버티컬 + day-one 매출** |
| **NewsDiffs** (2012~) | 기사 버전 diff | **문자 단위** — 오타와 실질 정정을 구별 못 함 |

**열린 레인(리서치가 명시):** ① 검증된 인용(주장↔출처 함의 게이트) · ② 출처 신뢰도 게이팅 · ③ **주장 단위** 편향/쟁점 · ④ **정정/철회 추적(완전 미해결)** · ⑤ 시간적 staleness/superseded 신호 · ⑥ 불확실성 라벨링 · ⑦ **"이게 나에게 왜 중요한가"의 인과적 관련성**(가장 명확한 미점유 레인).

---

## 3. 우선순위 차별화 요소 (Prioritized Differentiators)

> 점수 = 적대적 평가 3렌즈 평균(NOVELTY / PRACTICALITY / HARNESS NECESSITY), 5점 만점.

### 3-1. Consequence Ledger — 재계산·함의 게이팅된 "이게 당신 업무에 왜 중요한가" · **avg 4.0**

**무엇을 하나.** 사용자의 1차(first-party) 노출 프로필(역할·섹터·보유자산·벤더·지역)에 대해 Claude가 개인화 영향 노트를 작성한다. 모든 정량/인과 주장은 원자화되고, **Codex가 산술을 실행 코드로 재도출**하고 인용 구절에 대해 'so what'을 함의 재검증한다. 재현되지 않으면 불확실 라벨로 **강등(demote)** 하거나 **드롭(drop)** 한다.

**왜 경쟁사를 이기나.** Ground/Particle의 토픽 팔로잉, agentic-news.ai의 검증 없는 일반 'lenses'를 리서치의 가장 명확한 열린 레인(검증 가능한 사실에 근거한 개인화 결과 추론)에서 이긴다. 단일 모델이라면 **그럴듯하지만 틀린 숫자를 confabulate**하는 바로 그 지점이다(Gemini ungrounded 56%, EBU 20% 정확도 결함).

**실전/빌더빌리티.** 검증 코어(Claude 작성 / Codex 산술·함의 재도출)는 라이선스 없이 오늘 in-harness로 동작 — 대부분 오케스트레이션 + 프롬프트 + 코드 샌드박스. 노출 프로필은 1차 사용자 데이터라 수집 비용·법적 노출 0. **구속 조건은 풀텍스트 출처 접근**(인과 'so what' 함의에는 스니펫이 아니라 실제 인용 구절 필요)과 주장별 코드 실행/NLI의 지연·비용.

**Claude vs Codex.**
- *Claude*: 노출 프로필 해석, 영향 노트 초안, 정량/인과 주장 원자화.
- *Codex*: **샌드박스에서 산술 재도출(LLM 자가검증이 아니라 결정론적 실행)** + 인용 구절에 대한 'so what' 함의 게이트 → 재현 실패 시 강등/드롭. 하네스가 load-bearing인 핵심은 **숫자 절반**(산술 게이트); 함의 절반은 단일 모델+NLI로도 상당 부분 대체 가능해 4점.

**점수.** NOVELTY 4 · PRACTICALITY 4 · HARNESS 4 → **avg 4.0**

---

### 3-2. Diff-Since-Last — 당신의 마지막 열람 이후의 검증된 변경 델타 · **avg 4.0**

**무엇을 하나.** 사용자별·스레드별 스토리 상태를 영속화하고 **검증된 델타만** 발행한다: `NEW_FACT`, `CONTRADICTS_PRIOR`, `NUMBER_CHANGED 12→30`, `STATUS_CHANGED alleged→charged`, `NO_CHANGE`(억제). Codex가 커밋된 스냅샷에 대한 **set/diff로 각 델타를 독립 재도출**해 환각된 새로움·누락된 반전을 차단한다.

**왜 경쟁사를 이기나.** Particle/Bulletin은 사용자 메모리 없이 재요약 → "열 때마다 새것처럼 보임". NewsDiffs는 문자 단위라 오타와 실질 변경을 구별 못 함. 이 기능은 **31% 과부하 회피 동인을 직격**한다.

**실전/빌더빌리티.** 쉬운 절반(영속 상태 = SQLite/JSON, 델타 = 결정론적 set/diff)이 가치의 핵심이고 in-harness 즉시 가능. **breaking-news 지연 불필요** — 읽기 시점 on-demand 계산이라 RSS 15~30분 폴링으로 충분. 어려운 절반: **스토리 스레드 동일성**(과병합 시 유령 델타, 과소병합 시 'every open looks fresh' 회귀)과 `NUMBER_CHANGED`/`STATUS_CHANGED`에 필요한 **풀텍스트 본문 접근**. 스냅샷 스키마는 **사실(facts) only, 원문 verbatim 저장 금지**로 변형성·저장 한도 유지.

**Claude vs Codex.**
- *Claude*: 사실 추출, 델타 후보 생성·라벨링.
- *Codex*: 동일 커밋 스냅샷에 대한 **독립 diff 재도출** → 두 모델이 **합의해야** 발행(commission = 조작된 새 사실, omission = 누락된 반전 모두 포착). 영속 상태·dedup·NO_CHANGE 억제는 결정론적 코드라 하네스는 "신뢰 보증"의 핵심이지만 전부는 아님 → 4점.

**점수.** NOVELTY 4 · PRACTICALITY 4 · HARNESS 4 → **avg 4.0**

---

### 3-3. Prediction & Claim Ledger — 주장이 "유지됐는지" 채점하는 예측판 Retraction Watch · **avg 4.0**

**무엇을 하나.** 반증가능 미래 주장('Fed 3월 인하', 애널리스트 가격 목표, 출시일)을 `{주장자, 주장, 해소일, 기준, 구절}` 구조 레코드로 기록한다. 만기일에 **Codex가 사전 등록 기준에 대해** `HELD/FAILED/PARTIAL/STILL-OPEN/UNFALSIFIABLE`를 **최소 컨텍스트**(Claude의 서술이 아니라)로 판정하고, 주장자 트랙레코드를 코드로 재계산한다.

**왜 경쟁사를 이기나.** 전 landscape는 **과거/현재 충실도**(지금 요약이 출처와 일치하나)에 집중 — 어느 누구도 **미래 주장 책무**를 하지 않는다("Follow-the-story-over-time과 corrections tracking은 largely UNSOLVED", "뉴스용 Retraction Watch 부재"). **20% 무력감(powerlessness) 회피자**가 원하는 주체성(agency)을 복원한다. 핵심: 채점 모델이 그 주장을 **쓰지 않았기 때문에** 판정이 신뢰된다.

**실전/빌더빌리티.** 가장 데이터 친화적 — 풀텍스트 본문 불필요(메타데이터 + 헤드라인 + 짧은 구절로 반증가능 주장 추출 충분, GDELT + RSS로 충분). 원장에 쓰는 건 작은 구조 레코드라 Bartz/Ross verbatim/대체재 함정을 **거의 완전히 우회**. 자연스러운 비동기/cron 워크로드라 지연 압력 소멸. **어려운 절반: 만기일 해소 증거 소싱**(naive 웹 그라운딩은 misinformation 세탁, false claim 35%) → 출처 신뢰도 게이팅 필수. + 명명된 주장자의 잘못된 트랙레코드는 **명예훼손성 책임**.

**Claude vs Codex.**
- *Claude*: 반증가능 주장 추출, 해소 기준 사전 등록, 서술.
- *Codex*: 만기일 **독립 판정**(권한 분리 = 트러스트 내러티브의 본질) + 트랙레코드 코드 재계산. 하네스는 **역할 분리 장치**로 load-bearing(자기 예측을 HELD로 합리화하는 퇴행 방지)이나 판정 자체는 rubric-constrained → 4점.

**점수.** NOVELTY 4 · PRACTICALITY 4 · HARNESS 4 → **avg 4.0**

---

### 3-4. Corrections Propagation Ledger — "당신이 읽은 주장이 이후 정정됨" 소급 배지 · **avg 3.67**

**무엇을 하나.** 이미 전달한 사실 뒤의 원문을 **지속 버전 diff**하고 변경을 분류(`CORRECTION / TYPO / STEALTH_RETRACTION / ROUTINE_UPDATE`)해, 그 사실을 서빙한 **모든 과거 브리핑에 배지를 소급 전파**한다. **Codex의 독립 재diff + supersession 함의 검사가 합의해야만** 정정이 발화된다.

**왜 경쟁사를 이기나.** 어떤 shipping 제품도 **소급 정정 전파**를 하지 않는다. NewsDiffs(유일 prior art)는 "오타 수정과 실질 정정/stealth 철회를 구별 못 함" — 정확히 이 분류 레이어가 빠져 있다. 리서치가 "wide open"으로 두 번 명시한 격차.

**실전/빌더빌리티(3점으로 끌어내림).** diff-and-flag 코어와 backward 배지 전파는 빌드 가능하나, **지속적 풀텍스트 재페치**가 (1) 풀텍스트 접근, (2) **Bartz/Ross 이후 가장 방어 어려운 접근 패턴**(고빈도·비유입·verbatim 다중 저장), (3) ~48% AI 크롤러 차단, (4) **자가 정정하는 페이월 매체(NYT 등)가 가장 필요하면서 가장 위험**한 coverage paradox와 정면 충돌. → 협력/라이선스/오픈 RSS 매체 한정 v1로 출시.

**Claude vs Codex.**
- *Claude*: 변경 탐지·분류 초안, 사실↔브리핑 provenance 맵 유지.
- *Codex*: **원본 버전에서 독립 재diff + supersession 함의 검사** → **AND 게이트 합의 시에만** 정정 발화(비가역 trust mutation을 two-key consensus로 전환, 오탐 억제). 역사 수정은 비가역이라 자가 인증 불가 → 하네스 load-bearing이나 ingestion 문제는 못 풀어 4점(렌즈 평균은 PRACTICALITY 3에 눌림).

**점수.** NOVELTY 4 · PRACTICALITY 3 · HARNESS 4 → **avg 3.67**

---

### 3-5. Verified Ask-the-Briefing Q&A — 고정·일자화 코퍼스 위의 함의 게이팅 후속질문 · **avg 3.67**

**무엇을 하나.** 발행 후 후속질문을 **이 브리핑을 위해 가져온 정확한 기사(고정·일자화)** 에서만 답한다. 모든 답변 문장이 주장→구절 인용을 달고, **Codex가 후보 구절에 대해 문장 단위 NLI + liveness/superseded 검사**를 독립 수행해, 함의되는 게 없으면 **기권**("브리핑의 출처가 이를 입증하지 못합니다")을 강제한다.

**왜 경쟁사를 이기나.** Particle 스토리별 Q&A·Perplexity 인라인 인용은 함의 검사를 **안 돌려** 31% present-but-wrong. 작은 주장당 코퍼스가 **무거운 게이트를 SMB 예산으로** 만든다.

**실전/빌더빌리티.** 정의적 한 수 — 검증 대상이 오픈 firehose가 아니라 **이 브리핑의 이미 가져온 ~10~40개 기사**(고정·일자화). 이 스코핑이 비용/법적/freshness 블로커를 모두 녹임: 주장당 NLI가 고정·사소한 워크로드가 되고(SummaC/FENICE/QAFactEval off-the-shelf), 신규 수집 표면 0, '고정'은 freshness의 반대. **약한 솔기: liveness/superseded** — 머신리더블 정정 피드 부재로 얕은 HTTP/last-modified 휴리스틱으로 퇴화해 stealth 정정을 놓침.

**Claude vs Codex.**
- *Claude*: 후보 구절에서 답변 합성, 주장→구절 인용 부착.
- *Codex*: 문장 단위 **NLI 독립 게이트** + liveness/superseded 검사 → 미함의 시 기권. 단, 주장당 NLI는 결정론적 게이트라 **소형 전용 NLI 모델로 치환 가능** → 두 번째 frontier 모델은 helpful-but-substitutable → HARNESS 3점.

**점수.** NOVELTY 4 · PRACTICALITY 4 · HARNESS 3 → **avg 3.67**

---

### 3-6. Claim-Split Dispute Ledger — 함의 검증된 "누가 주장 vs 누가 반박" · **avg 3.0**

**무엇을 하나.** Claude가 클러스터를 **원자적 쟁점 주장**으로 분해하고 매체별 `assert/contest/silent`를 귀속한다. **Codex가 각 인용 구절을 독립 재페치해 결정론적 NLI**를 돌려, 함의 실패한 '매체 X는 Y라 말함' 엣지의 표시를 **거부**하고 재diff 원장에 영속화한다.

**왜 경쟁사를 이기나.** Ground News(매체 단위 tint는 거짓 주장을 가릴 수 있음)·Perplexity(인용이 미함의)를 **주장 단위 검증 귀속**으로 이긴다. 리서치의 명시 격차(매체가 아니라 주장에 쟁점 귀속).

**실전/빌더빌리티(2점 — 가장 무거움).** 단일 클러스터 프로토타입은 즉시 가능하나 **스케일에서 막힌다**: 모든 매체의 **풀텍스트 본문**이 필요한데 GDELT는 메타데이터 only, ~48% 차단 → 페치 불가 매체의 'silent' false-negative가 assert/contest 매트릭스를 조용히 깨뜨림. **주장×매체×문장쌍 NLI** 비용이 breaking-news와 비호환(8주장×15매체 = 클러스터당 120 엣지). 5개의 개별 미해결 문제(클러스터링·분해·귀속·함의 게이트·버전 diff)를 동시에 요구.

**Claude vs Codex.**
- *Claude*: 클러스터 분해, assert/contest/silent 귀속.
- *Codex/결정론 NLI*: 인용 구절 재페치 + **결정론적 NLI 게이트**(미함의 엣지 거부). 단, 함의 게이트는 **소형 MNLI + 코드가 이상적**(결정론·감사성 위해) → 특정 두-frontier-모델 하네스는 over-specified → HARNESS 3점.

**점수.** NOVELTY 4 · PRACTICALITY 2 · HARNESS 3 → **avg 3.0**

---

### 우선순위 요약 + Table Stakes

| # | 차별화 요소 | NOVELTY | PRACT. | HARNESS | **avg** |
|---|---|:--:|:--:|:--:|:--:|
| 1 | Consequence Ledger | 4 | 4 | 4 | **4.00** |
| 2 | Diff-Since-Last | 4 | 4 | 4 | **4.00** |
| 3 | Prediction & Claim Ledger | 4 | 4 | 4 | **4.00** |
| 4 | Corrections Propagation Ledger | 4 | 3 | 4 | **3.67** |
| 5 | Verified Ask-the-Briefing Q&A | 4 | 4 | 3 | **3.67** |
| 6 | Claim-Split Dispute Ledger | 4 | 2 | 3 | **3.00** |

**Table stakes (모트가 아니라 기본기 — 없으면 출시 불가):** 크로스아웃렛 스토리 클러스터링 + 신디케이션 dedup · 출처 링크 노출 멀티소스 요약 · 예약 발송 + 멀티채널 렌더(email/Slack/markdown/HTML) · TYPE/BRAND/DEPTH Skill 구성 · **합법적 수집 스택**(GDELT + robots/ToS/EU Art.4(3) TDM 존중 RSS + readability) · 출처 신뢰도 게이팅(NewsGuard식 allowlist + known-false 핑거프린트) · 사용자별 영속 프로필/상태 저장 + 'seen' 캐시 · de-clickbait 헤드라인 정규화 + 차분한 anti-doomscroll 기본 표면.

---

## 4. TYPE / BRAND / DEPTH Skill 구성 매핑

모든 차별화 요소는 단일 Skill 구성 표면 위에서 동작한다.

### TYPE (도메인 스키마)
버티컬을 정의 → 노출 프로필 스키마와 클레임 추출 어휘를 결정.
- `finance`: 보유자산·티커·금리 노출 → **Consequence Ledger**가 mortgage/포트폴리오 델타 산술, **Prediction Ledger**가 애널리스트 가격 목표·Fed 결정 추적.
- `policy`: 관할·규제·이해관계자 → **Claim-Split Dispute Ledger**가 쟁점 정책 주장의 assert/contest, **Corrections Ledger**가 alleged→charged STATUS 추적.
- `ai-tech`: 벤더·출시일·벤치마크 → **Prediction Ledger**가 ship-date/roadmap, **Diff-Since-Last**가 모델/제품 스레드 델타.

### BRAND (편집 보이스)
톤·채널 페르소나·표면 밀도. 차분·anti-doomscroll 기본이 **40% 뉴스 회피자**용 manageability를 충족. **신뢰 신호(verdict 칩: VERIFIED / DEMOTED-TO-UNCERTAIN / BLOCKED)는 BRAND와 무관하게 항상 노출** — "show your work"는 협상 불가.

### DEPTH (verbosity tier)
헤드라인 ↔ 풀 확장. 동일 검증 상태를 다른 밀도로 렌더(검증은 업스트림 1회, 렌더는 trust state를 절대 leak하지 않음).
- `headline`: 검증된 델타 + verdict 칩만.
- `standard`: Consequence 노트 + Diff-Since-Last + 인용.
- `deep`: **Claim-Split Dispute Ledger** 전개(쟁점 ledger의 deep tier), **Ask-the-Briefing Q&A** 활성화, Prediction 트랙레코드 스코어보드.

> 드롭된 후보들(Story-Thread 온보딩 catch-up, Steelman Duel 등)은 독립 슬롯이 아니라 **DEPTH 상위 tier 또는 cross-cutting UX**(confidence 칩)로 흡수된다.

---

## 5. 구체적 MVP 슬라이스 + 검증 후 발행 게이트 설계

### 5-1. 첫 출시로 무엇을 빌드해 차별화를 증명하나

**MVP = `finance` 버티컬 · Diff-Since-Last + Consequence Ledger · 큐레이션된 robots-friendly 풀텍스트 RSS 6~10개.**

이 슬라이스를 고르는 이유:
1. 두 기능 모두 **avg 4.0** — 가장 높은 점수, 하네스가 진짜 load-bearing.
2. **풀텍스트 의존을 한 줌의 협력/오픈 RSS 매체로 한정** → Bartz/Ross·~48% 차단 문제를 데모 단계에서 회피.
3. **breaking-news 지연 불필요**(둘 다 읽기 시점 on-demand) → GDELT 15분 + 적응형 RSS 폴링으로 충분.
4. **지불하는 버티컬**(금융 전문가)에 day-one 매출 wedge — Artifact의 죽음 회피.

**빌드 순서:**
1. **합법적 수집 + dedup**(table stakes): GDELT 메타데이터 + 큐레이션 RSS + readability 추출 + 'seen'/클러스터 캐시.
2. **사실-only 스냅샷 스토어**(SQLite): `{thread_id, claim, number, status, source_version, date}` — verbatim 금지.
3. **Diff-Since-Last 엔진**: 스냅샷 set/diff → 5개 델타 라벨.
4. **Consequence Ledger**: 1차 노출 프로필 + 산술 노트 초안.
5. **멀티채널 렌더**: email/Slack/markdown, verdict 칩 포함.
6. **소형 적대적 평가셋**(v1 acceptance gate): 라벨된 실제 반전/정정 ~30~50건으로 델타 분류기가 rubber-stamp가 아님을 증명.

### 5-2. 검증 후 발행(verify-before-publish) 게이트 설계

```
[Claude: 작성자]                          [Codex: 인증자]
보도 클러스터링                            ── 최소 컨텍스트만 수신 ──
  ↓                                        (원문 구절 + 주장 문자열 + 스키마)
원자적 주장 분해                            Claude의 추론은 절대 전달 안 함
  ↓                                              ↓
브리핑 초안 + 델타 라벨        ────────▶   독립 재도출:
  ↓                                         · 산술 = 샌드박스 실행 코드
영속 원장에 사실 커밋                        · 함의 = NLI / supersession
                                            · diff = 커밋 스냅샷에 대한 set/diff
                                            · 판정 = HELD/FAILED/… rubric
                                                 ↓
                                       ┌── 합의(AGREE)? ──┐
                                       │                  │
                                     YES                 NO
                                       │                  │
                                  ✅ 발행          ⛔ BLOCK / 강등(DEMOTE)
                                  VERIFIED 칩        · 산술 미재현 → 드롭
                                                     · 함의 실패 → 기권 라벨
                                                     · diff 불일치 → 억제
```

**게이트 원칙:**
- **최소 컨텍스트 인증.** Codex는 Claude의 narration을 절대 받지 않음 → 상관 오류(correlated error) 최소화, "자기 채점 금지" 보장.
- **AND 게이트 = precision 우선.** 비가역 trust action(정정 소급, 트랙레코드)은 **두 모델 합의 시에만** 발화. recall을 희생해 오탐(잘못된 배지)을 막음.
- **결정론적 검증 우선.** 산술은 샌드박스 코드, 함의는 가능하면 pinned NLI(SummaC/FENICE)로 — 감사성(reproducibility)을 위해 frontier-LLM 판정보다 byte-stable 결정론 게이트 선호.
- **세 가지 출력 상태**가 신뢰 UX: `VERIFIED` / `DEMOTED-TO-UNCERTAIN` / `BLOCKED` — 모델 발산(divergence)을 숨기지 않고 confidence 칩으로 노출.

---

## 6. 솔직한 리스크 + 완화책 (Risks & Mitigations)

### 데이터 / 법무
| 리스크 | 완화책 |
|---|---|
| 함의 게이트에 **풀텍스트 본문** 필요하나 무료 API는 메타데이터/truncated only, full-text RSS 축소 | 협력/라이선스/오픈 풀텍스트 RSS **소수 매체로 v1 한정** · 스냅샷은 **사실-only**(verbatim 금지)로 변형성 유지 |
| **Bartz/Ross**: 수집 방법이 dispositive. 지속 재페치(Corrections)는 가장 방어 어려운 패턴 | robots.txt/ToS/EU Art.4(3) TDM **per-user-agent 존중** · 변형적·출처 링크·비대체 태세 · 지속 재페치는 협력 매체 한정 |
| ~48% 매체 AI 크롤러 차단 → 합법 coverage가 보이는 것보다 작음 | 'silent' false-negative를 **coverage 한계로 명시 라벨** · GDELT + Web NGrams/BigQuery 폴백 |
| 명명된 주장자의 잘못된 트랙레코드 = **명예훼손성 책임** | 사전 등록 기준 + UNFALSIFIABLE/PARTIAL 보수 라벨 · 콜드스타트엔 스코어보드 비표시 |

### 비용 / 지연
| 리스크 | 완화책 |
|---|---|
| 주장당 NLI + Codex 코드 실행이 compute-heavy(인큐번트가 건너뛰는 이유) | 게이트를 **작은 코퍼스/고가치 스토리/변경된 기사에만** 적용 · 공격적 캐싱 · 소형 전용 NLI · breaking-news SLA 포기(비동기 브리핑) |
| 두-frontier-모델 + 샌드박스가 thin B2C ASP($4~15/mo)와 충돌 | **지불하는 전문 버티컬**(금융/정책/법률)에 가격 책정 — 일반 B2C 앱 아님 |

### 신규성 / 모트
| 리스크 | 완화책 |
|---|---|
| 사용자 가시 후크(개인화 'why this matters')는 commoditized, 신규 절반(코드 재도출·함의 게이트)은 보이지 않는 백엔드 | 모트를 **영속 원장(durable ledger)** — 베이스라인이 구조적으로 못 갖는 자체 진화 상태 — 으로 이동 · 검증 상태를 **가시적 verdict 칩**으로 표면화 |
| 인큐번트(Particle/NewsGuard)가 분기 내 fast-follow 가능(구성품 off-the-shelf) | 모트 = 실행 속도 + **권한 분리 아키텍처** + 라이선스/합법 수집 태세(스크래핑 우선 업체가 주장 불가) |
| "두 모델 = 신뢰"는 마케팅상 취약(결정론 NLI가 실제 인증자) | **결정론 게이트를 헤드라인으로** · 비가역 trust action의 권한 분리를 핵심 내러티브로 · independence는 **authorship 분리**로 명확히(통계적 독립 과장 금지) |
| 스토리 스레드 동일성 = 미해결 upstream 의존(과/과소 병합) | dedup/canonicalization 레이어 지속 튜닝 · 소형 적대적 평가셋을 v1 acceptance gate로 |

### 사업 (out-of-lens이지만 gating)
- **Artifact graveyard**: 깔끔한 요약은 table stakes. 생존 = 지불 버티컬 + day-one 매출 + **attention이 이미 있는 곳**(inbox/Slack/브라우저)에 거주 — 독립 destination 앱 지양.

---

### 부록: 왜 이 6개인가 (드롭 근거 요약)
- **Steelman Duel / Spectrum & Correction Watch / Claim-Level Dedup**: Claim-Split Dispute Ledger·Corrections Ledger와 중복 → deep DEPTH tier 또는 table stakes로 흡수.
- **Disagreement Surfacer**: 하네스의 일반 작동 원리(모든 차별화가 이미 Claude-vs-Codex 발산을 노출) → cross-cutting confidence 칩.
- **Durable Interest Model / Story-Thread 온보딩 / Two-Voice Audio / Trust-Tiered Render**: 각각 출처 게이팅·Diff-Since-Last·멀티채널 렌더 table stakes에 흡수.

---

*31개 에이전트 리서치 워크플로우로 생성(4개 영역 경쟁 지형 웹 리서치 → 6개 렌즈 17개 차별화 후보 → 컨셉 압축 → 각 3개 적대적 평가 → 종합). 심사별 상세 투표·출처는 워크플로우 트랜스크립트에 보관됨.*
