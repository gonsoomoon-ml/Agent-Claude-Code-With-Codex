# 구현 메모 — 주제 밴드(topic-grouping) (2026-10-24)

계획: `docs/superpowers/plans/2026-10-24-topic-grouping.md` · 스펙: `docs/superpowers/specs/2026-10-24-topic-grouping-design.md`

## Task 6 스모크 — Sonnet 5.5 Converse 파라미터 (확인 먼저)
- 등록 프로필(us-east-1 `list-inference-profiles`): `us.anthropic.claude-sonnet-5-5`, `global.anthropic.claude-sonnet-5-5` → `.env` 는 global.
- 후보 A `additionalModelRequestFields={"thinking": {"type": "between_tools"}}`, `maxTokens=6000`(`LABEL_MAX_TOKENS`) → **통과**: 텍스트 블록 `"OK"` 수신, ValidationException 없음. 후보 B(adaptive 기본 + effort)는 시도하지 않음.
- 관련성·선별·헤드라인 선별 헬퍼(`_converse_text`, `thinking: disabled`)는 바이트 동일 유지(테스트 `test_relevance_helper_still_sends_thinking_disabled`).

## Task 7 머지 게이트 — 골든셋 평가 · 헤드라인 점검 · 핵심 3 관찰 (2026-10-24)
- `run_golden.py` 1차(2회차, 규칙 원안): **87.0%** PASS(114/131), 안정성 93.9%, 불일치 17 = 경계 8 + 비경계 9 → 사유를 `golden-eval-20261024-1349.md` 에 기록. 패턴 1개 = 고객 사례(Deepgram·i14/Laplace)가 칩 규칙(③)으로 감 → 규칙 ⑤에 "①·③보다 우선" 문구 추가.
- 2차(1회차, 규칙 수정): **91.6%** PASS(120/131), 불일치 11 = 경계 6 + 비경계 5(`golden-eval-20261024-1352.md`). 개선폭은 변동 범위 안 → 수정은 유지(해치지 않음). 프롬프트 반복 1/3 · 골든 라벨 변경 0 · boundary 표시 4장(상한 7).
- 남은 비경계 불일치의 성격: 과학 결과 *논쟁*(Navier-Stokes)·회사 연구 성과(Recursive)·정렬 키워드(unreleased model)·AI 관련성 약한 카드(GeoJSON) — 정의로 잡기 어려운 판단 차이, 수용.
- `headline_check.py`: 라이브 50제목 × 2회 — 미배정 0·0, 2회 일치 98%, 운영 경로(all-or-nothing) 소제목 OK → **PASS**. 손 검토: AI 제목 오분류 0(경계 1), 비AI 제목은 Applied AI 로 몰리나 운영에선 선별이 먼저 거른다.
- 핵심 3 관찰: 7 run 전부 티어 규칙 충족, 구 라벨의 오귀속 2건(TorchTPU 가이드=Google 큰 발표 · Claude 제공 확대=Google) 사라짐. 비용: 골든 2회차+1회차 ≈ $0.7, 헤드라인 ≈ $0.03.
