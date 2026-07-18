# 요약 품질 + certifier 정규화 + author 타임아웃 — 전달 기록

- **날짜:** 2026-07-18
- **상태:** **COMMITTED (브랜치 `fix/certifier-cross-lingual-numerals`, main 대비 23 커밋) · 미배포**
  — 340 tests passed · ruff clean · 프로덕션은 여전히 구 프롬프트(layered-v2) 가동 중.
- **스펙:** [`docs/superpowers/specs/2026-07-17-represent-v3-prompt-design.md`](../superpowers/specs/2026-07-17-represent-v3-prompt-design.md)
  (v3 설계 — 실제 결과는 아래대로 v3.1 확정·v3.2 revert·v3.3 로 진화. 스펙은 불변 이력이라 미개정, 최종 상태는 이 기록·메모리가 진실.)
- **메모리:** `research-summary-representativeness` · `project-certifier-numeric-normalization` · `project-author-timeout-recalibration`

이 브랜치는 사용자 제보("비-AI 기사가 왔다" → 실은 AI 관련 정상 통과)에서 시작해, **요약이 원문을 대표하는가**라는 질문으로 확장됐고, 그 과정에서 발견된 검증층·페치·지연 결함까지 함께 고쳤다.

## 무엇을 했나 (as-built)

### 1. certifier 산술 검증: 문자열 → **값 대조** (교차언어)
- **문제:** 원문은 영어("eight months"·"four trillion"·"October"), claim 은 한국어("8개월"·"4조"·"10월"). 검증기가 리터럴 "8" 을 찾다 실패해 BLOCK. 실측 13일: BLOCKED **243/243(100%)이 이 위양성**, 진짜 오류 차단 0.
- **수정:** `core/verification/numeric.py`(신규) — 문자열이 아니라 **값**을 비교(자릿수 보존). 네임스페이스 분리(수량/월/서수/퍼센트), 소비 순서+마스킹, 한국어 만/억/조 체이닝, 영어 스케일/분수/배수. 순진한 정규화(영단어→숫자 주입)는 catch-rate 100%→50% 붕괴시켜 **값 대조가 유일 안전책**.
- **적대적 경화:** 워크플로우 검증이 거짓 VERIFIED 를 실제로 뚫음 → 5회 추가 수정(스케일 합성 값 창조·서수↔수량 누수·분모0 예외·관용구 'one'·'5천'/등위생략). 매체 부트플레이트(the-decoder 구독문의 'six times a year')도 동결 원문에서 제거(숫자 알리바이 차단).
- **결과:** 회귀셋(`tests/eval_set/cases.jsonl` 30건, 6개월 빈 슬롯 채움) 위양성 100%→0%·**catch-rate 100% 유지**. 프로덕션 재생 위양성 170→6, 회귀 0. `tests/test_eval_set.py`·`test_numeric.py` = 머지 게이트.
- **정정:** "잔여 BLOCK 6건 전부 위양성" 오판 → 실은 **진양성 1 포함**(원문 "five levels"인데 "7가지"). grep 만 보고 단정한 방법론 오류를 커밋으로 정정.
- 커밋: `0904b85` `23c2dfe` `ff68ebe` `4691661` `1ea7d7a` `4e425d3` `e67ea45` `6c55438`

### 2. SEO 스텁 발행 차단 (동결 원문 하한)
- **문제:** openai.com 이 Cloudflare 로 봇 403 → 전문 추출 실패 → RSS 요약(SEO 메타설명 139~176자)이 동결 원문이 됨. openai 소스 **8/8 이 스텁**, 6~7장 발행("Learn how OpenAI is making ChatGPT safer for teens…" 한 문장). author 완벽·certifier 정확 통과 = **garbage in, verified garbage out**.
- **수정:** `sources.py` `MIN_SOURCE_CHARS=500` 페치 게이트(RSS·HTML 공용, non-silent warn). 임계 근거: 스텁 139~373자 vs 진짜 짧은 기사 604·910자(기자 바이라인 완결). openai 소스 비활성화(우회 금지 방침), admin 프로필 14→13.
- 커밋: `5e3f9bf`

### 3. 요약 계약: represent-v3 → v3.1(확정) → v3.2(revert) → **v3.3**
- **진단(35 에이전트 리서치 + 프로덕션 감사 + 독립 재현):** 병은 길이가 아니라 **lead bias** — 요약이 원문 아닌 *서두*를 대표. 요약 앵커 최심 median 0.61 vs **같은 카드 claims 0.90**(author 는 다 읽었는데 summary 에서만 버림). certifier 는 envelope 4필드만 봐 *누락*을 원리적으로 못 봄 → **생성 계약이 유일 방어선**.
- **v3(f08b741):** 선택 규칙("위치가 아니라 사실의 무게") + 논조·귀속 보존. A/B: lead bias 해결(최심 0.20→0.91·헤지 17%→82%). **단 요약 1,149자 폭증**.
- **v3.1(f5128e1, 확정):** 문장 예산 3~5 재도입("예산이 선택을 강제한다"). A/B+블라인드 이중 검증: 길이 절반(534자), 예산 준수, 대표성·독자·충실도 균형.
- **v3.2(b0cbbbf → revert 12b1805):** "수치는 조건과 한 몸" 규칙. **블라인드 심사에서 효과 없음**(충실도 v3.1 vs v3.2 = 3-3, 핵심 테스트에선 역효과) → revert. *교훈: 블라인드 종합 AI 가 팔 식별을 절반 틀림 → 반드시 ground-truth 매핑으로 재집계.*
- **v3.3(72bae27, 현행):** claims 를 **'원문 전체'→'요약 커버리지'**로 좁힘(타임아웃 근본 수정, §4). 안전망 불변식 보존.
- 부채 청산: base md 의 `{headline}` 요구 vs 출력계약 "제목 금지" 모순 제거, 거짓 "skill 이 길이 정함" 서술 제거, lens 의 '간결히'(새 계약과 충돌) 제거.

### 4. author 타임아웃 근본 수정 (240→360, claims 축소)
- **근본 원인(순차 실측 = 프로덕션 조건):** v3 의 "claims 원문 전체 빠짐없이"가 밀집 기사에서 **24~39 claims** → 지연 240s+ → 카드 유실. *A/B 동시 실행 지연(190~215s)은 부풀려져 못 씀 — 순차로 재야 진짜 타임아웃이 보인다.*
- **수정:** claims = 발행물(요약)의 안전망으로 재정의(v3.3). 요약이 버린 사실은 검증 불필요(독자 미노출). 검증: claims **35→10~22**, 지연 완료 **전부 119~197s**. 안전망 스팟체크 통과(요약 사실 1:1 대응). 타임아웃 240→360(안전 마진).
- **잔여 tail(값으로 못 막음):** 초밀집 연구논문(LaTeX 수식, 예 CARI4D)은 버전 무관하게 >360s → 카드 격리 드롭.
- 커밋: `72bae27` · 진단 도구 `scripts/measure_latency.py`·`verify_timeout.py`(`14727b4`)

### 5. 도구 (재사용 가능)
- `scripts/ab_prompt.py` — 요약 프롬프트 오프라인 A/B(프로덕션 미접촉). 병렬 실행+반복(노이즈 바닥 측정), git 원본 md 재현+토큰 불변식 격리 검증. *교훈: 팔이 실제로 다른지 돌리기 전에 검증(오염 2회 겪음).*
- `scripts/ab_judge.py` — 블라인드 심사 자료 생성(팔 가림·라벨 회전·중앙값 반복·원문 동봉).

## 검증
- `uv run pytest` **340 passed / 4 skipped** · `ruff` clean.
- certifier: 회귀셋 위양성 0%·catch 100% + 프로덕션 재생 회귀 0.
- 요약: A/B(6기사×3반복) + 블라인드 심사(6기사×3렌즈) 이중, ground-truth 매핑 재집계.
- 타임아웃: 순차 실측(밀집 8,000자) 완료 전부 <240s.
- **미배포 검증**(실 브리핑 발송)은 배포 후 몫.

## 배포 상태 — **미배포**
브랜치에만 존재. 프로덕션은 구 프롬프트 가동 중. 배포 시 PROMPT_VERSION `layered-v2`→`represent-v3.3` = 사실층 캐시 전면 무효화(전 카드 재생성). 카나리 불가(fact_card_key 에 user·lens 성분 없음 = 전역 all-or-nothing, kill-switch=전체 revert).

## 잔여 / OPEN
1. **(b) certifier 잔여 구멍** — 적대 검증이 찾은 엣지 케이스 일부 미해결(사용자 postpone). 주요 수정(243→6)은 이 브랜치에 반영됨.
2. **silent-failure 통지** — 타임아웃/실패 카드 드롭이 여전히 무음(warn 만). 초밀집 tail 을 *보이게* 하는 유일한 길. (기존 OPEN 항목)
3. **요약 예산 컴플라이언스** — v3.3 tail 에서 832·665자 요약 관측(예산 ~500자). 타임아웃엔 무해하나 품질 변동.
4. **독자 계측 0건** — "옳은 요약"이 기사 대체인지 티저인지는 CTR 만이 답. `message_id` 이미 sent-log 에 있어 SES ConfigurationSet 로 획득 가능.
5. **openai 소스** — 봇 차단 해제/대체 피드/Browser Tool 전까지 비활성.
