# 메일 카드 밴드 발행처 → 주제 6칸 — 전달 기록 (2026-10-25)

> **상태: SHIPPED · 배포됨 · 관리자 시험 발송 OK(03:01Z) · 정기 첫 run 검증 대기** — main `fa72db0`(브랜치 `topic-grouping` 13 커밋, `--no-ff`) · `deploy_runtime` READY(v59→**v60**, 2026-10-25 02:46Z) · ECR `20261025-024503-695`
> 스펙 `docs/superpowers/specs/2026-10-24-topic-grouping-design.md` · 플랜 `docs/superpowers/plans/2026-10-24-topic-grouping.md` · 발단 = 사용자 PRD `docs/work_note/Oct-2026/261024-Reorder-Content/reorder-prd.md`

## 1. 무엇이 바뀌었나

- **카드 밴드 = 기사 단위 주제 6칸**(`core/areas.py`, 메일 순서): AI Agents → Applied AI → Models & Releases → Inference & Hardware → Safety, Security & Policy → Industry & Business. 헤드라인 칸(AI타임스)도 같은 6칸·순서. 발행처(카탈로그 category) 밴드는 제거 — 그 자리에 **출처 집계 줄** `출처 · Amazon (AWS) 7 · Anthropic 6 · …`.
- **라벨 1콜로 핵심 3 + 분야**: 기존 핵심 3 라벨 호출에 `area` 필드 추가(추가 호출 0). 모델 = `LABEL_MODEL_ID`(.env = Sonnet 5.5, `runtime_env` 화이트리스트로 컨테이너 전달). 입력 = 보이는 카드 전부(⚠ 포함), 핵심 3 선택은 PUBLISH 라벨만. 불완전·예외 → 같은 입력 1회 재시도 → 그래도 안 되면 핵심 3·밴드 **함께 생략**(평평: 핵심 3 있으면 `요약 N건` 단일 밴드). 부분 라벨은 쓰지 않는다. 분야는 캐시하지 않는다(run 당 라벨, 같은 묶음 사용자끼리 memo 공유).
- **글자 위계**(사용자 지적 2026-10-25): 헤드라인 칸 제목 = 본문 크기(13px 지정 제거) · 분야 밴드(◆)·헤드라인 칸 머리(◇) 15/14px → **20px**(브리핑 제목 22 > 묶음 머리 20 > 기사 제목 19 > 본문).
- Bedrock: Sonnet 5.5 는 `thinking: disabled` 가 400 → 라벨 전용 헬퍼 `thinking: between_tools`(스모크 확인), `maxTokens 6000`. 호출마다 `[WARN areas 호출] model=…` 한 줄.

## 2. 근거·게이트

- 7일(10-17~23) 132편 손분류: 장르 ≈ 발행처(76%), 주제는 발행처와 독립(37~42%) → 주제 축 하나(`work_note/…/classify-7d.md`).
- 머지 게이트(골든셋 131편 채점, 실 Sonnet 5.5): 정확 일치 **87.0%**(안정성 93.9%) → 규칙 ⑤ 우선 문구 뒤 **91.6%**(게이트 85% 둘 다 PASS). 헤드라인 50제목 × 2회: 미배정 0 · 일치 98%. 비용 ≈ $0.75. 결과 `work_note/…/golden-eval-*.md`·`headline-check-*.md`.
- 최종 리뷰(별도 리뷰어) Critical 1·Important 1 수정(`c4a9c7b`): 잘려 나갔던 pipeline 회귀 테스트 18개 복원, 분야 분포 로그 4000자. Minor 5 보류(아래 §5).

## 3. 배포

| 항목 | 값 |
|---|---|
| 배포 시점 결정 | 처음 "U8 ② 뒤"(02:3xZ) → 같은 날 사용자 `deploy` 로 **즉시**. 사전 확인: `.env` 요약 모델 Sonnet 5(② 미착수)·운영 v59 그대로 → 관찰 창 없음·혼입 없음. **U8 ② 기준선 = 이 변경 포함** |
| IAM | 런타임 역할 `bedrock:InvokeModel` 리소스 `inference-profile/*`·`foundation-model/*`(`arn:aws:bedrock:*`) → Sonnet 5.5 글로벌 프로파일 커버 |
| 런타임 | `briefing_agent-b9uh7rDAqL` v60 READY 02:46:15Z · 환경변수 17 → **18**(`LABEL_MODEL_ID=global.anthropic.claude-sonnet-5-5` 추가; AUTHOR Sonnet 5·RELEVANCE Haiku 5.5·`RELEVANCE_LLM_ENABLED=1` 불변) |
| 빌드 컨텍스트 | `.agentcore_build/briefing/core/areas.py` 존재 · render 20px 머리 2곳 · deploy_runtime 화이트리스트 포함 |
| 실행 이미지 | `containerUri` = `…/bedrock-agentcore-briefing_agent:20261025-024503-695` — 배포 로그의 빌드 태그와 일치(캐시된 옛 이미지 아님) |
| 관리자 시험 발송(사용자 지시, 02:54Z accepted → **03:01Z sent**) | 임시 행 `tmp-moongons-topic-test`(admin 복제, 접수 직후 삭제) · `--mode scheduled --now-utc 2026-10-25T20:00Z`(run_date = 오늘 밤 정기 run 과 동일 → cross-day dedup 보호). 결과: **sent · 발행 11 · ⚠ 0 · 244초 · $1.11**(아침 run 의 사실층 카드 캐시 재사용). 로그: `[WARN areas 호출] model=global.anthropic.claude-sonnet-5-5 maxTokens=6000` 1회 · `[WARN areas 라벨] AI Agents 3 · Applied AI 3 · Models & Releases 3 · Safety, Security & Policy 2`(11장 제목 전부, 절단 없음; Inference·Industry 0 → 밴드 숨김) · `[WARN top picks 선정] p1 OpenAI(isolated agents) | p2 applied(patent attorneys) | p2 Anthropic(Scion)` · **폴백(`평평`) 줄 없음** · 헤드라인 분야 호출 WARN 없음(= all-or-nothing 성공). sent-log 에 tmp 행 흔적 남음(이전 시험들과 같음) |
| 하지 않은 것 | `deploy_scheduler`(DRY_RUN 리셋 풋건) · `deploy_api`(webapi 는 바뀐 모듈 미사용) · M3 `run_golden.py --passes 2` 재측정(미요청) · CLAUDE.md 한 줄(사용자 미커밋 변경과 섞여 보류) · main push(미요청) |

## 4. 첫 run 검증 체크리스트 (2026-10-26 05:00 KST = 10-25 20:00Z)

CloudWatch `/aws/bedrock-agentcore/runtimes/briefing_agent-b9uh7rDAqL-DEFAULT`:
- [x] `[WARN areas 호출] model=global.anthropic.claude-sonnet-5-5 maxTokens=6000` — run 당 **1회**(카드 라벨; 헤드라인 분야 호출은 같은 모델이지만 이 로그를 남기지 않음) — 시험 발송에서 확인
- [x] `[WARN areas 라벨] AI Agents N: … | Applied AI N: … ` 분포 줄 — 보이는 카드 제목이 **전부** 들어 있음(절단 없음) — 시험 발송 11/11 확인
- [ ] `[WARN top picks 선정] p1 … | p2 …` — 티어 규칙(5대 기업 큰 발표 ≤2·응용 ≥1)
- [x] `areas 라벨 … → 핵심 3·분야 밴드 생략(평평)` 가 **없음**(있으면 사유 확인: 400·파싱·area 미배정) — 시험 발송 확인(정기 run 에서 재확인)
- [ ] sent-log 7명 `status=sent`
메일(관리자 수신분):
- [ ] 부제 아래 `출처 · Amazon (AWS) n · …` 집계 줄
- [ ] 핵심 3 아래 분야 밴드(◆, 20px) AREAS 순, 빈 칸 숨김, 칸 안 AWS 먼저
- [ ] 헤드라인 칸 머리(◇) 20px · 제목 글자 = 본문 크기 · 소제목 6칸 어휘
- [ ] ⚠ 카드가 자기 분야 칸 안에 있음(핵심 3 에는 없음)

통과하면: 이 문서 상태 → **SHIPPED·LIVE**, `docs/README.md` 같은 줄, CLAUDE.md 한 줄(카드 밴드 = 주제 6칸), 메모리 `catalog-publisher-taxonomy` 갱신, `.superpowers/sdd/2026-10-24-topic-grouping/` 삭제.

## 5. 보류 Minor (리뷰어, 미수정)

- M1 `test_run_briefing_groups_by_area_and_dates_header` 가 집계 줄 덕에 통과 — 단언·이름 갱신.
- M2 폴백 로그 라벨 `areas 라벨`(스펙 예시 `areas 폴백`) — 런북 grep 은 일관.
- M3 출하 프롬프트(규칙 ⑤) 안정성 2회차 미측정(`--passes 2` ≈ $0.25).
- M4 러너 stability 모수가 분류 불가 1장 포함(132 vs 131).
- M5 `headline_check.assign_tolerant` 파싱 복제·비공개 이름 사용.

## 6. 함정(다음 사람을 위해)

- `runtime_env` 화이트리스트에 없는 env 는 **조용히** 기본값 — 모델 id 류는 반드시 테스트(`test_runtime_env_forwards_label_model_id_when_set`)로 고정.
- Sonnet 5.5 Converse 는 `thinking: disabled` 400 — 모델 바꿀 땐 `label_request_fields` 스모크 먼저.
- 라벨 실패 = 핵심 3 도 동시 상실(한 호출) — 재시도 1회로 완화. 로그 `areas 라벨 … 평평` 이 신호.
- 편집 교훈: `s[:start] + new` 식 꼬리 치환은 뒤 섹션을 지운다(리뷰 C1) — 섹션 경계로 잘라 붙일 것.
