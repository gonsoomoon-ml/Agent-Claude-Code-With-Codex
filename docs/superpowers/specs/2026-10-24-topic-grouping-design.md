# 메일 카드 밴드 — 발행처 → 주제(topic) 묶기 재설계 (설계)

- **상태:** IMPLEMENTED·미배포 (2026-10-25) — 결정 7건 확정(§3), 브랜치 `topic-grouping` 구현·리뷰 완료. 빌더 체크 질문 5건 전부 답(§12). **배포 = U8 ②(요약 모델 관찰) 뒤**(사용자 결정 2026-10-25, §10) — 그때까지 main 미병합.
- **발단:** 사용자 PRD `docs/work_note/Oct-2026/261024-Reorder-Content/reorder-prd.md` — "AI Times 헤드라인은 주제(AI Agents·Models & Releases·Research…)로 묶여 있다. 제공사별 기사도 이렇게 주제로 묶는 것을 검토해봐."
- **선행:** `docs/deliveries/2026-07-08-catalog-publisher-taxonomy-delivery.md`(소스 분류 = 발행처) · `19df96a`(헤드라인 분야 묶음, 2026-10-18) · `4de613a`(오늘의 핵심 3 라벨 호출, 2026-10-20) · `design/ux/email-ux-mockup.md` §5(현행 "분야 = 출처 기준").
- **근거 자료:** `docs/work_note/Oct-2026/261024-Reorder-Content/classify-7d.md`(7일 132편 손분류 표) · `scripts/area_eval/golden_7d.json`(같은 라벨 + 요약 스냅숏 = 머지 게이트 입력).

## 요약

- **무엇:** 메일의 카드 밴드를 **발행처(카탈로그 category)** 에서 **기사 단위 주제(topic)** 로 바꾼다. 6칸, 순서 고정: **AI Agents → Applied AI → Models & Releases → Inference & Hardware → Safety, Security & Policy → Industry & Business**. 헤드라인 칸(AI Times)도 같은 목록·순서.
- **어떻게:** 오늘의 핵심 3 이 이미 매 run 전 카드에 붙이는 라벨 호출에 `area` 필드 하나를 더한다 — **추가 LLM 호출 0**. 라벨 모델만 Haiku 5.5 → **Sonnet 5.5**(`LABEL_MODEL_ID`, 관련성 판정은 Haiku 유지). 실패·부분 라벨은 1회 재시도 → 그래도 불완전하면 **평평한 단일 밴드** 폴백. 메일 모양은 둘뿐.
- **잃는 것·보완:** "AWS 블록" 한눈 보기가 사라진다 → 칸 안 순서 = 카탈로그 순(AWS 맨 위) + 머리 한 줄 `출처 · Amazon (AWS) 7 · Anthropic 6 · …`.
- **검증:** 분야는 사실 주장이 아니라 certifier 가 못 본다 → 골든셋 132편 정확 일치 ≥85%(머지 게이트) + run 마다 CloudWatch 카드별 분야 로그 + 월 1회 표본 점검.
- **건드리지 않는 것:** author·certifier·gate·캐시 스키마·웹 picker·사용자 프로필.

---

## 1. 왜 (intent)

### 1.1 7월 결정과 충돌하지 않는다
2026-07-08 에 "콘텐츠 유형 그룹핑·하이브리드 기각(재제안 금지)"은 **소스(picker)** 를 유형으로 묶다가 Anthropic·Google 이 여러 섹션에 흩어진 문제였다. 소스는 발행처가 하나지만 주제는 여럿이라 소스 단위 주제 묶기는 원래 성립하지 않는다. 이번 요청은 **기사(카드) 단위** 이고, 기사는 (대체로) 주제가 하나다. 웹 picker 의 `category` 는 발행처 그대로 둔다 — `catalog.yaml` 무변경.

### 1.2 데이터가 말하는 것 (7 run · 고유 132편 · 손분류, LLM 아님)
- **장르(어떤 종류의 글)는 발행처가 76% 결정한다.** Decoder=보도 100%, PyTorch KR=큐레이션 100%, AWS=가이드·사례 85%. 장르 밴드는 발행처 밴드의 복사본 → 묶는 축으로 쓰지 않는다.
- **주제(무엇에 관한 글)는 발행처와 독립적이다(발행처로 맞히는 비율 37%).** 새 정보를 주는 축은 주제뿐이다.
- **헤드라인 5분야는 뉴스용이라 카드와 안 맞는다.** 서빙·칩·학습 인프라(32%)가 갈 칸이 없고, Industry & Business 는 카드에서 8편/주뿐이다. 그래서 목록을 물려받지 않고 데이터에서 거꾸로 뽑았다(§4).
- **경계 사례 29%(38/132).** 최다 쌍 = "모델이 어느 플랫폼에서 제공된다"(Models↔Industry) → 규칙 ②로 흡수.
- **발송 규모:** 9/20~10/23 34회, 하루 10~26장(중앙값 21), 6장 미만 0회.

### 1.3 독자
현재 수신자 7명 전원이 AWS 직원(@amazon.com)이고, 현행 섹션 순서(AWS → Anthropic → Google → …, 2026-10-20)는 "우리 회사가 어제 뭘 냈나"를 먼저 보는 읽기였다. 주제 묶기는 이 읽기를 깨는 대신 같은 주제(공식 발표 + 보도)를 한 칸에 모은다 — 사용자가 2026-10-24 에 택한 쪽이다. 장차 외부 구독자에겐 주제 묶기가 더 중립적이다.

## 2. 목표 · 비목표 · 안티목표

**목표**
1. 카드 밴드 = 주제 6칸, 메일 전체(헤드라인 칸 포함)가 한 어휘·한 순서.
2. 추가 LLM 호출 0 — 기존 라벨 호출(핵심 3)에 `area` 를 얹는다.
3. 메일 모양은 결정론적으로 둘: 주제 밴드 / 평평. 어느 쪽인지 규칙이 정한다.
4. 분류 품질을 **측정**할 수 있다(골든셋·run 로그·표본 점검).
5. author·certifier·gate·캐시 스키마 무변경(순서만 바꾼다 — 핵심 3·relevance 와 같은 논거).

**비목표(이번에 안 함)**
- 웹 picker `/catalog` 분류 변경 · 사용자별 `group_by` 스위치 · 헤드라인을 밴드 안으로 합치기 · 분야를 카드 캐시에 저장 · `runtime/supervisor.py` 경로와 `webapi/sample_briefing.html` 갱신 · 해석층(lens) 변경.

**안티목표(동작해도 실패인 것)**
- 검증 카드와 미검증 헤드라인이 한 칸에 섞인다(검증 명세서 정체성 훼손).
- 메일 구조가 날마다 다른 모양으로 나온다.
- 폴백이 조용히 일어난다(warn 없음).
- LLM 이 목록에 없는 칸을 발명하고 그것이 메일에 보인다.
- 라벨 입력에 해석층(why)이 들어간다 — lens 별로 달라 run 내 사용자 간 공유(memo)가 깨진다.
- 원문 수집·author·certifier 코드에 손이 간다.

## 3. 결정 (2026-10-24, 사용자 승인 — 문제 7건)

| # | 문제 | 결정 |
|---|---|---|
| 1 | 축 혼합 — 헤드라인 5분야는 주제 4 + 장르 1(Research) | 밴드 축 = **주제 단일 축**, 장르 배제. 분야 목록은 데이터에서 재설계(§4). |
| 2 | 발행처·장르 블록 상실(독자 7명 AWS) | **A+B**: 칸 안 순서 = 카탈로그 순(AWS 맨 위) + 머리 한 줄 출처 집계. 사용자별 스위치·AWS 강조 표시 안 함. |
| 3 | 주말 1장 밴드 | **그대로 둔다**(접기·"12장 미만 평평" 안 함). |
| 4 | 구조가 날마다 바뀜(실패·부분 라벨) | 1회 **재시도** → 그래도 불완전하면 **평평 단일 밴드** 폴백. 모양은 둘뿐. 호출을 카드 수와 분리하지 않음(6장 미만 0회). |
| 5 | 헤드라인 칸과 소제목 중복 | **A+D**: 같은 어휘 유지(시각 무게로 구분), 두 칸 분류 불일치는 수용. |
| 6 | 분류 검증 불가 | run 로그 · **골든셋 132편 ≥85%** 머지 게이트 · 파서 닫힌 목록 · 월 1회 30장 표본. 라벨 모델 **Sonnet 5.5**(3모델 비교 생략 — 사용자 결정). |
| 7 | ⚠ 카드·사용자 간 공유 | 라벨 호출에 **보이는 카드 전부(PUBLISH+⚠)**, 핵심 3 은 PUBLISH 만(N5). 사용자 간 불일치 **수용**. (memo 키·캐시 미저장은 빌더 기본안 §9) |

## 4. 분야 체계 (areas-v1)

### 4.1 이름·순서·정의 — 영문 이름이 정본(2026-10-18 원칙: 한국어판·영어판 공통 키)

| 순서 | 분야 | 정의(라벨 프롬프트에 그대로 옮긴다) | 7일 분포 |
|---|---|---|---|
| 1 | **AI Agents** | 에이전트 제품·프레임워크·프로토콜(MCP·Agent Skills)·에이전트 코딩·에이전트 평가·벤치마크·샌드박스/격리·에이전트 기술 가이드 | 30 (4.3/일) |
| 2 | **Applied AI** | 누군가 AI 를 *썼다*: 고객·조직 사례(named org 의 자기 업무 적용), 도메인 응용(과학·의료·지구·산업), 운영 실무(게이트웨이·RAG·관측·비용·컴플라이언스·배포 운영) | 28 (4.0/일) |
| 3 | **Models & Releases** | 벤더가 *내놓은* 것: 새 모델·업데이트·성능 비교(언어·음성·이미지·영상), 플랫폼·제품 출시, **모델의 플랫폼 제공(availability)** 발표 | 28 (4.0/일) |
| 4 | **Inference & Hardware** | 서빙 엔진(vLLM·SGLang)·KV 캐시·추론 최적화·온디바이스·학습 인프라·가속기(Trainium·TPU·NPU)·데이터센터 기술 | 25 (3.6/일) |
| 5 | **Safety, Security & Policy** | 보안 사고·공급망 공격·취약점, 정렬/안전 연구·감사·사건 평가, 법·규제·정부 조치 | 12 (1.7/일) |
| 6 | **Industry & Business** | 투자·계약·파트너십·시장 분석·가격 경쟁·인사·조직 소식 | 8 (1.1/일) |

(분류 불가 1편: 제목이 "Announcements" 뿐인 글 — 소스 제목 품질 문제, 별건.)

### 4.2 우선 규칙 (프롬프트에 고정 — 경계 사례 해소용)
1. 에이전트 시스템이 주인공이면 Models·Applied 보다 **AI Agents**(에이전트 제품 출시 포함: Claude Duet·Cowork).
2. "모델/플랫폼이 X 에서 제공된다", 벤더의 새 기능·출시는 **Models & Releases**(Industry 아님).
3. 엔진·칩·학습 도구·추론 성능은 장르(가이드든 발표든) 무관 **Inference & Hardware**.
4. 피해·공격·사고·감사·법은 Agents 보다 **Safety**(능력·벤치마크는 Agents); 돈·계약·시장만 **Industry**.
5. (사례 규칙) named org 가 자기 업무에 AI 를 적용한 글은 그 기술이 에이전트·칩이어도 **Applied AI**(Bayer·W컨셉·Deepgram/Trainium·Laplace 3B/Trainium2) — 단, 기술 자체가 주인공인 가이드는 기술 칸.

### 4.3 헤드라인 칸에 적용
`HEADLINE_AREAS` → 공용 상수(예: `AREAS`)로 교체, 헤드라인 분야 프롬프트의 정의를 6칸에 맞게 다시 쓴다: 칩·데이터센터 **기술** 뉴스 → Inference & Hardware, 칩·데이터센터 **돈** 뉴스(투자·실적) → Industry & Business; 연구 결과 뉴스 → 주제로(과학 응용=Applied AI, 에이전트 연구=AI Agents, 안전 연구=Safety). 빈 칸 숨김은 현행 그대로. 테스트 `test_headline_areas_are_the_five_user_approved_names_in_order` 는 6칸·새 순서로 갱신(사용자 승인 2026-10-24).

### 4.4 기각한 체계(재제안 금지)
장르(콘텐츠 유형) 밴드 · 주제→발행처 2단 밴드 · 7칸(Platforms & Production 분리 — 칸 수 부담) · 5칸(Safety+Industry 합침 — 이질 혼합) · "Research"(장르 이름) 칸 유지 · 카드에 주제 태그만 붙이기(순서가 안 바뀜) · 헤드라인 5분야 그대로 쓰기(Infra 칸 없음).

## 5. 메일 구조

### 5.1 전·후 (예시 = 10-24 발송분 24장)
```
[현행]
오늘의 브리핑 · 10월 24일 (금)                        ✓ 요약은 다른 AI 에이전트가 원문 대조
헤드라인 15건 · 요약 24건 · Engineer 관점 해석
────────────────────────────────────────────────────
◇ AI타임스 헤드라인 15건 · 요약·검증 없음 — 제목과 원문 링크만
   AI Agents 3 / Models & Releases 4 / Research 2 / Policy & Security 3 / Industry & Business 3
◆ 오늘의 핵심 3건
◆ Amazon (AWS) 6건 → ◆ Anthropic 5건 → ◆ Google 3건 → ◆ News & Media 5건 → ◆ Engineering Blogs 1건 → ◆ Community 1건

[제안]
오늘의 브리핑 · 10월 24일 (금)                        ✓ 요약은 다른 AI 에이전트가 원문 대조
헤드라인 15건 · 요약 24건 · Engineer 관점 해석
출처 · Amazon (AWS) 7 · Anthropic 6 · Google 3 · News & Media 5 · Engineering Blogs 2 · Community 1
────────────────────────────────────────────────────
◇ AI타임스 헤드라인 15건 · 요약·검증 없음 — 제목과 원문 링크만
   AI Agents 4 / Applied AI 2 / Models & Releases 3 / Safety, Security & Policy 3 / Industry & Business 3   (빈 칸 숨김)
◆ 오늘의 핵심 3건
◆ AI Agents 4건 → ◆ Applied AI 7건 → ◆ Models & Releases 2건 → ◆ Inference & Hardware 4건 → ◆ Safety, Security & Policy 4건
   (Industry & Business 0 → 숨김 · 칸 안 순서 = AWS → Anthropic → Google → … → 보도 → 커뮤니티 · 번호 칸마다 01부터)

[폴백 — 재시도 뒤에도 라벨 불완전]
◇ 헤드라인 → ◆ 오늘의 핵심 3건(그날 선정이 있으면) → ◆ 요약 21건  (한 덩어리, 카탈로그 순, 전역 번호)
```

### 5.2 밴드 규칙
- 밴드 키 = 카드별 `area`(라벨). 순서 = §4.1. 빈 칸 숨김. **1장 칸 허용**(결정 3).
- 칸 안 순서 = 파이프라인이 준 카드 순서 그대로. 그 순서는 `resolve_sources` 가 카탈로그 순으로 돌려주므로 발행처 카탈로그 순(공식 채널 먼저·보도 뒤·AWS 맨 위)과 같다 — render 는 **안정 분할**만 하면 된다(정렬 금지: 같은 소스 안의 기사 순서를 보존).
- 번호는 칸마다 리셋(현행). 핵심 3 카드는 원래 칸에서 뺀다(현행).
- **출처 집계 줄**(결정 2-B): 부제 바로 아래, 부제와 같은 모노 스타일. 형식 = `출처 · {category} {n} · {category} {n} …`, 대상 = 보이는 카드 전부(핵심 3 포함, ⚠ 포함), `category` = 카탈로그 category 원문(영문), 순서 = 카탈로그 순, 0 은 생략. 결정론(`source_categories` 만으로 계산) — 라벨 실패 날에도 그린다.
- **폴백 모양**: 라벨이 없으면(미호출·실패·불완전) 분야 밴드 대신 **단일 밴드 `요약 N건`**(N = 핵심 3 제외 나머지 — 부제·인장의 어휘 "요약"과 같은 말; "소식"은 헤드라인도 뜻해 모호하다는 2026-10-18 결정 유지), 전역 번호. 핵심 3 이 없으면 밴드 머리 없이 평평(현행 "분야 하나" 경로와 동형). 발행처 밴드로는 돌아가지 않는다(세 번째 모양 금지) — **`card_areas` 가 없거나 None 인 모든 호출자(supervisor 경로·e2e 스모크 포함)가 이 모양을 받는다. 발행처 밴드 코드는 제거한다.**
- 헤드라인 칸·인장·부제·푸터·카드 내부(요약/해석/검증줄/출처줄)는 무변경.

## 6. 라벨 호출 (데이터 흐름)

```
pipeline(사용자 u)
  cards = 보이는 카드(PUBLISH + QUARANTINE)                         # 핵심 3 과 같은 묶음 + ⚠
  labels = label_cards(cards, sections)        ← memo[(source_id 튜플)]  # run 내 같은 묶음 사용자끼리 1회
           ├ 호출 1: Sonnet 5.5, 입력 = 번호. [category] headline ⏎ summary[:300]   (현행 재료 + ⚠ 포함)
           ├ 파싱: 카드마다 {n, org, type, importance, event, area}; area ∉ AREAS 또는 누락 → "불완전"
           ├ 불완전/예외 → 호출 2(동일 입력) → 여전히 불완전 → labels = None (warn: 사유·몇 장)
  top    = assign_top(labels[PUBLISH], sections)  (라벨이 있고 PUBLISH ≥ TOP_MIN_CARDS 일 때 — 현행 규칙)
  areas  = {source_id: area} (labels 가 있을 때만)
  render(cards, …, source_categories, top_picks, card_areas=areas)   # areas=None → 폴백 모양
```
- **seam 교체(설계자 결정, 빌더 체크 Q3):** `TopPickFn(cards, k, sections) -> list[GatedCard]` 를 **`LabelFn(cards, sections) -> list[dict]`**(순수 LLM 라벨, 재시도 포함)로 바꾼다. `assign_top`(핵심 3)과 분야 맵은 **코드**가 라벨에서 만든다. 테스트 fake 는 선택이 아니라 라벨을 돌려준다(`_top_kw` 기반 3종·`test_pipeline` 핵심 3 테스트 갱신).
- **`area` 는 추가 필드다.** `type/org/importance/event` 의 뜻·`assign_top` 의 배분 규칙은 바꾸지 않는다(기존 `applied` type 과 Applied AI 분야는 축이 다르다 — 전자는 핵심 3 티어, 후자는 밴드).
- **핵심 3 회귀 = 관찰(게이트 아님, 빌더 체크 Q1):** 새 프롬프트·새 모델·⚠ 포함 입력은 세 변화가 한꺼번이라 CloudWatch "top picks 선정" 로그와 *같은 선택*을 기대할 수 없다. 대신 골든셋의 10-21~23 세 run 카드 묶음으로 라벨→`assign_top` 을 다시 돌려 ① 선택이 티어 규칙(5대 기업 큰 발표 ≤2·회사당 1·응용 ≥1·섹션당 1)을 만족하는지 ② CloudWatch 와 다른 선택은 사유(org/type 라벨이 바뀜)를 손으로 적는다. `assign_top` 자체는 `area` 를 읽지 않으므로 단위 테스트는 **파서**가 `area` 를 더해도 기존 필드를 그대로 돌려주는지에 둔다.
- **게이트:** 호출 자체는 현행대로 PUBLISH ≥ `TOP_MIN_CARDS`(6) 일 때만. 그 아래(34회 중 0회)는 라벨도 핵심 3 도 없음 → 폴백 모양.
- **결합 비용(새 동작):** 한 호출이 두 기능을 먹이므로, 재시도까지 실패한 날은 **핵심 3 도 함께 빠진다**(현행은 핵심 3 만 빠짐). 재시도 1회가 이 비용을 낮춘다.
- **memo 키** = 보이는 카드 source_id 튜플(PUBLISH+⚠). 프로필이 같으면 1회. 프로필이 갈라져 묶음이 다르면 같은 기사가 사용자마다 다른 칸에 갈 수 있다 — **수용**(결정 7). 분야는 **캐시에 넣지 않는다**(run 당 라벨; 2026-07-27 해석층 캐시 우회 사고 재발 방지).
- **로그(결정 6-①):** run·사용자 묶음마다 warn 한 줄 — 예: `[WARN areas 라벨] model=… | AI Agents 4: 제목…(40자) · … | Applied AI 7: … | 미배정 0 | 재시도 0`. 폴백 때는 `[WARN areas 폴백] 사유 … → 소식 N건`. 핵심 3 "선정" 로그와 같은 채널.

### 6.1 라벨 모델 — `LABEL_MODEL_ID` (Sonnet 5.5)
- 새 설정 `label_model_id` ← env `LABEL_MODEL_ID`, 기본값 = `relevance_model_id`(미설정이면 현행 Haiku 그대로 — additive). `.env` 에 `LABEL_MODEL_ID=global.anthropic.claude-sonnet-5-5` (★ `aws bedrock list-inference-profiles` 등록 문자열 그대로 — 접미사 유무 확인).
- **★ 컨테이너 env 플럼빙 필수:** `deploy_runtime.runtime_env` 는 env 를 화이트리스트로 넘긴다(`RELEVANCE_MODEL_ID` 등). `LABEL_MODEL_ID` 를 넣지 않으면 **프로덕션은 조용히 Haiku 기본값**으로 돈다. 첫 프로덕션 run 의 라벨 로그에 `model=` 을 찍어 증명한다.
- **★ Converse 호환은 '확인 먼저' 작업:** 현행 `_converse_text` 는 모든 호출에 `thinking: {type: disabled}` 를 보낸다. Sonnet 5.5 는 `disabled` 가 400, `temperature` 지정도 400. 라벨 전용 invoke 헬퍼를 따로 두고(관련성 판정 헬퍼 무변경) 모델별 파라미터를 분기한다: Sonnet 5.5 는 `thinking: {type: "between_tools"}`(사고 끔) 또는 adaptive 유지 + 낮은 effort 중 **등록 프로필에 스모크 호출로 확인**한 쪽. thinking 이 켜져 있으면 `maxTokens` 를 사고분까지 넉넉히(현 3000 → 상향) 잡고 텍스트 블록을 탐색해 읽는다(2026-10-17 Haiku 5.5 함정과 동형).
- 비용: run 당 ≈ 입력 4K·출력 1.2K 토큰 ≈ $0.02(재시도 포함 최대 2배). 관련성 판정(기사마다 호출)은 `RELEVANCE_MODEL_ID` Haiku 유지.
- 헤드라인 분야 호출(`make_bedrock_headline_areas`)도 **같은 `LABEL_MODEL_ID`** 를 쓴다(빌더 기본안 — 같은 분류 체계는 같은 판정자; 비용 무시 수준).

## 7. 품질 게이트 (결정 6)

- **골든셋** `scripts/area_eval/golden_7d.json`: 138행(10-17~23 run, 관리자 ledger) = 고유 132편(반복 6행 `repeat_of_earlier_run`), 카드마다 `source_id·card_key·decision·media·category·headline·summary(사실층, 2026-10-24 스냅숏 — card-cache TTL 30일 대비)·area·boundary·alt_old_code·genre`. 분류 불가 1편(`area: null`)은 제외.
- **합격선(머지 게이트, 빌더 체크 Q2 로 정밀화):** 라벨 호출(Sonnet 5.5, 실제 프롬프트·실제 입력 형식, 입력 = 골든셋을 run_date 별 묶음으로 = 실제 호출 크기)을 돌려 **하드 조건 = `area` 정확 일치 ≥85%**(분류 가능한 고유 131장 기준 → 오답 ≤19장, **1회차** 결과). **소프트 조건** = `boundary=false` 카드의 불일치는 건별로 사유를 적는다(0 강제 아님; 정의·규칙 수정의 재료). 2회차는 안정성(1·2회 일치율)만 보고.
- **반복 상한·중단 조건:** 프롬프트(정의·규칙) 수정은 **3회**까지. 3회 뒤에도 85% 미달이면 중단하고 사용자에게 가져간다(모델 비교는 §11 로 금지 — 남는 레버는 임계값·정의이며 그 결정은 사용자 몫). **골든 라벨 수정 상한 = 7장(5%)**: 평가 중 골든셋 쪽이 틀렸다고 판단되는 카드는 사유와 함께 고치되, 7장을 넘으면 같은 라벨러가 자기 라벨을 고쳐 통과시키는 순환이라 사용자 검토로 넘긴다.
- **핵심 3 회귀:** §6 의 `assign_top` 재실행 비교.
- **run 로그 + 월 1회 표본 점검:** 로그에서 30장을 뽑아 손으로 확인, 일치율을 작업 노트에 기록(`scripts/quality_audit.py` 식 정기 지표; 도구화는 선택).
- 골든셋 라벨은 사람(이번엔 Claude 손분류)의 판단이지 정답이 아니다 — 수정은 위 상한 안에서, 사유를 파일에 적는다(불변 역사 아님).
- **헤드라인 칸 임시 점검(빌더 체크 Q4):** 헤드라인은 한국어 제목만 입력이고 골든셋이 없다. 머지 전에 **AI타임스 라이브 피드 50제목 × 2회** 를 새 분야 프롬프트(Sonnet 5.5)로 돌려 ① 미배정 0 ② 2회 일치 ≥90% ③ 50건 손 검토 1회(오분류 수·사유)를 작업 노트에 남긴다. 미달이면 헤드라인 호출만 Haiku·구 정의로 두는 것도 허용(두 칸 어휘는 같아야 하므로 이름은 6칸 공용).

## 8. 구현 접점 (빌더용 touch list)

| 층 | 파일 · 함수 | 변경 |
|---|---|---|
| 분류 체계 | `core/retrieval/headlines.py` `HEADLINE_AREAS` → 공용 `AREAS`(이름·순서 §4.1); `_AREA_SYSTEM` 정의 재작성(§4.3) | 상수 이동·프롬프트 |
| 라벨 | `core/top_picks.py` `_LABEL_SYSTEM`(+area·정의·규칙 §4.1-4.2), `_parse_labels`(area 닫힌 목록 검사·누락 판정), `llm_top_picks` → `llm_labels`(순수 라벨 + 재시도 1회, seam `LabelFn`), `top_source_ids` → `label_cards`(보이는 카드 전부 입력 → memo → 핵심 3 은 PUBLISH 라벨만 `assign_top`, 분야 맵은 전부) | 핵심 변경 |
| 호출 | `core/retrieval/relevance_bedrock.py` 라벨 전용 invoke 헬퍼(모델별 파라미터·maxTokens), `make_bedrock_top_pick`/`make_bedrock_headline_areas` 가 `label_model_id` 사용 | 확인 먼저(§6.1) |
| 설정 | `core/config.py` `Settings.label_model_id` + `load_settings`; `.env`; `runtime/deploy_runtime.py` `runtime_env` 에 `LABEL_MODEL_ID` | ★ 플럼빙 |
| 파이프라인 | `core/pipeline.py` `run_briefing`: 라벨 memo·`card_areas` 계산·render 전달; ⚠ 포함 | |
| 렌더 | `core/render.py` `render_email(..., card_areas=None)`: 밴드 키 분기(areas → 분야 밴드 / None → 평평 `요약 N건`), 출처 집계 줄, **발행처 밴드 코드 제거**. 기존 호출자(`runtime/supervisor.py`·`scripts/e2e_smoke.py`)는 시그니처 호환으로 깨지지 않되 메일은 평평이 된다(supervisor 는 실험 경로 — 허용) | 두 모양 원칙 우선 |
| 테스트 | 갱신: `test_headlines`(6칸 이름·순서), `test_render` 밴드 3종(키=분야), `test_top_picks` 라벨 파서 + `_top_kw` fake 3종(seam 이 라벨 반환으로 바뀜), `test_supervisor_render::test_render_briefing_passes_area_map_and_date`(발행처 밴드 → 평평 `요약 N건`), `test_pipeline::test_run_briefing_top_picks_once_per_card_set_and_rendered_first`(`◆ Anthropic` 단언 → 분야 밴드 또는 평평). 신규: 재시도 1회 → 폴백, 부분 라벨 → 폴백, ⚠ 포함·핵심 3 은 PUBLISH 만, 출처 집계 줄 형식, 폴백 모양(`요약 N건`·전역 번호), 1장 칸 허용, 파서가 `area` 를 더해도 기존 필드 불변 | |
| 평가 | `scripts/area_eval/`: 골든셋 러너(실 호출·일치율·boundary 분해·안정성·핵심 3 회귀) — 머지 전 1회 실행, 결과를 작업 노트에 | |
| 문서 | `design/ux/email-ux-mockup.md` §5("출처 기준"→주제) · `catalog.yaml` 헤더(category = picker 전용 + 출처 집계·칸 안 순서) · `top_picks.py`/`headlines.py` docstring · `docs/README.md` 색인 · 출하 후 메모리 `catalog-publisher-taxonomy` | truth flows up |
| 배포 | `deploy_runtime` 만(런타임 ARN 불변·dry-run 풋건 없음). webapi·web 무변경. 7명 동시 전환(단계 롤아웃 없음 — 결정 2). 첫 run 뒤: 라벨 로그 `model=`·분포 확인 | |

## 9. 빌더에게 맡기는 것 (기본안 표시)
- memo 키·분야 미캐시(§6, 기본안 그대로).
- 헤드라인 분야 호출의 모델(기본안: `LABEL_MODEL_ID`).
- Sonnet 5.5 Converse 파라미터(§6.1 — 스모크로 결정) · `maxTokens` 값.
- 로그 줄의 정확한 형식(§6 예시 준수) · 안정성 합격선.
- 출처 집계 줄의 구분자(" · ")는 예시대로 하되 render 테스트가 고정하게. (폴백 밴드 문구는 `요약 N건` 으로 확정 — §5.2)
- `LABEL_PROMPT_VERSION` 상수 도입 여부(분야는 미캐시라 무효화 용도는 없음 — 평가 결과에 프롬프트 해시를 남기는 용도로만).

## 10. 위험 · 열린 사항
- Sonnet 5.5 가 Converse 에서 `between_tools`/effort 필드를 어떻게 받는지 미검증 — §6.1 확인 먼저.
- 한 호출 실패 = 핵심 3 + 분야 동시 상실(§6 결합 비용) — 재시도로 완화, 로그로 가시화.
- 분류 오류 5~15% 예상치는 추정 — 골든셋 실측으로 대체.
- **배포 시점(사용자 결정 2026-10-25: U8 ② 뒤, 빌더 체크 Q5):** U8 ②(요약 모델 교체 관찰)이 끝난 뒤 main 병합 + `deploy_runtime`. 그때까지 브랜치를 main 에 병합하지 않는다 — 병합하면 U8 ② 의 런타임 배포가 이 변경을 같이 싣는다. 배경: 이 변경은 메일 모양·라벨 모델을 동시에 바꾸고 `deploy_runtime` 은 `.env` 현재값을 통째로 싣는다 — U8 ① 관찰 창에 다른 배포가 섞인 전례가 있어, U8 ② 관찰 **앞/뒤** 를 정해야 한다.
- 부수 관찰(이 설계와 별건): 골든셋 복구 과정에서 관리자 ledger 키 23/138(17%)이 해석층 폴백(미캐시)이었다 — 해석층 lint/실패율 점검감.

## 11. 기각·재제안 금지 (이번 토론)
§4.4 의 체계들 · 사용자별 `group_by` 스위치 · AWS 카드 강조 표시(칩·색) · 1장 밴드 접기("그 밖에")·12장 미만 평평 · 발행처 밴드 폴백(세 번째 모양) · 헤드라인을 분야 밴드 안으로 합치기 · 라벨 호출을 카드 수와 분리 · 모델 3종 비교 실험(사용자가 Sonnet 5.5 로 바로 결정).

## 12. 빌더 체크 (2026-10-24, 별도 리뷰어 — 문서 경로만 전달)
리뷰어 보고: 현행 코드 서술은 전부 정확(`HEADLINE_AREAS`·`_converse_text`·`runtime_env`·`llm_top_picks`·`top_source_ids`·`resolve_sources`), 골든셋 수치 일치, CloudWatch 로그 보존 기간 무기한. 질문 5건과 처리:

| # | 질문 | 처리 |
|---|---|---|
| 1 | 핵심 3 회귀 비교의 합격 기준 — 게이트인가 관찰인가(세 변화가 섞여 "같은 선택" 기대 불가) | **설계자 결정:** 관찰. 티어 규칙 일관성 손 확인 + 차이 사유 기록(§6) |
| 2 | 골든셋 게이트의 "boundary 에 한함"은 하드인가(비경계 오답 0 = 85% 보다 엄격) · 라벨 수정의 순환 | **설계자 결정:** 하드 = 85%(1회차), 소프트 = 비경계 불일치 사유. 프롬프트 반복 3회·골든 라벨 수정 7장 상한, 초과 시 사용자(§7) |
| 3 | `card_areas` 없는 호출자(supervisor)는 발행처 밴드인가 평평인가 · seam 시그니처 변경 여부 | **설계자 결정:** 평평(두 모양 원칙 우선, 발행처 밴드 코드 제거) · seam = `LabelFn`(순수 라벨) 교체(§5.2·§6·§8) |
| 4 | 헤드라인 칸(한국어 제목만) 분류의 합격선 부재 | **설계자 결정:** 라이브 50제목 × 2회 임시 점검(미배정 0·일치 ≥90%·손 검토 1회), 미달이면 헤드라인 호출만 구 모델·구 정의 허용(§7) |
| 5 | 배포 시점 — U8 ②(요약 모델 관찰) 앞인가 뒤인가 | **뒤**(사용자 2026-10-25, §10) — 브랜치 미병합 유지 |
