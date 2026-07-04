# 웹 프로필 관리 완성 (lens·depth 노출 + prefill) — 설계 스펙 (2026-07-04)

> 상태: 승인됨(사용자 A안) · 관련: `2026-07-04-admin-roles-design.md` · 배경: 웹 폼이 lens='general'·depth='summary' 를 하드코딩해 저장 시 기존 스타일(engineer/full)을 리셋 — gonsoo→admin(sub) 신원 이관과 함께 "웹으로 관리"를 실제로 성립시킨다.

## 범위 — **web/ 만** (서버 무변경)

`validate_profile` 이 이미 lens/depth 를 카탈로그 기준으로 검증하고, `/catalog` 응답에 `lenses: [{key,name}]`·`depths: [...]` 가 이미 실려 있다. 변경은 `web/src/pages/Form.tsx`(+테스트, 필요시 types)뿐.

## 요구사항 3개

1. **lens·depth 선택 노출:** 발송 시각 라디오와 같은 패턴으로 두 라디오 그룹 추가 — 렌즈는 `catalog.lenses` 의 `name` 표시(`key` 전송), 깊이는 `catalog.depths` 그대로. 섹션 번호 재정렬(1 미디어 · 2 발송 시각 · 3 관점(렌즈) · 4 깊이 · 5 이메일). 기본값: lens `general` · depth `summary`(현행과 동일).
2. **구독자 prefill:** 로그인 + `getProfile().subscribed` 이면 `profile` 레코드의 `sources`·`send_hour`·`lens`·`depth` 를 폼 state 에 반영 — "저장 = 기존 설정 수정"이 되게. (recipient 표시는 기존 동작 유지.)
3. **하드코딩 제거:** `putProfile` payload 의 lens/depth 를 state 값으로.

## 불변식

- 서버·API 계약 무변경(payload 필드 구성 동일 — 값만 state 유래). 체험(trial) 흐름 무변경.
- 비로그인 화면은 라디오 기본값만 다르게 보일 뿐 동작 동일.

## 테스트 (vitest)

- prefill: subscribed mock(`profile: {sources:[...], send_hour: 6, lens:'engineer', depth:'full'}`) → 라디오/선택 상태 반영 확인.
- payload: 렌즈/깊이 라디오 변경 후 구독하기 → `putProfile` 호출 payload 에 해당 값.
- 기존 테스트 전부 무수정 통과(기본값 동일하므로).

## 검증 사다리

vitest + tsc → `deploy_web`(웹만) → 실 로그인으로 prefill·저장 확인(사용자).
