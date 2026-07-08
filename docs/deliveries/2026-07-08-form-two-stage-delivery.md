# 구독 폼 2단 재구성 (지금 체험 / 매일 구독) — 2026-07-08

**상태: SHIPPED · LIVE** — `https://dqizh0gi9cp2q.cloudfront.net/setup` · 커밋 `48419b1` · **프론트 전용(deploy_web)**

## 무엇을 (What)
`/setup` 폼을 평평한 5단계 → **2단 구조**로 재구성. 시간성이 다른 두 행동(즉시 체험 vs 예약 구독)을 구조로 분리.

## 문제 (Why)
- 첫 행동인 **체험(trial)이 실제로 쓰는 건 매체 + 이메일뿐** — `handleTrial` 은 `lens/depth/send_hour` 를 무시하고 `general/summary/즉시` 전송.
- 그런데 폼은 **발송 시각(예약)·관점·깊이를 체험 버튼 *앞*에** 나열 → 즉시 체험에 무관·오해되는 예약 시각이 제일 먼저 옴("체험이 첫 경험인데 예약 시각이 먼저").

## 해결 (B안 · progressive disclosure)
- 공통 상단: **미디어 선택**(체험·구독 공통).
- **① 지금 체험**: 이메일 + 체험하기 (즉시 발송 — 예약 아님).
- **② 매일 구독 설정**: 발송 시각·관점·깊이 + 로그인/구독하기 (예약).
- secondary 표현 = **폰트 축소가 아니라 박스 + 배지 + 위치 구조**(② 라벨 14px 로 ①과 가독성 통일). `:root` 에 `--stage` 토큰.
- 핸들러·버튼 role·라디오 aria-label·이메일 input **전부 verbatim** 보존 → test 33/33 (구독 성공 단언만 `/구독 완료|매일/` → `/구독 완료/` 로 정밀화: 새 카피의 "매일"과 충돌 제거).

## ⚠️ 미해결 (deferred) — 깊이(depth) "full" 은 죽은 옵션
`render.py` 의 depth 분기는 `if depth != "title-only"` **하나뿐** → 실제 렌더:
| 선택 | 결과 |
|---|---|
| title-only | 헤드라인 + 요약 (해석 없음) |
| summary | + 해석("나에게 왜 중요한가", lens) |
| **full** | **summary 와 100% 동일** (추가 분기 0) |
- "title-only" 도 이름과 달리 요약을 보여줌 → 라벨 3개가 오해 소지, **실제 구분은 2개**(요약 / 요약+해석).
- **고침 방향**: A(2옵션으로 단순화) 또는 B(full = 검증된 claims 근거 노출 — verify-before-publish 정체성에 부합). 어느 쪽이든 **render.py + `/catalog`(DEPTHS) 변경 → deploy_api + deploy_runtime** 필요(이메일 렌더가 런타임). 이번 레이아웃(프론트 전용)과 분리해 **보류**.

## 검증 (Verification)
- vitest **33/33** · tsc+vite build 클린 · 로컬 preview + **라이브 `/setup` 스크린샷**(2단 렌더 · 예약 시각이 ②로 이동 · 프로덕션 카탈로그 확인).
