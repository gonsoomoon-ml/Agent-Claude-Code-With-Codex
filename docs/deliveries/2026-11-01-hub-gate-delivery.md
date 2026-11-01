# 전달 기록 — html 목록 허브 관문 + PTK 캡 4 + 한정어 그림자 검사 수정 (2026-11-01)

> `deploy_runtime` READY v65 → **v66**(2026-11-01 01:36Z, 컨테이너 `20261101-013459-435`) → **v67**(02:37Z, 컨테이너 `20261101-023553-035`, +b) → **v68**(03:33Z, 컨테이너 `20261101-033232-609`, +d), ARN 불변 `briefing_agent-b9uh7rDAqL`.
> main `3a3c2b1`(origin 푸시 완료). 다른 컴포넌트(webapi·scheduler) 무변경 — 새 카탈로그 필드는 수집(runtime)만 쓴다.
> 작업 노트: `docs/work_note/Oct-2026/261030-improve-today-briefing/`(README 문제 표 · `problem-7-html-listing-rewalk.md` §6-a).

## 1. 무엇이 실렸나

| 커밋 | 내용 | 독자 영향 |
|---|---|---|
| `edbe30f` feat(retrieval) | **허브/비기사 관문** — `Source.exclude_paths`(아는 비기사 URL 을 목록 단계에서 제거) + `Source.page_type: article`(선언된 og:type/JSON-LD 가 기사가 아니면 skip + `[WARN fetch non-article]`). 카탈로그: anthropic `page_type` + 허브 7 · pytorch-kr-news `/t/topic/407` · google-dev `/search` | Anthropic News 허브(기사 모음)가 "✓ 검증" 카드로 나가던 일(10-21 "Announcements"·10-28 "Partnerships", 7명) 재발 방지. 남은 허브 3개(features·policy·safeguards)도 더는 카드가 안 됨 |
| `edbe30f` (같은 커밋) | **pytorch-kr-news `max_items` 5→4**(#4b) | 평일 48h 풀(5건+)에서 Haiku pick-4 가 실제로 돈다 → PTK 카드 ≤4/일 |
| `5b14b31` fix(quality_checks) | 한국어 한정어 그림자 검사(`qualifier_dropped`) 오탐 수정(#5) | 없음(로그 전용) — 그림자 집계가 실제를 반영 |
| `c194d0e` docs · `1b92df8` docs(CLAUDE.md) | 문제 정의 md 2건·도구 14종·재현 출력 · 「하나씩 보여주기」 규칙 | — |

## 2. 검증(배포 전·후)

- 테스트 826 통과·5 skip, ruff clean. 관문 테스트 8개는 구현 전 실패(RED) 확인 뒤 통과.
- 운영 함수 재현(11-01, `tools/gate_replay.py`): anthropic 요청 27→20 · PTK 31→30 · google-dev 39→38, 세 소스 모두 경고 0, 제외 경로 요청 0.
- PTK 캡 4 시뮬(배포 뒤 11-01, `tools/ptk_cap4_sim.py`, 운영 Haiku 선별자 2회): PTK 5장이던 3일(10-23·26·29) 15→12장, AI Agents 밴드행 8→8 — 탈락은 Inference & Hardware 글(TorchNeuron imp 4·RecIR imp 3), 10-26 은 Corgi↔NPU 흔들림. 관문·캡 모두 클라우드 실제 run 은 11-02(관문)·11-03 평일(캡)부터.
- 배포 뒤: DEFAULT 엔드포인트 `liveVersion=66` READY(01:36Z) · dispatch Lambda `BRIEFING_DRY_RUN=0`·ARN 일치 · `invoke_runtime --mode smoke` 7명 workflow_complete.

## 3. 첫 정기 run 확인(11-02 05:00 KST = 11-01 20:00Z)

```
aws logs filter-log-events --region us-east-1 --log-group-name /aws/bedrock-agentcore/runtimes/briefing_agent-b9uh7rDAqL-DEFAULT \
  --start-time <11-01 19:55Z epoch_ms> --filter-pattern '"WARN fetch"' --query 'events[].message' --output text
```

- 기대: anthropic Product/Security·PTK 카테고리 글의 `fetch stub` **0**(10-22~31 은 매 run 3줄) · `fetch non-article` **0**(새 허브가 생기면 1줄 — 그때 `exclude_paths` 에 추가).
- 남는 경고(별건): meta-research Muse 고정 글 2건 `fetch offsite` · 진짜 스텁(피드 티저 등)은 그대로 보여야 한다 — 10-26 aws-kr-tech 사례처럼.
- PTK 캡 4 는 평일 run(11-03 화)부터 의미 있음: Community/AI Agents 밴드의 PTK 카드 ≤4 + `select` 로그.
- 그림자 `집계` 줄의 `qualifier_dropped` 가 0~1 수준이면 #5 수정이 운영에서도 유효.

## 4. 함정·메모

- `page_type` 은 **anthropic 에만** 켠다. Discourse(PTK)는 글 전부 og:type=website, claude-blog 는 같은 글도 fetch 마다 메타가 다름, google-dev 는 og:type 없음(실측 `hub-signals-20261101.txt`).
- anthropic.com 사이트맵은 `lastmod` = 수정일(최근 94건 중 84건이 옛 글) → `kind: sitemap` 전환 금지. RSS 는 없음.
- 사이트맵에 `/engineering/` 0건, 엔지니어링 글이 `/research/` 아래 → 새 항목 (b) "anthropic-eng 0건"의 원인 후보(미확인).
- 배포는 작업 트리 `src/briefing` 을 실으므로 커밋 뒤 `src`·`tests` 미커밋 변경 없음 확인(이번 11-01: 없음; `CLAUDE.md`·`README.md` 의 다른 세션 변경은 빌드 컨텍스트 밖).

## 5. 같은 날 2차 배포 — runtime v67 (02:37Z): +b anthropic-eng 되살림

- 커밋 `a3464a4` feat(retrieval) · `4755fff` docs. 원인 = Anthropic 사이트 개편(10-13 이후 엔지니어링 글이 `/research/<slug>` 로, `/engineering` 은 JS 모음 페이지) →
  anthropic-eng 가 3주간 조용히 0건(새 글 0편이라 독자 손실 없음). 변경: 카탈로그 `article_path: /research/` + `page_type: article` + 팀 허브 5개 `exclude_paths`
  (`/research/team/*` 는 og:type=website·최신 글 날짜 — 30일 창 재현에서 3쪽 통과 실측) + `fetch_generic_html` 목록 링크 0개면 `[WARN fetch listing]`.
- run 내 같은 글(anthropic-research 와 겹침)은 `curate` 가 `source_id` 로 접음(확인, 파이프라인 변경 없음 — 회귀 가드 테스트).
- 검증: 테스트 829 통과·ruff clean · 운영 함수 재현 48h 요청 25·통과 0·경고 0 / 30일 창 통과 1(10-13 글)·팀 허브 요청 0 · 배포 뒤 liveVersion **67** READY ·
  dispatch Lambda `BRIEFING_DRY_RUN=0`·ARN 일치 · smoke invoke 7명 workflow_complete.
- 첫 run 확인(11-02 05:00 KST)에 추가: `fetch listing` 경고 0(anthropic-eng 가 링크 25개를 읽음) · 다음 엔지니어링 글이 나오면 Anthropic Engineering 카드 1장(research 와 중복 0).
- 새 항목 +d(미정의): `/research` 목록 페이지가 211편 중 22편만 노출 — 10-13 이후 보안·레드팀 글 4편이 카드가 된 적 없음(`tools/research_gap.py`).

## 6. 같은 날 3차 배포 — runtime v68 (03:33Z): +d Anthropic Research 팀 페이지 보조 목록

- 커밋 `3863083` feat(retrieval) · `3a3c2b1` docs. 원인 = `/research` 메인 목록(22편)은 사이트 편집 선택이라 Frontier Red Team·Interpretability 글을 한 편도
  싣지 않음(팀 페이지 5개에만, 메인과 겹침 0) → 10-13 이후 red-team 글 4편이 카드가 된 적 없음(09-01 이후 8편). 변경 = `Source.listing_urls`(보조 목록, 주 → 보조 순
  합치기·URL 중복 1회·보조 실패는 그 목록만 skip+`fetch listing` 경고) + 카탈로그 anthropic-research 에 팀 페이지 5개. 키 불변 → 프로필·webapi 무변경.
- 검증: 테스트 834 통과·ruff clean · 운영 함수 재현 48h 요청 130(목록 6)·22s / 30일 창 통과 17편(이전엔 안 보이던 red-team 4편 등 6편 포함) ·
  배포 뒤 liveVersion **68** READY · dispatch Lambda `BRIEFING_DRY_RUN=0`·ARN 일치 · smoke invoke 7명 workflow_complete.
- 첫 run 확인(11-02 05:00 KST)에 추가: anthropic-research 수집 시간 ≈22s(run 총시간 +20s 안팎) · 새 red-team/interpretability 글이 나오면 Anthropic Research 카드로 등장.
- **알려진 잔여(미승인·보류):** 팀 페이지가 링크하는 옛 글 4쪽이 매 run 경고 4줄 — interpretability `/research/crosscoder-model-diffing`(2025-02, 381자)·
  `/research/features-as-classifiers`(2024-10, 430자)·`/research/transformer-circuits`(2024-03, 475자) = `fetch stub`, societal-impacts `/research/AI-fluency-index`
  (2026-02, canonical academy.claude.com) = `fetch offsite`. 전부 창 밖이라 카드 영향 0. 처치 = `exclude_paths` 4줄(사용자 결정 대기).
