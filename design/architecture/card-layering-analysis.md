# 카드 2층화 분석 — 공통 사실층 + 렌즈 해석층 (Card Layering & Personalization Balance)

> **방법:** lens 실측 실험 2건(실 `claude -p`, 통제 변수) + 6-에이전트 동적 워크플로우(5관점 병렬 분석 → 적대 반박 → 종합 판정, run `wf_94e64e85`) · 2026-07-06 · Korean-friendly
> **제안(사용자):** 카드를 두 층으로 — **사실층**(원제목 + headline·summary 를 general 로 공통 생성·검증) / **해석층**(why_it_matters 만 lens 별: engineer·business·ai-agent…).
> **판정: `adopt-modified`** — 방향 채택, 원안 그대로는 기각(무가드 해석층 = trust laundering), 본체 착수는 게이트 조건부 권고(확대 실증 + 구독자 손익분기).
> **UPDATE 2026-07-06: 소유자 결정으로 본체 즉시 구현** — §5 구조(사실층 공유 + 가드된 해석층 + 층별 격리)와 §6 의 ⓑ(claim_type 재라우팅)·ⓒ(원제목 출처줄)를 TDD 로 구현, 208 테스트 + 라이브 e2e(사실층 14/14 VERIFIED + engineer 해석 lint PASS + 오탐 회귀 수정) 통과. §6 의 ⓐ(silent-failure 통지)와 착수 게이트의 확대 실증은 여전히 미완 — 게이트는 '착수 조건'에서 '사후 검증 과제'로 전환됨.
> **핵심 통찰:** lens 의 실제 발산 지점은 why_it_matters — lens 가치는 희석이 아니라 **응축**된다. 검증은 (기사, claims)의 canonical 속성이 되어야 하고, 개인화는 검증이 필요 없는 층(선택·해석·형식)에 산다.
> **연결 문서:** [`value-roadmap.md`](value-roadmap.md) · [`news-agent-differentiation.md`](news-agent-differentiation.md) · [`../research/personalized-morning-briefing-research.md`](../research/personalized-morning-briefing-research.md) · `src/briefing/core/`(author·gate·cache·render·lenses)

> 한 줄: **"무슨 일이 일어났나"는 공통, "그게 나에게 왜 중요한가"는 개인.** 사실은 한 번 추출·검증되고(공유 = 기능), 개인화는 검증 대상이 아닌 곳에서 산다 — 이미 신뢰 경계(불변식 #4·skill_md 미열람)가 코드화한 원칙을 생성·캐시 층까지 관철하는 문제.

---

## 1. 계기 — lens 실측 실험 (2026-07-05~06)

**통제된 실험:** 같은 동결본(content-addressed) × lens 3종(general/engineer/business) × skill_md 공백 × 실 author(`claude -p` on Bedrock). 기사 2건: 영문(aws-ml "Bedrock catches AI-generated phishing", 7,996자) + 국문(aitimes "AI 신뢰성 전문가 부족", 1,457자).

| 관찰 | 내용 | 함의 |
|---|---|---|
| **요약 수렴** | 핵심 claims 는 렌즈 간 대부분 동일 사실. summary 는 같은 내용을 어휘만 달리(engineer=기술용어 병기, business=최단·시장어휘) | lens 를 위해 카드 전체를 렌즈 수만큼 재생성하는 것은 낭비 후보 |
| **why 발산** | why_it_matters 가 렌즈 간 최대 발산 — 관점별 해석이 실질 차별점 | lens 가치의 실체는 해석 한 단락에 응축 |
| claims 수 흔들림 | 영문 15/13/11, 국문 9/12/8 (general/engineer/business) | 렌즈가 *사실 추출 집합 자체*를 바꾼다는 반증도 됨(devil 논거) |
| **claim_type 흔들림** | 같은 사실("양성 최소 3년")이 렌즈 따라 `arithmetic`↔`entailment` | 검증 경로가 author 확률 분류에 의존 — 결정론 재라우팅 필요(§6 ⓑ) |
| 언어 반전(수정됨) | engineer lens + 영문 원문 → 카드 전체 영어 출력 | base 계약에 "독자 언어=한국어" 고정으로 해결(`e427c37`, 재배포 완료) |

**주의(devil):** n=2 기사 × 셀당 1샘플 × skill_md 공백 — "요약은 수렴한다"의 일반화 근거로는 부족. 본체 착수 전 확대 실증 필수(§6 게이트).

## 2. 층위 프레임 — 개인화는 슬라이더가 아니라 스택

| 층 | 공통/개인 | 비용 | 근거 |
|---|---|---|---|
| 동결 원문 (source-of-record) | 100% 공통 | O(기사) | 정의상 canonical — 흔들리면 검증 무의미 |
| 사실 추출 (claims·summary) | **공통이어야 함** | O(기사) | 사실이 관점 따라 달라지면 검증의 전제 붕괴 |
| 해석 (why_it_matters) | **코호트 개인화**(lens 4~5종) | O(기사×렌즈) | 실증상 발산이 실제로 일어나는 곳 |
| 편집 취향 (skill_md) | 1:1 개인 | O(기사×사용자) | 가장 비싸고 검증 불가 — 그래서 신뢰 경계 *밖* |
| 선택 (sources·require_ai·depth·send_hour) | 1:1 개인 | ~0 | 결정론 필터 = 공짜 — 체감 대비 최고 효율 |

- **공통성 자체가 기능:** ① 대화 가능성(두 구독자가 같은 사실을 공유 — 사실까지 개인화하면 필터버블) ② Diff-Since-Last 의 전제(렌즈 무관 사실 정본이 있어야 diff 성립) ③ 검증 신호 일관성(같은 기사=같은 "N건 검증"; 현행은 15/13/11 로 사용자마다 다름).
- **신문 비유:** 1면(공통 사실) + 칼럼니스트(lens=페르소나 해석) + 스크랩/여백 메모(skill). 칼럼니스트가 기사 본문을 고쳐 쓰지 않듯 lens 도 사실을 못 고친다.
- **아키텍처 정합:** 이 균형은 이미 코드에 있다 — certifier 는 lens·skill 미열람(불변식 #4), skill_md 는 신뢰 경계 밖(파일 오버레이). 2층화는 그 선을 생성·캐시 층까지 내리는 것.
- **개인화는 에스컬레이션:** 비용 0 인 선택 개인화 + 라벨링("나에게 왜 중요한가 · {lens} 관점")으로 체감을 먼저 만들고, 비싼 생성 개인화(skill 주입)는 부족할 때 올린다. Reuters DNR(리서치 §3.4): 독자가 원하는 건 다른 뉴스가 아니라 더 나은 전달.

## 3. 다관점 평가 (워크플로우 `wf_94e64e85` · 에이전트 6 · 도구 호출 64 · 22분)

| 관점 | 판정 | 효과/실용 | 요지 |
|---|---|:--:|---|
| 신뢰 아키텍처 | support | 4/4 | 렌즈별 재검증은 의도된 중복이 아니라 캐시 키 부산물 — verdict 교차 없음, 신뢰 기여 0. 공유해도 decorrelation 무손상(certifier 는 이미 user-blind) |
| 비용/스케일 | support | 5/4 | N=100 에서 certifier ~79×, N=10k 에서 토큰 ~6,700× 절감. **단 N≈1 현재는 층 분리가 순손실**(카드당 author 2콜) |
| 제품 포지셔닝 | support | 4/4 | lens 가치는 why 로 응축(희석 아님). 원제목 노출 = "요약은 AI, 사실은 원문" 카피의 물증 |
| 독자 UX | **mixed** | 4/4 | 구조는 기존 UX 경계(검증줄=요약, why=해석 시각구분)의 승격이라 정합. 단 개인화 지각 하락 리스크 — 라벨 재정박 없이는 "채택 금지 수준" |
| 반대 심문 (devil) | **oppose** | 2/2 | n=2 일반화 불가 + N≈1 순손실 + silent-failure 통지(백로그 1순위)를 앞설 근거 없음 — **시퀀싱 논쟁에서 승리** |

**만장일치 3건:**
1. **Trust laundering 함정** — why 는 "가장 검증이 필요한 줄"(author.py:57)인데 무검증 해석층으로 빼면, 바로 아래 "✓ 사실 N건 검증" 배지가 미검증 해석에 후광을 찍는다. 원안 그대로 기각의 사유.
2. **해석 B(멀티 lens 병렬)는 이메일에서 기각** — value-roadmap §"아침 본편은 절대 무겁게 하지 않는다" 하드 가드 위반 + Gmail `<details>` 항상-열림 + "나에게"라는 카피 성립 불가. 자리는 웹("다른 관점 보기" 토글).
3. **원제목은 h2 병기가 아니라 출처줄 메타** — `📰 domain · 날짜 · "원제목…" · 원문 →`. 신뢰 앵커(영수증)는 얻고, 클릭베이트 재유입·제목 2줄 스캔 비용·영/한 혼재는 차단.

## 4. 옵션 비교

| | A. 현행 유지(+긴급 수리) | B. 원안(무가드 2층) | **C. 수정 채택안(권고)** |
|---|---|---|---|
| 구조 | 카드 전체를 lens+skill 로 생성, 키=`sha256(source_id\|lens\|skill_md\|model)` | 사실층 general 1회 생성·검증·공유 + why 만 lens 별, **무검증** | 사실층 공유 + **가드된 claim-grounded 해석층**(§5) |
| 신뢰 | claims 안전망 최대 | **치명: trust laundering** | 가드로 차단, 검증줄 커버리지 명시 |
| 비용 | N 선형 — N≈50~100 부터 운영 한계(certifier ~15k호출/일) | N=100 에서 79× 절감 | B 의 절감 거의 보존(가드 ~40콜/일) |
| 판정 | 현 규모 최선·스케일 불가 | 기각 | **adopt-modified, 게이트 후 착수** |

## 5. 권고안 C — 구조

1. **사실층(공유):** 원제목(FrozenSource.title 재사용, 출처줄 메타로만) + general headline·summary·claims 를 **무skill** 로 1회 생성 → claim_type 결정론 재라우팅 → Maker-Checker 검증. 키 = `sha256(source_id|author_model_id|prompt_version)` — lens·skill 제거 = 죽어 있던 캐시 공유 첫 실현. 검증이 (기사, claims)의 canonical 속성이 됨.
2. **해석층(lens):** why 만. 입력 = 동결 원문 + **VERIFIED claims**. 출력 계약 = 근거 claim id 인용 필수 + "검증된 claims/원문에 없는 새 사실·수치 금지". 가드 = 결정론 lint(why 안의 숫자·날짜·고유명사가 claims/원문에 부재 → 실패) + 선택적 entailment 1콜(루프 없음, (source,lens) 공유). 키 = `sha256(source_id|lens|fact_key)` — fact_key 포함으로 사실층 갱신 시 자동 무효화.
3. **층별 격리:** 해석층 실패 → 카드 QUARANTINE 이 아니라 **해석만 강등**(general why 폴백/생략) — 2026-07-02 미발송 인시던트의 격리 교훈을 층 단위로 하강. QUARANTINE 사실층엔 해석층 생성 차단.
4. **렌더·카피:** 요약 라벨에서 lens 제거, 해석 라벨 "나에게 왜 중요한가 · {lens} 관점 (해석)" 로 **개인화 재정박**(UX 채택 조건), 검증줄 "**요약의** 사실 N건 검증" 으로 범위 정직화. 푸터: "AI 에이전트가 원문 기사를 요약하면 다른 AI 에이전트가 원문과 대조해 확인하고, 확인된 요약 위에 {lens} 관점의 해석을 덧붙입니다"("AI 가 쓴다" 금지 준수). title-only depth 예외 처리 필요(§7).
5. **로드맵 상보성:** 공유 사실층 = Diff-Since-Last 스냅샷·Tap-to-Source·Consequence Ledger 의 canonical 저장 지점. 새 lens 추가 한계비용 O(기사) — lens 라이브러리 확장이 싸진다.

## 6. 시퀀싱 — "C 가 옳다"와 "C 를 지금 한다"의 분리

**0단계 (즉시, 층 분리와 무관하게 이득 — devil 의 우선순위 반박 채택):**
- ⓐ **silent-failure 통지** — 기존 백로그 1순위 그대로 최우선(7/2 인시던트 OPEN).
- ⓑ **claim_type 결정론 재라우팅** — gate 에서 claim 텍스트가 숫자 정규식(`_NUM_RE`) 매치 시 author 라벨 무시하고 `arithmetic` 강제; `_to_draft_card` 의 미상→entailment 폴백을 미상→arithmetic 으로(프롬프트 계약 "애매하면 arithmetic" 과 정렬).
- ⓒ **원제목 출처줄 노출** — render.py `_source_line` 에 mono 말줄임 편입. LLM 비용 0.

**착수 게이트 (본체 진행 조건, AND):**
- 확대 실증: 기사 ≥20건 × 카테고리 ≥3 × 셀당 ≥3샘플 × **실사용자 skill_md 포함** — summary 의 의미적 발산(사실 포함 집합 기준) 재측정, 수렴 재확인.
- 손익분기: 출처당 고유 (lens, skill) 조합 ≥2 (현 N≈1 에선 층 분리가 호출 증가 = 순손실).

**본체 (게이트 통과 후):** author 프롬프트 계약 2분할 → gate 경량 가드+층별 격리 → cache 키 2종 → render+카피 → 테스트·e2e 갱신(층별 격리 시나리오 필수) + 캐시 전량 무효화 첫날 재검증 스파이크 예산 + `BRIEFING_DRY_RUN` 리셋 함정 체크.

**후속 트랙(본체와 독립):**
- 해석 B = 웹 아카이브/프로필 "다른 관점 보기" opt-in 토글(푸터 '관점 바꾸기'가 진입점).
- **'ai agent' lens 는 둘로 분리:** (a) "에이전트 빌더(agent-builder)" *사람 페르소나* 렌즈 — `lenses.yaml` PR 로 즉시 추가 가능(불변식 #4 유지; guidance 에 engineer 와의 경계 명시: 도구 사용·오케스트레이션·평가·운영 비용·에이전트 제품화 시사점). (b) 기계 소비용 출력은 lens 가 아니라 **"verified claims feed" 채널** — 검증된 claims 를 가진 이 구조에 특유하게 유리한 v-next 이나 현 Email UX 포커스에서 이탈이라 파킹.

## 7. 미결 질문 (결정 대기)

1. 시퀀싱 동의 — 0단계 3건 먼저, 본체는 게이트 뒤? (권고: yes)
2. skill_md 를 해석층에 넣나 — 빼면 (source,lens) 공유 완성 / 넣으면 "나에게"가 진짜·O(N×S) 회귀. 절충: v1 은 lens 공유, skill 주입은 v2/프리미엄 티어.
3. engineer summary 의 기술용어 병기 등 요약 수준 lens 가치 소실 수용 여부 — lens 차별화를 why 가 홀로 짊어짐.
4. 해석층 가드 수준 — 결정론 lint 만(비용 0) vs +entailment 1콜(~40콜/일). 신뢰·devil 은 후자, 비용은 전자 시작 권고.
5. "{lens} 관점 요약" 판매 문구 포기 + "공통 요약(검증) + {lens} 관점 해석" 프레임 승인 여부.
6. title-only depth 사각지대 — why 1문장 칩 예외 vs lens 사용자 기본 depth 상향.
7. 공유 위양성 blast radius 상쇄(기사 단위 표본 감사·Withheld-and-Why)를 본체 마일스톤에 묶나 후속으로 빼나.
8. "에이전트 빌더" lens 지금 추가하나.

## 8. 근거·재현

- 실험: scratchpad `lens_demo.py` — `uv run python lens_demo.py <source_key> [lens...]` (같은 동결본·빈 skill·실 author). 카드는 author 단계만 = 미검증 초안 기준 비교.
- 워크플로우: run `wf_94e64e85`(5 병렬 분석 + 종합, 산출 = 관점별 findings/risks/variant + 옵션표 + MVP 경로 + open questions). 스크립트·journal 은 세션 산출물 — 재현은 이 문서의 프롬프트 구성(관점 5종 + 공통 사실 컨텍스트: 실증 데이터·캐시 키 구조·렌더 구조) 참조.
- 코드 근거: `core/stores/cache.py:22-28`(card_key 에 skill_md — 공유 0 의 원인) · `core/authoring/author.py:40,57`(core claim 정의·why 주석) · `core/render.py:97,58-73,104`(headline h2·출처줄·title-only 분기) · `core/gate.py`(user-blind envelope·격리·처분).
