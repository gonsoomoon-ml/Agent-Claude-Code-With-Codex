# Field Experiment 1-B (d) — 클라우드 그림 트랙 전달 기록 (Delivery Record)

> 상태: **코드 완료 · 테스트 전부 통과(`uv run pytest`) · 런타임 재배포 대기(사용자 승인)** · 날짜: 2026-11-07 · 선행: `2026-11-07-weekly-cloud-schedule-delivery.md`(v70 LIVE) · 흐름도: `field-experiment/workflow.md`
> 승인: 11-07 "d." → "discard the 11-07. do the d and store the workflow to some md file".

## 1. 결정 (Decision)

11-07 호를 어떻게 보낼지 네 갈래를 비교해 **(d) 영구 해법**을 골랐고, **11-07 호는 보내지 않는다**(표에는 `ready` 로 남는다 — 어떤 스케줄도 그 날짜를 다시 집지 않는다. 11-14 06:00 build 는 `issue_date_kst` 로 11-14 항목을 새로 만든다).

| 갈래 | 내용 | 버린 이유 |
|---|---|---|
| (a) 클라우드 `weekly_send` | 만들어진 기사 그대로, 그림 없음, $0 | 그림이 필요하다(사용자) |
| (b) 로컬 1-A 전체 재빌드 | 새 기사 + 그림, ≈$2.5 · 15분 | 보던 기사를 버리고 저장소가 둘로 갈린다. 일회성 |
| (c) 기존 기사 + 그림만 로컬 생성 | 같은 기사, $0.2~0.9, force 전이 1회 | 일회성 수동 단계. 스크립트 2개는 scratchpad 에만 남김(미실행) |
| **(d) 컨테이너에 렌더 환경 + PNG 를 표로** | 매주 자동으로 그림까지 | **채택** — 오늘 호에는 못 쓰므로 11-07 은 건너뜀 |

## 2. 무엇을 전달했나 (Scope) — main 커밋 1개

| 파일 | 변경 |
|---|---|
| `src/briefing/runtime/container/Dockerfile` · `requirements.txt` | `playwright==1.58.0`(호스트 검증 버전 pin) + `python -m playwright install --with-deps chromium`(Chromium 1208 + apt 라이브러리) + `fonts-noto-cjk`. `PLAYWRIGHT_BROWSERS_PATH=/ms-playwright`(HOME 밖 — 설치 root · 실행 `bedrock_agentcore`) + `chmod a+rX` |
| `src/briefing/runtime/deploy_runtime.py` | `WEEKLY_ENV_KEYS` 에 `WEEKLY_FIGURE`(이전엔 일부러 제외) |
| `src/briefing/weekly/run.py` | build: `make_figure(..., timeout_s=주간 상한)` · ready PNG 를 `figure_png_b64` 로 항목에(`_figure_b64_field`, 상한 `FIGURE_B64_MAX_CHARS`=300,000자 → 넘으면 생략 + notes). send: `_figure_bytes` — b64 우선, `figure_png` 경로 폴백(옛 호 · 로컬) |
| `src/briefing/weekly/figure/build.py` | `make_figure(timeout_s=None)` → 작성자 호출에 전달(기본 None = 데일리 360 불변) |
| 테스트 | `test_runtime`(FIGURE 전달로 뒤집음 2) · `test_weekly_figure`(timeout 전달 1) · `test_weekly_run`(b64 저장 + 파일 없는 세션에서 첨부 · 경로 폴백 · 상한 초과 생략 · timeout 전달 4) — RED→GREEN, 전체 suite 통과(개수는 명령이 진실) |
| 문서 | `field-experiment/workflow.md`(ASCII 흐름도, 사용자 요청) · `delivery-plan.md` §2 · §4 · `docs/README.md` · 선행 전달 기록 §5 |

데일리 무변경: 바뀐 코드는 weekly · 컨테이너 Dockerfile(데일리 경로가 쓰지 않는 패키지 추가) · `WEEKLY_*` 전달뿐. 테스트 suite 전부 통과.

## 3. 호스트 `claude -p` 플러그인 오버헤드 (조사 — 사용자 질문)

`_run_author` 와 같은 argv · env(`bedrock_author_env`)로 짧은 질문을 보내 봉투 usage 를 쟀다(프로브 5회 ≈ $0.15, `scratchpad/probe_author_overhead.py`).

| 조건 | 도구 수 | 프리픽스 토큰(cache write) | Haiku 5.5 실측 | Opus 5.5 |
|---|---|---|---|---|
| 호스트 그대로(plain = `_run_author` 호스트 실행) | 81 + SessionStart 훅 2 | 75,046 | $0.0104 · 12.8s | ≈$0.38 (토큰 × $5/M 추정) |
| 빈 HOME (= 컨테이너 상당) | 20 | 24,348 | $0.0034 · 5.5s | $0.127 실측 |
| `--bare` | 3 | 1,634 | $0.0003 · 2.4s | $0.010 실측 |

- 프로브 답변이 직접 증언: plain 은 "Respond in Korean" 훅과 "skill 을 먼저 호출하라" 훅을 받았다 — 비용만이 아니라 **행동 오염**(그림 스펙 작성 중 도구 · skill 호출로 다턴 가능).
- 컨테이너에는 사용자 플러그인이 없어 빈 HOME 행과 같다 → (d) 의 그림 호출은 회당 ≈$0.15.
- `--bare` 는 `_run_author` 가 넘기지 않아 저장소 변경이 필요(미착수). 금액은 CLI 의 Anthropic 정가 기준(앱 `cost_usd` 와 같은 계산) — Bedrock 청구와 다를 수 있다.

## 4. 배포 runbook (승인 뒤)

1. `uv run python -m briefing.runtime.deploy_runtime` — CodeBuild ARM64 이미지 빌드(Chromium + 글꼴로 이미지 ≈ +400MB, 빌드 시간 증가) → READY. `.env` 의 `WEEKLY_FIGURE=1` 이 이번부터 전달된다.
2. 확인: `aws bedrock-agentcore-control get-agent-runtime --agent-runtime-id <id> --region us-east-1 --query '{v:agentRuntimeVersion,s:status}'` + 런타임 env 에 `WEEKLY_FIGURE` 가 있는지.
3. 05:00 KST 데일리 근처는 피한다(배포 중 run 과 겹치지 않게).

## 5. 검증 체크리스트 — 11-14 첫 자동 run

| 항목 | 기대 | 결과 |
|---|---|---|
| 06:00 build 로그 | `figure ready`(notes) · `calls_json` 에 그림 호출 1~3회 | |
| 표 11-14 항목 | `figure_status=ready` · `figure_png_b64` 있음 · 항목 < 400KB | |
| 07:00 메일 | ③ 「그림 2」 자리에 PNG 인라인(ASCII 블록은 빠지고 캡션 줄은 남음) · 한글 글꼴 정상 | |
| 그림이 빠졌다면 | notes 에 `그림 skipped(playwright 없음…)` / `그림 실패: …` / `그림 b64 생략(…)` 중 어느 것인지 → 원인 분기 | |

**남은 위험(배포 전엔 못 잰다).** 컨테이너 안 Chromium 실행은 11-14 build 가 첫 실측이다 — 호스트엔 docker 가 없어 이미지를 로컬에서 못 돌린다. microVM 의 `/dev/shm` 이 작으면 렌더가 실패할 수 있고(그때는 `--disable-dev-shm-usage` 런치 인자 후속), 실패해도 기사는 그대로 나간다(설계). playwright 1.58 이 Debian 12 arm64 를 지원하고 Chromium 1208 이 호스트와 같은 빌드인 것은 패키지 레지스트리로 확인했다.

## 6. 후속 (미착수 · 별도 승인)

- 11-14 뒤 `WEEKLY_MAX_REVISIONS=1` → 2 되돌리기(`.env`).
- `ready` 전이가 이전 실패의 `error` 필드를 안 지운다(11-07 항목에 묵은 "write: TimeoutExpired") — `building` 전이에서 비우기.
- `pull` 이 `figure_png_b64` 를 `issues/<date>.figure.png` 로 풀어 주기(사람이 읽는 사본에 그림).
- (c) 용 scratchpad 스크립트 2개(`make_figure_1107.py` · `attach_figure_1107.py`)는 미실행 — 필요하면 수동 복구 도구로 승격.
