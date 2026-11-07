# Field Experiment 주간 기사 워크플로 (1-B 클라우드 자동 · 그림 포함)

> 2026-11-07 (d) 기준 — 컨테이너에 Chromium 을 넣어 **그림 트랙이 클라우드에서 돌고**, PNG 는 표(`figure_png_b64`)로 07:00 send 세션에 넘어간다.
> 코드 = `src/briefing/weekly/`(build · send) · `src/briefing/scheduler/`(Lambda · 스케줄) · `src/briefing/runtime/`(런타임 분기 · 컨테이너).
> 계획 · 결정 = `delivery-plan.md`, 전달 기록 = `docs/deliveries/2026-11-07-weekly-cloud-schedule-delivery.md` · `…-weekly-figure-container-delivery.md`.

```
토요일 KST                                    ★ = 2026-11-07 (d) 로 새로 생긴 것 · 바뀐 것
══════════════════════════════════════════════════════════════════════════════════

 06:00  EventBridge Scheduler "briefing-weekly-build"   Input {mode: weekly_build}
          │
          ▼
        Lambda briefing-scheduler-dispatch   (mode 그대로 전달 · accepted ack 만 받고 반환)
          │  invoke_agent_runtime(새 session id, payload {mode, dry_run})
          ▼
 ┌─ AgentCore Runtime 세션 A ─ 컨테이너 ★ playwright 1.58 + Chromium + Noto CJK(한글 글꼴) ──┐
 │  entrypoint → add_async_task → run_cloud("weekly_build")   issue_date = KST 날짜          │
 │                                                                                          │
 │  DDB briefing-weekly-issues:  (없음 | ready | quarantined | failed) ──▶ building         │
 │     │                                                                                    │
 │     ▼ collect   데일리 원장 · 카드 캐시 · 원문 저장소(읽기 전용) → 이번 주 카드 ~110장      │
 │     ▼ select    Opus 5.5 → 씨앗 + 수렴 글 + 실험 한 줄                            ($0.6) │
 │     ▼ source    동결 원문(잘린 것은 refetch · 상한 60,000자)                              │
 │     ▼ write     Opus 5.5 → Draft{md, cites}   (12턴 · 346s · 상한 WEEKLY_AUTHOR_TIMEOUT_S) │
 │     ▼ critique  Opus 5.5 자기 비평 → revise                                        ($0.5) │
 │     ▼ gate      lint 9 + certifier(codex, 원문 대조) + 저장소 링크 · 모델 · 자(ruler)      │
 │     │     FAIL(고칠 수 있는 것만) → revise → gate   (≤ WEEKLY_MAX_REVISIONS)              │
 │     ▼ PASS → ready   /   아니면 quarantined(표시 달아 관리자에게)                          │
 │     ▼ figure ★ make_figure(md, timeout_s=주간 상한)   ★ WEEKLY_FIGURE 를 runtime_env 로 전달 │
 │     │     Opus 5.5 → 그림 스펙 JSON → 검증(한도 · 숫자는 기사 ② 의 것만) ≤ 3회  ($0.15/회) │
 │     │     scheme_a HTML → Chromium 렌더 → PNG → lint(넘침 · 글자 예산 · 16px · 단색)       │
 │     │     실패 · 환경 없음 → 기사 상태는 그대로, notes 에만 남김                            │
 │     ▼ store     building ──▶ ready | quarantined                                         │
 │           {issue_md, email_html, cites, gate, seed, cost, calls,                          │
 │            ★ figure_png_b64 (≈150KB; 상한 300K자 — 넘으면 생략 · notes), figure_json}     │
 └──────────────────────────────────────────────────────────────────────────────────────────┘
        어느 단계든 예외 → building ──▶ failed {stage, error}

 07:00  EventBridge Scheduler "briefing-weekly-send"    Input {mode: weekly_send}
          │
          ▼
        Lambda briefing-scheduler-dispatch → invoke_agent_runtime(★ 새 session = 다른 파일시스템)
          ▼
 ┌─ AgentCore Runtime 세션 B ───────────────────────────────────────────────────────────────┐
 │  run_cloud("weekly_send") → DDB get(issue_date)                                           │
 │     │                                                                                     │
 │     ├─ building | failed | 없음 ──▶ SES "[현장 실험] 생성 실패 <date>" → 관리자              │
 │     │                                                                                     │
 │     └─ ready | quarantined                                                                │
 │          ▼ ★ figure_png_b64 있음(없으면 figure_png 경로 폴백) → render_email(figure_cid)     │
 │          │     ③ 의 ASCII 그림 블록 → <img cid:fig2>   (md 의 ASCII 가 진실 · PNG 는 메일용)  │
 │          ▼ ready ──▶ sending   (조건부 전이 — 두 번째 send 는 여기서 멈춤)                   │
 │          ▼ SES send_raw_email(HTML + inline PNG) → 관리자(1단계)                            │
 │          ▼ sending ──▶ sent {message_id, sent_at}                                          │
 │          ▼ sent-log  weekly#<admin>/<date>   (관리자 화면 /admin/emails)                    │
 └───────────────────────────────────────────────────────────────────────────────────────────┘

 이후   pull → field-experiment/issues/<date>.md + .log.md (사람이 읽는 사본)
        2단계 approve(동료 opt-in) — 미구현 (delivery-plan.md §1)
 로컬 1-A(호스트)도 같은 코드 · 같은 필드 — b64 로 통일해 경로 의존이 없다(옛 호의 경로 필드는 폴백)
```

## 왜 PNG 가 표에 들어가나

06:00 build 와 07:00 send 는 **서로 다른 런타임 세션**이다 — Lambda 가 호출마다 새 session id 를 만들고, AgentCore 는 세션마다 microVM 을 띄우므로 파일시스템이 공유되지 않는다. 호스트 전제였던 `figure_png`(로컬 경로)만 적으면 클라우드에선 그림이 조용히 빠진다. 그래서 build 가 PNG 를 base64 로 항목에 싣고(`figure_png_b64`), send 가 그 바이트로 인라인 첨부를 만든다. 11-07 항목 ≈29KB + PNG 148KB(b64) ≈ 180KB 로 DDB 항목 상한 400KB 안이라 S3 는 쓰지 않는다. 상한(`FIGURE_B64_MAX_CHARS` = 300,000자)을 넘기는 PNG 는 b64 를 생략하고 기사는 그대로 보낸다 — 그림은 기사를 막지 않는다.

## 호스트에서 돌릴 때(로컬 1-A · 실험)

호스트 `claude -p` 는 사용자 플러그인(도구 81개 · SessionStart 훅 2개)이 실려 컨테이너와 다르다 — Opus 5.5 호출당 ≈$0.25 더 들고 "한국어로 답하라 · skill 을 먼저 써라" 지시가 작성자에게 들어간다(2026-11-07 프로브, `docs/deliveries/2026-11-07-weekly-figure-container-delivery.md` §3). 로컬 실험은 빈 HOME 레시피로 돌린다(메모리 `project-local-author-host-contamination`).
