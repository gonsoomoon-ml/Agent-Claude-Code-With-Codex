# 2026-10-30 — 브리핑 리뷰 후속: offsite 완화 + 핵심 3 우선순위 확정 (전달 기록)

> **상태: SHIPPED · LIVE · 정기 첫 run 검증 대기** — main `02bc7fd`(origin 동기화, 브랜치 `worktree-offsite-warn-only` fast-forward) ·
> `deploy_runtime` READY v64 → **v65**(2026-10-30 10:42Z, ARN 불변 `briefing_agent-b9uh7rDAqL`, env 19개 무변경, 컨테이너 `20261030-104124-668`)

## 1. 무엇이 바뀌었나 (커밋 4개)

| 커밋 | 내용 | 효과 |
|---|---|---|
| `2b28b1a` | 수집층 offsite(canonical 교차) 차단 → **경고만 통과**(`fetch offsite` 라벨 불변) | Meta 처럼 ai.meta.com 원본을 research.meta.ai 목록에 미러하는 글이 날짜 검사 전에 버려지지 않음(미래 방어). 반복 발행은 URL 키 dedup(90일)이 막음. 출력 무변화(두 Muse 글은 04/07 월 옛 글 → 48h 창에서 걸러짐) |
| `56f1286` | 라벨 프롬프트 `launch` 정의 좁힘(새 모델·새 제품/서비스·플랫폼 GA 만; 점진 기능·통합·SDK/스킬·튜토리얼·엔지니어링 글 = applied) | 1티어 후보 58→33장(10일 재생), 플래그십 유지. how-to(TorchTPU·AWS Batch 할당량 등)가 큰 발표 칸에서 빠짐 |
| `422df5b` | (중간 단계) 응용 칸 = applied ∧ 분야 {AI Agents, Applied AI} | `02bc7fd` 로 대체 |
| `02bc7fd` | **사용자 우선순위 확정** ① 5대 기업 큰 발표 → ② AI Agents → ③ Applied AI(엄격) + **Arel**(큰 발표는 그날 최고 AI Agents 후보 importance 이상일 때만 1순위, 미달 시 Agents 다음·Applied AI 앞) | `tier` 4등급·`ranks`·`assign_top` 단계 ①②②.5③④·로그 `p1↓`. 10일 시뮬: 엄격 순서 5일 변화(Applied AI 는 큰 발표 2장 미만인 날만 — 사용자 수용), Arel 1일(10-25) |

리뷰 전체 기록·측정 = `docs/work_note/Oct-2026/261030-improve-today-briefing/`(문제 9건 목록, 재생 리포트, 날짜별 핵심 3 비교, 도구).

## 2. 근거·게이트

- 테스트 813 passed · ruff clean. 핵심 3 규칙 = 결정론 단위 테스트(등급·엄격 순서·Arel 역전/동점·MAX_BIG 합산·로그 표시).
- 프롬프트 변경은 10일 재생(Sonnet 5.5, 운영 경로 `make_bedrock_labels`)으로 검증. 분야 골든 게이트: 현 89.3%(같은 날) vs 좁힌 87.8%(≥85% 통과, 불일치 12건 공유 = 잡음).
- 기각(재제안 금지): 1티어 importance 절대 문턱(≥4) · "연구 결과→other" 문구 · importance 앵커 · 번갈아 채우기 · importance 우선(B).

## 3. 배포

- `uv run python -m briefing.runtime.deploy_runtime` → launch 75s → READY(1/60) → `.env` writeback. 다른 컴포넌트(webapi·scheduler) 무변경.
- 주의: 이 세션은 worktree 에서 작업 → `ExitWorktree(keep)` 뒤 main 에서 `--ff-only` 병합·push. deploy 는 main 작업 트리를 실음 — 빌드 컨텍스트 = `src/briefing` + `runtime/container` 자산 + `users/`(`stage_build_context`). `src`·`tests` 미커밋 변경 없음 확인; `CLAUDE.md` 는 다른 세션의 미커밋 변경이 있었으나 빌드 컨텍스트 밖이라 컨테이너에 안 실림. 배포 뒤 확인: DEFAULT 엔드포인트 liveVersion=65(10:43Z) · dispatch Lambda `BRIEFING_DRY_RUN=0`·ARN 일치(07-04 이후 무변경) · `invoke_runtime --mode smoke` 7명 workflow_complete.

## 4. 첫 run 검증 체크리스트 (2026-10-31 05:00 KST = 10-30 20:00Z)

CloudWatch `/aws/bedrock-agentcore/runtimes/briefing_agent-b9uh7rDAqL-DEFAULT`:
- [ ] `[WARN top picks 선정]` 한 줄 — 새 표기 `p1 · p1↓ · p2 · p3 · p4`; 1티어 뒤에 p2(AI Agents)가 오고 p3(Applied AI)는 큰 발표가 2장 미만일 때만
- [ ] `[WARN fetch offsite] meta-research: … 경고만, 통과(반복은 URL 키 dedup 이 막음)` — 문구가 바뀌었는지(구 "글이 아니라 건너뜀" 이면 구 버전)
- [ ] meta-research 외 소스에서 `fetch offsite` 히트가 없는지(1주일 관찰; sitemap 소스는 표본 밖)
- [ ] `[WARN areas 라벨]` 분포 줄 정상(평평 폴백 없음)
- [ ] sent-log 7명 `status=sent`
메일(관리자 수신분):
- [ ] 핵심 3 = 큰 발표 → AI Agents 순; how-to 성 글이 큰 발표 칸에 없음
- [ ] 분야 밴드·출처 집계 줄 등 나머지 레이아웃 무변화

통과하면: 이 문서 상태 → **SHIPPED·LIVE(검증 완료)**, `docs/README.md` 같은 줄, 메모리 `project-top-picks-big-announcements`·`project-offsite-warn-only` 갱신.

## 5. 남은 일 (문제 목록 #3~9 + 새 항목)

- #3 분야 라벨 run 간 흔들림 6%(연재물 묶기 제안) · #4 PyTorch KR 편중 · #5 수식어 탈락 · #6 해석층 폴백 · #7 날짜 없는 목록의 매일 재열람 · #8 `fetch stub` 노이즈 · #9 고유명사 미포함
- 새 항목: ai.meta.com 페이지 trafilatura 날짜 추출 오류(Muse Image/Video → 2022-11-18) · Anthropic News 목록 페이지("Announcements"·"Partnerships")가 카드로 수집됨
- 핵심 칸 확대(K>3) 시 손볼 것: "섹션당 1장" 규칙이 주말(섹션 2개)엔 3장에서 멈춤 · 단계 ④ 잔여 큰 발표가 표시 정렬에서 3번째 큰 발표처럼 보임(10-27)

## 6. 함정(다음 사람을 위해)

- worktree 세션에서는 하네스가 main 체크아웃 git·heredoc→uv/python 을 거부 — 스크립트는 scratchpad 파일로 써서 경로로 실행.
- 해석층 폴백 카드는 interp 키로 캐시되지 않는데 ledger 는 그 키를 적는다 → 재생 때 `fact_card_key(source_id, 요약 모델[10-25 전 Sonnet 5], 지시 버전)` 로 재탐색.
- 라벨 LLM 은 같은 프롬프트로도 run 마다 핵심 3 이 다르다(10일 중 5일) — 단건 뒤집힘으로 규칙을 판단하지 말고 10일 재생으로.
- 매일 같은 URL 에 뜨는 WARN 은 "새 사고"가 아니라 옛 고정 글 신호일 수 있다 — 페이지 날짜부터 확인(이번 #1 오진).
