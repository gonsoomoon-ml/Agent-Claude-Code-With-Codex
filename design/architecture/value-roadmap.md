# 가치 로드맵 — '현재 기능 유지'하며 가치 더하기 (Value Roadmap)

> **방법:** 16-에이전트 동적 워크플로우(7개 후보 × 심화→적대 비평 + 완전성 발굴 + 종합) · 2026-06-25 · Korean-friendly
> **핵심 통찰:** 더 많은 가치 = 새 기능이 아니라, 게이트가 *이미 만들고 버리는 3대 폐자원*(① NO_CHANGE 억제분 ② BLOCKED/DEMOTED 더미 ③ 누적 verdict 로그)을 *시간(원장 복리) + amortization(인증자 재사용)*으로 수확.
> **사용자 선택(2026-06-25):** **Tap-to-Source(탭하면 영수증)** 를 다음에 진행. 나머지 후보(Diff-Since-Last 코어 포함)는 로드맵에 그대로 유지(parked).
> **코어 권장(참고):** Diff-Since-Last(인증된 델타) — 본편을 더 짧게, certifier가 각 델타를 독립 재도출. (Verified Quiet은 red-team 후 제외 — §3.)
> **연결 문서:** [`news-agent-differentiation.md`](news-agent-differentiation.md) · [`harness-to-verify-before-publish-mapping.md`](harness-to-verify-before-publish-mapping.md) · [`personalized-morning-briefing-research.md`](../research/personalized-morning-briefing-research.md)


> 한 줄: **아침 본편은 절대 무겁게 하지 않는다.** 모든 가치는 *새 기능*이 아니라 게이트가 *이미 만들고 버리는 자산*에서 — 시간(원장 복리) + amortization(인증자 재사용)으로 — 나온다.

---

## 1. 랭킹 표 — (inclusion-test 강도 × user_value ÷ cost)

점수: inclusion-strength·user_value = 1~5, cost = L(1)/M(2)/H(3). **Score = (incl × uv) / cost**. inclusion-강도는 게이트 4축((a)무게 (b)두-하니스 load-bearing (c)범위 (d)원장-소유)을 얼마나 *자력으로* 통과하는지.

| 순위 | 후보 | incl 강도 | user_value | cost | **Score** | harness | 판정 |
|---|---|:--:|:--:|:--:|:--:|:--:|:--:|
| 1 | **Diff-Since-Last** — 인증된 두 스냅샷 간 델타만 | 4 | 4 | L(1) | **16.0** | partial | **KEEP (코어 · 다음 레이어)** |
| 2 | **Withheld-and-Why (차단 원장 다이제스트)** — 막은 것을 신뢰 산출물로 | 4 | 4 | L(1) | **16.0** | yes | **KEEP / net-new** |
| 3 | **Tap-to-Source (탭하면 영수증)** — verdict 칩 = 감사 창 | 4 | 5 | M(1.3)\* | **15.4** | partial | **KEEP** |
| 4 | **Self-Calibration (자가 보정 스코어보드)** — 시스템 자신을 채점 | 4 | 4 | L(1) | **16.0** → **12.0**† | yes | **KEEP (지연)** |
| 5 | **Prediction Ledger** (보정 축으로 전환) | 3 | 3 | L(1) | **9.0** | partial | **KEEP (deep tier)** |
| 6 | **Verified Q&A** | 3 | 4 | L(1) | **12.0** → **TRIM**‡ | partial | **TRIM (deep tier)** |
| 7 | **Audio/멀티채널** (downgrade-only 불변식만) | 2 | 4 | L(1) | **8.0** | partial | **TRIM (v2 채널)** |
| 8 | **Cross-Source Reconcile (숫자 충돌 칩)** | 3 | 3 | L(1) | **9.0** | yes | **MAYBE (지금 거의 공짜)** |
| 9 | **Confidence-tier render** | 2 | 3 | L(1) | **6.0** | partial | **TRIM (칩에 흡수)** |
| 10 | **Why-Shown (노출 프로필 원장)** | 3 | 3 | M(1.3) | **6.9** | partial | **MAYBE** |
| 11 | **Source-Trust Chip** | 2 | 2 | L(1) | **4.0** | partial | **TRIM→DROP (별칩 금지)** |
| — | ~~Verified Quiet (검증된 침묵)~~ | — | — | — | — | — | **DROP (red-team, §3)** |

\* Tap-to-source는 정적 이메일 펼침은 L이나, top_improvement(탭마다 재-resolve)를 넣으면 M. †Self-Calibration은 가치는 높으나 **원장이 30일 누적돼야** 의미가 생겨 cost를 시간-지연으로 페널티(12.0). ‡Q&A는 단독으로 두 번째 frontier 모델을 정당화 못 해(HARNESS 3) 코어가 아닌 deep tier로 강등 → 실효 TRIM.

**랭킹의 한 줄 해석:** 상위 후보(Diff-Since-Last · Withheld-and-Why · Tap-to-Source)는 모두 **certifier의 *출력*을 소비**한다 — 두 번째 하니스 없이는 구조적으로 존재 불가하고, 아침 본편을 무겁게 하지 않는다(Diff는 *오히려 짧게*). 이것이 inclusion-test 최강 군집이다.

---

## 2. 다음에 설계할 단 1개 레이어 — **Diff-Since-Last (인증된 델타)**

> Verified Quiet(검증된 침묵)이 원래 이 자리였으나 red-team 후 제외(§3). 차순위이자 *코어*인 Diff-Since-Last가 다음 레이어다.

### 왜 이것인가
- **본편을 짧게 만든다.** 어제 본 thread는 풀 재요약 대신 **한 줄 델타 칩**으로 축약하고, 변화 없으면 `NO_CHANGE`로 본편에서 억제 → 어제 읽은 독자는 오늘 *더 적게* 본다. 'every open looks fresh' 회귀 제거 = 과부하 31% 직격, finishability 강화.
- **시간(원장 복리)의 직접 구현.** 하루치 스냅샷을 *사실의 시계열*로 전환 — baseline(Skill+WebSearch+scheduler)이 구조적으로 못 갖는 자체 진화 상태(inclusion test (d) 강함).
- **certifier가 load-bearing.** author가 델타 후보를 라벨링하면, 인증자가 *커밋된 스냅샷에 대해 set/diff를 독립 재도출* → 두 모델이 합의해야 발행. commission(날조된 새 사실)과 omission(놓친 반전) 모두 포착. 단일 모델이면 "이건 새롭다"를 자기가 합리화.

### 무엇을 / author·certifier 인터페이스

```
[오늘 스냅샷]  vs  [어제 커밋 스냅샷]      ← 사실-only store (thread_id 기준)
        ▼
[AUTHOR: Claude]  thread별 델타 후보 + 라벨:
   NEW_FACT / NUMBER_CHANGED 12→30 / STATUS_CHANGED alleged→charged / CONTRADICTS_PRIOR / NO_CHANGE(억제)
        │  최소 컨텍스트 핸드오프(narration 차단): {thread_id, 어제 값, 오늘 원문 구절, 제안 델타}
        ▼
[CERTIFIER: Codex]  같은 커밋 스냅샷에 대해 델타를 *독립 재도출*:
   · 합의             → 발행(델타 칩)
   · 산술/함의 불일치  → 강등 또는 차단(유령 델타 / 놓친 반전 차단)
        ▼  NO_CHANGE는 본편에서 억제(노이즈 0)
```

### 원장 스키마 (사실-only, verbatim 금지)

```
fact_snapshot ( thread_id, user_id, claim, number, status, source_version, captured_date )
delta_record  ( thread_id, user_id, label, from_value, to_value, certified, certified_at )
```

`source_version` 핀으로 supersession 감지. 델타 이력이 누적돼 *시간 복리*(어제 대비가 아니라 "이 스토리 7일 궤적"까지 소유).

### 브리핑 내 UX (본편을 *더 짧게*)
- 어제 본 thread: 풀 재요약 대신 **델타 칩 한 줄**("매출 12→30억", "alleged→charged"). 변화 없으면 본편에서 제거.
- DEPTH: `headline`=델타 칩만 / `standard`=델타 + 1문장 / `deep`=before/after 펼침.

### 가장 큰 약점 (숨기지 않음) — thread-identity
스토리 스레드 동일성이 단일 최대 약점이자 *미해결 upstream 의존*: 과병합→유령 델타, 과소병합→'every open looks fresh' 회귀로 기능 가치 소멸. → v1 수용 게이트를 '존재'가 아니라 **양방향 catch-rate**(유령 델타 precision × 놓친 반전 recall, 라벨 30~50건)로 측정하고, dedup/canonicalization 레이어를 *상시 회귀*로 튜닝. 임계 미달이면 델타를 발행 말고 강등.

---

## 3. DROP할 것과 이유

| 항목 | DROP 이유 |
|---|---|
| **Verified Quiet (검증된 침묵)** — *원래 #1 추천, red-team 후 제외* | (i) 비-사건을 6~10개 출처 창에서 *인증*하는 건, 이 제품이 싸우려는 **과신(over-trust)을 스스로 제조** — 사건보다 *부재*를 grounding하기가 더 어렵다. (ii) RSS 6~10개 커버리지면 `NOT_COVERED`(맹점)를 *매일 광고* → 안심 장치가 불안 장치로. (iii) **harness=yes는 과장**: 커버리지=코드, 새-사실 함의=Diff가 *이미 돌리는* NLI → 새로 load-bearing한 것 없음(실제 partial, Diff의 *렌더*일 뿐). (iv) "안 읽어도 됨" pitch가 리텐션(여는 일수)을 **자가잠식** + 걱정 점호(roll-call)로 anti-calm. **살아남는 최소형 = 기능이 아니라 한 줄 tier**: 사용자가 핀한 극소수(예: 보유종목)에 한해 점호 없이 *"오늘은 조용"* 한 줄(⚠미수집은 숨김). |
| **Source-Trust Chip (별도 칩)** | (i) 정적 allowlist tier = differentiation:160에서 **이미 table stakes** 명시 (모트 아님), (ii) 매체-tint는 doc 전반(22·38·271)이 공격하는 Ground News 안티패턴(CJR 비판), (iii) tier↔grounding 불일치 신호는 *이미* 1차 verdict 칩(VERIFIED/DEMOTED)이 표면화한 것의 재라벨 — 인지 중복. **별 칩 슬롯 자체를 DROP**, 정적 tier는 *보이지 않는 컷오프 필터/정렬 tiebreak*로만 흡수, 불일치는 기존 칩에 변형자 1개로. (명예훼손성 매체-tint 라벨도 제거됨.) |
| **Confidence-tier render (독립 후보)** | differentiation:271·183이 "Trust-Tiered Render"를 **이미 드롭**(멀티채널 렌더 table stakes에 흡수)으로 명시. 진짜 델타(span-level 강등 + 마이크로-라벨)는 *기존 verdict 칩 안에서* 흡수 가능한 개선이지 독립 슬롯 아님. → 칩에 접어 넣고 후보로는 DROP. |
| **Audio "오디오가 제품" 포지셔닝** | 전달은 베이스라인 프리미티브 → inclusion (c) 탈락, Artifact graveyard(264) 직행("깔끔한 전달=table stakes, 독립 destination 앱 지양"). **TTS 렌더러는 v2로 격리**, 살아남는 건 channel-integrity 불변식뿐(아래 4번). |
| **Claim-Split Dispute Ledger** (참고) | 이미 avg 3.0, 가장 무거움(N² NLI·풀텍스트 전매체). Cross-Source Reconcile(산술 충돌만)이 그 *경량 대체재* — 무거운 원본은 범위 밖 유지. |

---

## 4. '지금 거의 공짜로 박을' 묶음 (Diff-Since-Last 코어 위에 amortization으로)

게이트가 *이미 만들고 버리는 3대 폐자원*(① NO_CHANGE 억제분 ② BLOCKED/DEMOTED 더미 ③ 누적 verdict 로그)을 수확하면 추가 추론·수집 ≈ 0:

1. **Withheld-and-Why 주간 다이제스트** — 이미 QUARANTINE되어 폐기되는 BLOCKED/DEMOTED 더미 + 인증자 근거를 opt-in 주간 'show-your-work'로. 실증된 적대적 차단 3/3(23만 vs 230만 자릿수 오류)이 *곧 콘텐츠*. **추가 컴퓨트 0**(거부의 잔열 수확). 별도 cadence라 본편 무게 0. → trust를 마케팅이 아닌 *가시화된 검증 가능 속성*으로 만드는 첫 산출물.

2. **Cross-Source Reconcile 충돌 칩** — 게이트가 *이미 모든 정량 주장에 돌리는* 산술 재도출 결과의 **set 비교만** 추가. 같은 사건 5~10개 출처에서 숫자가 어긋날 때만($2B vs $20B) 칩 + 강등, 화해되면 침묵(노이즈 0). 사용자가 가장 쉽게 속는 실패 모드를 *발행 전*에, dispute ledger의 무게 없이. **추가 = set 비교 µs.**

3. **Tap-to-Source 영수증 (정적 펼침 버전)** — verdict 칩에 펼침을 거는 viewer. 신규 수집 0(span 메타 {source_url, version, char_start/end, entailment_label}만 직렬화, verbatim 비저장). 정적 이메일은 details/summary로 graceful degrade. **본편 0줄 추가**(칩 옆 'source ⌄' 한 글자). → verdict 칩을 "믿어라"에서 "직접 확인하라"로.

4. **Channel-integrity 불변식** (Audio에서 살린 단 한 조각) — downgrade-only 코드 단언: 어떤 채널/푸시도 verdict를 *위로* upgrade 불가(BLOCKED→무음, DEMOTED→음성 칩 의무). 결정론 코드라 LLM 0. 채널 변환이 신뢰를 leak하는 걸 구조적으로 차단. (TTS 합성 자체는 v2.)

5. **Self-Calibration 스코어보드 (씨앗만 지금)** — 감사 레코드에 *이미 누적되는* 두 모델 판정/verdict/provenance를 집계하는 **빈 테이블 + insert만** 지금 박아둔다. 가치는 30일 후 발현(누적 신뢰 곡선)이라 **렌더는 지연**하되, *데이터 적재는 오늘 시작*해야 복리가 돈다("더 많은 가치 = 시간 복리"의 직접 구현, 명예훼손 0 — 자기 시스템 채점).

---

## 5. 시종일관 가드 — 아침 본편은 가볍게

- 모든 추가는 **(꼬리 섹션 | 별도 cadence | 충돌 시만 1칩 | opt-in deep tier)** 중 하나로만. 본편 Smart Brevity(제목→1문장→왜나에게→링크, 5~10개, 완결감)는 *어떤 후보도* 건드리지 않는다.
- **Diff-Since-Last가 본편을 오히려 짧게 만든다** — 반복 노출 thread를 `NO_CHANGE`로 억제하고 변경은 델타 칩 한 줄로 축약 → 'every open looks fresh' 회귀 제거 = manageability 강화. 이것이 다음 레이어인 진짜 이유.
- **blocker 정직 표기:** thread-identity는 Diff-Since-Last의 단일 최대 약점이며 *미해결 upstream 의존*이다 → v1 acceptance gate를 '존재'가 아니라 **양방향 catch-rate**(유령 델타 precision × 놓친 반전 recall)로 측정, 임계 미달이면 델타를 발행 말고 강등.

---

**한 줄 결론:** 다음 레이어는 **Diff-Since-Last** — 어제 이후 *바뀐 것만* 발행해 본편을 더 짧게 만들고(시간 복리), certifier가 각 델타를 독립 재도출해 commission/omission을 모두 막는다. 같은 슬라이스에서 4번 묶음(Withheld-and-Why · Reconcile · Tap-to-Source · channel 불변식 · Calibration 적재)을 폐자원 수확으로 동시에 박는다. (Verified Quiet은 red-team 후 제외 — §3.)

근거 문서(절대경로): `/home/ubuntu/Agent-Claude-Code-With-Codex/design/news-agent-differentiation.md` · `/home/ubuntu/Agent-Claude-Code-With-Codex/design/harness-to-verify-before-publish-mapping.md` · `/home/ubuntu/Agent-Claude-Code-With-Codex/design/personalized-morning-briefing-research.md`
