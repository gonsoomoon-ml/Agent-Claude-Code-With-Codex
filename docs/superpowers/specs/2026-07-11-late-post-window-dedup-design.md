# 늦은 발행(late-post) 수집 갭 수정 — 소스별 window + ledger 발행 dedup 설계

- **상태:** DRAFT (2026-07-11) → 구현
- **발단:** 사용자 질문 "reflect-with-claude·claude-model-and-effort 두 URL 을 우리가 수집하나?" → DDB source-store 실증으로 **둘 다 수집된 적 없음** 확인.

## 1. Root cause (실증 완료)

수집은 매일 1회 스냅샷(07:00 KST = 전날 22:00 UTC = 전날 15:00 PT), 윈도우 24h. **html 소스는 trafilatura 메타데이터가 date-only**라 `_is_stale` 이 자정(00:00)으로 파싱 → 기사가 실제보다 최대 24h 늙어 보임.

- date-only 기사의 수집 기회 = **발행 날짜 당일 22:00 UTC 런 딱 1회**(자정 기준 age 22h).
- 그날 15:00 PT 이후 발행(SF 회사 오후 발행 빈번) → 유일한 eligible 런 시점에 리스팅에 없음 → 다음 런에선 age 46h > 24h → **영영 유실**.
- 증거(소스-스토어 대조): 7/7 `claude-model-and-effort`·`government` ❌, 7/8 `reflect-with-claude` ❌(같은 날짜 thomson-reuters·marketing-ops ✅), 7/9 `ust-claude` ❌(같은 날짜 hard-questions·ben-bernanke ✅) — 갈린 기준이 정확히 "당일 22:00 UTC 에 리스팅에 있었는가".

## 2. 원칙: W ≥ U + P

안전 윈도우 W ≥ timestamp 불확실성 U + 런 주기 P. RSS(U≈0)+P24h → W=24h(현행 유지). **html date-only(U=24h)+P24h → W=48h 필요.** 즉 48h 는 규칙 완화가 아니라 timestamp 해상도 보정 — "24h 규칙"의 의도(신선·정확히 1회)는 유지.

## 3. 변경 (2부분)

### (A) 소스별 윈도우 오버라이드
- `Source.window_hours: int = 0`(0=글로벌 기본 사용) + catalog 로더 검증(int·≥0, 아니면 시작 시 크래시).
- `curation._default_fetch`: `win = source.window_hours or window_hours` — 오버라이드 소스만 넓은 윈도우.
- catalog: html(date-only) 4소스 `window_hours: 48` — anthropic·anthropic-eng·claude-blog·google-dev. (RSS 소스 무변경.)

### (B) ledger 기반 cross-day 발행 dedup (불변식의 명시화)
48h 겹침(shingle)으로 이른 발행 글이 D+1·D+2 두 런에 잡히므로, "각 기사 = 사용자당 정확히 1회"를 윈도우 산술(암묵)이 아니라 **ledger 조회(명시)** 로 보장:

- 현황: sent-log dedup 은 (user, run_date) 단위(같은 날 재발송 방지)라 기사 단위 아님. ledger 는 (user, run_date, source_id, decision) 을 **기록만** 하고 아무도 조회 안 함 — docstring 의 "Diff-Since-Last 토대" 용도를 이번에 처음 사용.
- `run_briefing` per-user 루프 앞에서 `ledger.query(u.id, since=run_date-7d)` → **prior_published** = `{source_id | decision==PUBLISH and rec.run_date < run_date}` → 해당 frozen source skip(+non-silent dprint).
- **의미론 3결정:**
  1. **PUBLISH 만 dedup** — QUARANTINE 기록은 skip 안 함(다음 런 재도전 허용; 사용자는 그 카드를 받은 적 없음).
  2. **strictly-earlier(`< run_date`)만** — 같은 날 재실행(강제 재발송 런북)은 dedup 에 안 걸림(멱등 재실행 보존; 하루 1회 발송은 sent-log 소관).
  3. **run_date 빈값이면 dedup off** — 순서 비교 불가한 ad-hoc/로컬 경로는 현행 유지.
- `ledger=None`(기존 테스트·로컬 기본) → dedup 자체가 off = 기존 동작 무변경.

## 4. 사용자 가시 효과

| | 현행 | 변경 후 |
|---|---|---|
| 미국 오전 발행 글 | D+1 아침 브리핑 | 동일(D+1; D+2 런에도 잡히지만 dedup 이 제외) |
| 미국 오후 발행 글 | **영영 유실** | D+2 아침 브리핑(하루 늦게라도 1회) |
| 중복/낡은 글 | — | 없음(dedup·실나이 이틀 미만) |

## 5. 테스트 계획 (TDD)

1. sources: catalog 에서 `window_hours` 로드(anthropic=48·aitimes=0) + 로더가 음수/비정수 거부.
2. curation: `_default_fetch` 가 source.window_hours 오버라이드를 fetch 에 전달(monkeypatch 캡처).
3. pipeline dedup: ① 전날 PUBLISH 기록 → 오늘 skip ② 같은 run_date 재실행 → skip 안 함 ③ 전날 QUARANTINE → skip 안 함(재도전) — LocalLedger(tmp) 로 결정론.
4. 회귀: 전체 스위트(ledger=None 경로 무변경).

## 6. 배포·검증

- catalog+코드 = 런타임 이미지 → **deploy_runtime 필요**(ARN 불변·scheduler 무접촉). deploy_api 불필요(webapi 는 window_hours 미사용).
- live 검증: 배포 다음날부터 — 오후 PT 발행 글이 D+2 아침 브리핑에 1회 실리는지 + CloudWatch "pipeline dedup" dprint. (오늘 유실분 4건은 이미 48h 밖 — 소급 불가.)
