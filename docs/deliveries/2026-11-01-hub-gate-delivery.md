# 전달 기록 — html 목록 허브 관문 + PTK 캡 4 + 한정어 그림자 검사 수정 (2026-11-01)

> `deploy_runtime` READY v65 → **v66**(2026-11-01 01:36Z, ARN 불변 `briefing_agent-b9uh7rDAqL`, 컨테이너 `20261101-013459-435`).
> main `1b92df8`(origin 푸시 완료). 다른 컴포넌트(webapi·scheduler) 무변경 — 새 카탈로그 필드는 수집(runtime)만 쓴다.
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
