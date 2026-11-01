# #6 — 해석층 lint 폴백: lens 해석이 사실층 why 로 조용히 대체됨 (문제 정의, 2026-10-31)

> 상태: **정의 기록 · dive-in(원인 상세·선택지) 미착수 — 사용자 검토 대기.** 저장소 코드 무변경.
> 측정 도구: `tools/interp_lint_cases.py`(WARN 의 "밀수 토큰"을 원문·검증 claim 과 값 기준 대조, 읽기 전용 DDB).

## 1. 무엇이 일어나는가

해석층(lens 별 "왜 중요한가")은 발행 전에 결정론 lint(`gate._interp_lint`)를 통과해야 한다. 규칙 ④ = *why 의 모든 숫자 토큰이
(동결 원문 ∪ VERIFIED claim) 에 있어야 한다*(trust laundering 차단 — "✓ 검증" 카드에 미검증 수치가 실리면 안 됨).
실패하면 카드는 죽지 않고 **사실층(일반용) why 로 폴백**한다 — `[WARN gate interp] <sid>: lint 실패(…) → 사실층 why 폴백`.

## 2. 관찰 (CloudWatch, 2026-10-21~30 정기 run 10회)

| 항목 | 값 |
|---|---|
| 폴백 카드 | 28장 (run 당 2.8장) — 시험 발송 run 포함하면 WARN 35줄 |
| 10-21~23 (요약·해석 모델 교체 전) | 14장: "why 빈값" 11 · "based_on 인용 무효" 2 · "미검증 수치 밀수" 1 |
| 10-25~30 (runtime v62, Sonnet 5.5 medium 이후) | 14장 (run 당 2.3장): **전부 "미검증 수치 밀수"** |

- "why 빈값"은 모델 교체 뒤 0건 → 현재 문제 아님.
- 수신자 7명 전원 lens = `engineer`(DDB briefing-users) → 카드당 해석 1회, 폴백 1건 = 7명 모두 같은 손실.

### "미검증 수치" 토큰 분류 — 33개(카드 20장 중 18장 복원; 2장은 시험 발송 run 이라 관리자 ledger 에 없음)

값 기준(`numeric.scan`, certifier 와 같은 비교기)으로 원문·VERIFIED claim 에 있는지 확인:

| 분류 | 개수 | 뜻 |
|---|---|---|
| **표기 불일치** | 22 (67%) | 값은 원문에 있는데 표기가 달라 토큰 비교에서 걸림 |
| **원문·claim 에 없는 수치** | 11 (33%) | 해석이 만들었거나 계산한 값 — 가드가 맞게 막은 경우 |

표기 불일치의 전형:
- 원문 "98.8 percent" / "up from 96.2 percent" ↔ 해석 "98.8%"·"96.2%" (GPT-6.1 Terra, 10-27)
- 표 셀 "13.53 | 10.22" (단위 % 는 표 설명에) ↔ 해석 "13.53%"·"10.22%" (Granite Speech 5.0, 10-22 — 6개 토큰 전부)
- 원문 "ten percent" ↔ 해석 "10%" (Anthropic S-1, 10-26)
- 원문 "cut the error rate from 30.8 to 23.8 percent" ↔ 해석 "30.8%"·"23.8%" (Nemotron 3.5 Transcribe, 10-28)
- 원문 "64 percent more output tokens" ↔ "64%" (Gemini 4 Carbon, 10-28) · "moved 10 percent … jumped 20 percent" ↔ "10%"·"20%" (Quick User Group, 10-30)

원문에 없는 수치의 예: '70'(OpenAI 할인 기사, 10-25) · '163'(Anthropic S-1) · '49'(OpenSandbox) · '20'·'9'(Claude for Financial Advisors) · '3'·'4'(LLM 신규성 판정 연구).
★ '1'·'3'·'4' 같은 작은 정수는 "3가지 이유"·"1단계" 같은 **열거**일 가능성이 있으나, 폴백된 해석 본문은 어디에도 저장되지 않아 확인 불가(WARN 에 토큰만 남음).

### 카드별 원자료 (tools/interp_lint_cases.py 출력 요약)

| run | 카드 | 토큰 → 분류 |
|---|---|---|
| 10-21 | U.S. Hunger / Amazon Quick | 1 → 표기(말로 쓴 수) |
| 10-22 | Granite Speech 5.0 | 10.22% 11.79% 13.53% 28.48% 30.50% 6.48% → 전부 표기(표 셀) |
| 10-24 | Block Dessa | 6 → 없음 |
| 10-25 | OpenAI discounts | 70 → 없음 |
| 10-25 | Jack Clark prediction | 55% 85% → 표기("55 percent") |
| 10-25 | OpenSandbox(AAIF) | 49 → 없음 |
| 10-26 | Bedrock Knowledge Base agentic retrieval | 8 → 없음 |
| 10-26 | Anthropic S-1 | 10% → 표기("ten percent") · 163 → 없음 |
| 10-26 | Meta $95B stock sales | 10 → 표기(말로 쓴 수) |
| 10-27 | LLM novelty judges | 1 → 표기 · 3, 4 → 없음 |
| 10-27 | GPT-6.1 Terra | 3 → 표기 · 96.2% 98.8% → 표기("percent") |
| 10-27 | Claude for Financial Advisors | 20, 9 → 없음 |
| 10-28 | Nemotron 3.5 Transcribe | 23.8% 30.8% → 표기 |
| 10-28 | Gemini 4 Carbon | 64% → 표기 |
| 10-28 | Claude drug development | 4 → 표기(말로 쓴 수) |
| 10-29 | LiteRT Play services | 1 → 없음 |
| 10-29 | Mistral Le Chonk | 11 → 없음 · 8 → 표기 |
| 10-30 | UK Amazon Quick User Group | 10% 20% → 표기 |

## 3. 왜 문제인가

- 폴백은 그 카드의 lens 해석 한 단락(interp-v1.2 의 "요약이 버린 것" 통찰, 2026-07-28 실증 통찰률 4→36%)을 **조용히** 버린다. 독자는
  일반용 사실층 why 를 보고, 무엇이 빠졌는지 모른다. 하루 2장쯤, 그중 약 2/3 는 해석이 틀리지 않았는데 버려진 것.
- lint 는 숫자 **토큰 문자열**(`_NUM_RE` = `\d[\d,]*(?:\.\d+)?%?`)을 비교하고 certifier 는 **값**(`numeric.scan`)을 비교한다 —
  같은 파이프라인 안에서 "같은 수치"의 정의가 두 가지다. 영어 원문은 백분율을 "percent" 로 쓰고 해석은 한국어 관행대로 "%" 를 붙이므로
  구조적으로 자주 어긋난다.
- 나머지 1/3 은 가드가 제 역할을 한 경우라 **가드 제거는 답이 아니다.** 원문에 없는 수치가 "✓ 검증" 카드에 실리는 것은 이 제품의 핵심
  신뢰 속성을 깬다.

## 4. 범위

- **안:** `_interp_lint` 규칙 ④(숫자 비교 방식)와 폴백의 독자 손실 · 열거 숫자('3가지')를 사실 수치와 구분할지.
- **밖:** 사실층 요약·검증 결과(해석층은 못 건드림) · 해석 프롬프트 전반의 품질 · 과거 "why 빈값"(모델 교체로 해소).

## 5. (참고) 토론 전 선택지 후보 — 미승인, dive-in 때 다시 정리

1. 규칙 ④ 를 certifier 와 같은 **값 기준**(`numeric.scan` + `contains`)으로 바꾼다 — 표기 불일치 22건은 통과, 진짜 새 수치 11건은 그대로 차단. 회귀셋 = 위 33 토큰.
2. 해석 프롬프트에 "숫자는 원문 표기 그대로(percent ↔ %)" 규칙 — LLM 준수에 기대므로 불안정, 1 과 겹침.
3. 폴백된 해석 본문을 로그(또는 ledger)에 남긴다 — 열거/계산 수치의 성격을 사후에 볼 수 있게(측정 가능성).
4. 그대로 둔다 — 하루 ~1.5장의 통찰 손실을 비용으로 수용.

## 6. 재현

```
BACKEND=dynamo uv run python docs/work_note/Oct-2026/261030-improve-today-briefing/tools/interp_lint_cases.py --since 2026-10-21 --until 2026-10-30
aws logs filter-log-events --region us-east-1 --log-group-name /aws/bedrock-agentcore/runtimes/briefing_agent-b9uh7rDAqL-DEFAULT \
  --start-time <epoch_ms> --filter-pattern '"gate interp"' --query 'events[].message' --output text
```
