# 카드 제목 = 기사 원제목 (real/lens 재정렬) — 2026-07-08

**상태: SHIPPED · LIVE** · 커밋 main `84ed757` · deploy_api + deploy_runtime

## 무엇을 (What)
카드 제목(h2)을 **AI 재프레이밍 헤드라인 → 기사 원제목(`source.title`)** 으로. real/lens 아키텍처 정렬.

## 문제 (Why)
사실층 author 가 headline 을 *재프레이밍* 생성 → 각도·함의를 사실층 제목에 심음 + 원제목이 출처줄로 밀려 **"제목 2개"** 로 보임.
예: 원제목 *"MS, 엑셀·아웃룩에 자체 'MAI' 모델 도입…의존도 낮춘다"* → AI *"MS, 자체 'MAI'로…의존도 줄인다"*.

## 해결 (real = 제목, lens = 왜 중요한가)
- **author**: `_OUTPUT_CONTRACT` 에서 headline 제거 — summary+claims만 생성. `_to_draft_card(source_id, title, data)` 가 `headline=title`(=`source.title`, data 의 headline 무시). `draft_card`·`revise_claims` 가 `source.title` 전달.
- **PROMPT_VERSION layered-v1→v2** — 계약 변경 → 사실층 캐시 자동 무효화(옛 AI-headline 카드 미재사용).
- **render**: 출처줄 = 📰 도메인·날짜·원문 링크만(원제목 제거, `_TITLE_MAX` 삭제). 제목은 h2(=`card.headline`=원제목).
- **각도·중요성**은 "나에게 왜 중요한가"(lens) 그대로. `sample_briefing.html` 도 새 포맷.
- **certifier·ledger·cache 무변경**(headline 은 여전히 필드, 값만 원제목).

## 검증 (Verification)
- ruff + pytest **214** · **실 e2e(`claude -p` author) — h2 = 기사 원제목 *"MS, 엑셀·아웃룩에…도입…낮춘다"*, 출처줄 = 도메인·날짜·원문(제목 없음)** 확인.
- 배포: deploy_api(라이브 `/sample` 새 포맷) + deploy_runtime(READY·ARN 불변·`DRY_RUN=0`) → 내일 06:00 KST admin 이메일부터 적용.

## 관련
- card-layering 원안의 ⓒ(원제목 출처줄) 를 대체(제목=h2 로 승격). 별개 **deferred: 깊이 full==summary**(render+런타임 별건).
