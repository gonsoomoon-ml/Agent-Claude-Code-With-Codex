# 데일리 브리핑 백로그 (Backlog)

> **이 파일이 목록의 진실이다.** 데일리 브리핑(Verified Dispatch)의 열린 문제·아이디어와, 이미 기각·보류한 제안을 한곳에 둔다.
> 여기는 **목록**만 둔다 — 정의·측정·선택지 같은 상세는 「근거」 칸의 문서에 있다.
> 주간(Field Experiment)은 `field-experiment/README.md` 가 진실이라 여기서 다루지 않는다.
> 처음 만든 날 2026-11-18. 그 전에 끝난 항목은 옮기지 않았다 — 이력은 `docs/README.md` 색인과 각 전달 기록에 있다.

## 규칙

1. **한 항목 = 한 줄.** 제목은 한 문장, 다음 행동은 한 구절. 길어지면 근거 문서에 쓰고 링크한다.
2. **번호는 고정.** `B-NNN` 은 한 번 붙이면 바꾸지 않고 다시 쓰지 않는다. 새 항목은 가장 큰 번호 다음.
3. **상태가 바뀌면 그 작업의 커밋에서 이 줄도 고친다.** 끝난 항목(완료·수용)은 「닫힌 항목」으로, 기각·보류한 제안은 「기각·보류」로 옮긴다.
4. **새 제안을 내기 전에 「기각·보류」를 먼저 본다.**
5. **공개 저장소다.** 사람 이름·이메일·계정 식별자를 쓰지 않는다.

## 상태 값 (일하는 순서 그대로)

| 상태 | 뜻 | 다음으로 넘어가는 조건 |
|---|---|---|
| 아이디어 | 관찰만 있고 문제 정의 전 | 정의(관찰 · 왜 문제 · 범위)를 보인다 |
| 정의됨 | 정의를 보였거나 문서로 기록했다 | 사용자 승인 → 원인·선택지 조사 |
| 선택 대기 | 원인과 선택지를 보였다 | 사용자가 고른다 |
| 구현 승인 대기 | 구현 계획을 보였다 | 사용자 "go" |
| 구현됨 | 코드·테스트가 끝났다 | 사용자의 commit · push · deploy 지시 |
| 배포됨 | 운영에 나갔다 | 첫 정기 run 확인 |
| 완료 | 확인까지 끝났다 | — |
| 수용 | 고치지 않기로 했다(무변경) | — |
| 건너뜀 | 지금은 다루지 않는다(기각 아님) | 같은 현상이 다시 보이면 새 관찰로 보고 |

중요도 = 상 · 중 · 하. 사용자가 정한다(처음 값은 제안).

## 열린 항목

| ID | 제목 | 중요도 | 상태 | 다음 행동 | 근거 |
|---|---|---|---|---|---|
| B-001 | 평일 메일이 카드 21장 안팎이라 끝까지 읽기 무겁다 | 상 | 아이디어 | 문제 정의 — 카드별 중요도 분포 측정부터 | 측정 메모 2026-11-18 · 「보류」 압축 문턱 · `docs/deliveries/2026-07-08-form-two-stage-delivery.md`(깊이 full = summary) |
| B-002 | 독자가 무엇을 여는지 재지 않는다(열람·클릭 데이터 없음) | 상 | 아이디어 | 문제 정의 | `docs/README.md` 색인 summary-quality 행의 OPEN "독자계측" |
| B-003 | 수집 구멍을 우연히만 발견한다(최근 3건) — 자동 탐지 | 중 | 아이디어 | 문제 정의 | `docs/work_note/Oct-2026/261030-improve-today-briefing/README.md`(+ 행: anthropic-eng 0건 · research 목록 일부 노출) · `docs/work_note/Nov-2026/261114-duplicate-articles-7days/README.md`(문제 4와 한계) |
| B-004 | OpenAI 공식 발표가 재보도로만 들어온다(1차 소스 없음) | 중 | 아이디어 | 문제 정의 — 제목 전용 칸의 적법성 등급 확인 먼저 | `src/briefing/core/retrieval/catalog.yaml` openai 주석(2026-07-17) |
| B-005 | 해석 단락이 하루 약 2장 폴백으로 사라진다(미검증 수치 lint) | 중 | 정의됨 | 사용자 검토 → 승인하면 원인·선택지 | `docs/work_note/Oct-2026/261030-improve-today-briefing/problem-6-interp-lint-fallback.md` · 측정 메모 2026-11-18 |
| B-006 | 발송 실패·빈 발송을 알리는 장치가 없다 | 중 | 아이디어 | 문제 정의 | `docs/deliveries/2026-08-10-fetch-timeout-delivery.md`(OPEN: 무통보 실패, 증거 2건) · 측정 메모 2026-11-18 |
| B-007 | anthropic-research 팀 페이지의 옛 글 4쪽이 매 run 경고 4줄을 낸다(카드 영향 0) | 하 | 선택 대기 | A(`exclude_paths` 4줄, 추천) / B(창 밖이면 경고 없이 폐기) 중 선택 | `docs/deliveries/2026-11-01-hub-gate-delivery.md` §6 |
| B-008 | ai.meta.com 글의 날짜가 틀리게 추출된다(Muse 글 → 2022-11-18) | 중 | 아이디어 | 문제 정의 | `docs/work_note/Oct-2026/261030-improve-today-briefing/README.md`(+ 행: Meta 날짜) |
| B-009 | 요약의 고유명사가 claims 에 없다(그림자 검사 `summary_name_not_in_claims`) | 하 | 아이디어 | 문제 정의 — 표본을 원문과 대조한 뒤 | 같은 README #9 |
| B-010 | 날짜 없는 목록 소스가 매일 같은 옛 글을 다시 연다(독자 영향 0) | 하 | 정의됨 | 사용자 검토 | `docs/work_note/Oct-2026/261030-improve-today-briefing/problem-7-html-listing-rewalk.md` |
| B-011 | 본 발표 글이 형제 글의 재보도로 빠진다(Gemini 4 Hydrogen, 2026-11-12) | — | 건너뜀 | 같은 유형이 다시 보이면 보고 | `docs/work_note/Nov-2026/261114-duplicate-articles-7days/README.md` 사례 5 |
| B-012 | 재보도 판정 응답 JSON 이 이유 문장의 큰따옴표로 깨진다 | — | 건너뜀 | 다른 쌍에서 보이면 보고 | 같은 README 사례 6 |

메모: 10-30 목록의 #8(`fetch stub` 노이즈)은 허브 관문으로 해소됐고, 남은 반복 경고는 B-007(스텁 3 · offsite 1)과 B-008(Muse offsite 2)이 맡는다.

## 측정 메모

- **2026-11-18** (B-001 · B-005 · B-006 · B-007 근거) — 정기 발송 run_date 2026-10-28~11-17, 21회.
  - 21회 모두 7명에게 발송, 격리 0.
  - 카드 수: 평일 15회 중앙 21장(14~30장) · 주말 6회 5~12장.
  - 최근 14회(11-04~11-17) 경고: 해석 폴백 `gate interp` 28장 · `fetch stub` 3줄/run · `fetch offsite` 3줄/run(11-09 부터 4줄 — 늘어난 1줄은 미조사) · 카드 실패 `pipeline card` 0 · 수집 시간 초과 0. 로그에는 경고 한 건이 두 줄로 남아 절반으로 셌다.
  - CloudWatch 알람 0개.
  - 카드별 중요도는 로그에 남지 않아 분포를 못 쟀다(B-001 정의의 첫 단계).
  - 방법: `briefing-sent-log` 조회 + 런타임 로그의 경고 꼬리표 집계(읽기 전용).

## 기각·보류

### 기각 (재제안 금지)

| 날짜 | 기각한 제안 | 이유 한 줄 | 출처 |
|---|---|---|---|
| 2026-06-25 | Verified Quiet(검증된 침묵) · Source-Trust 별칩 · Confidence-tier 독립 표시 · Audio 를 제품으로 포지셔닝 | 비-사건을 인증하면 제품이 싸우는 과신을 스스로 만든다 | `design/architecture/value-roadmap.md` |
| 2026-07-06 | 검증 없는 해석층 · 여러 lens 를 한 메일에 나란히 | 검증 배지가 미검증 해석에 후광을 준다 · 아침 본편을 무겁게 하지 않는다 | `design/architecture/card-layering-analysis.md` |
| 2026-07-11 | 소스 선별을 기사당 이진 판정으로 · render 단계에서 선별 | 스펙의 「기각한 대안」 참조 | `docs/superpowers/specs/2026-07-11-llm-select-topk-design.md` |
| 2026-07-17 | OpenAI 본문 차단 우회 | 접근 통제 우회 금지 | `src/briefing/core/retrieval/catalog.yaml` openai 주석 |
| 2026-07-18 | 요약 길이 계약 3종 | 병은 길이가 아니라 앞부분 쏠림(lead bias) — 길이는 관측치일 뿐 | `docs/superpowers/specs/2026-07-27-ai-relevance-axis-design.md` |
| 2026-07-27 | 요약 규칙의 "둘 다 담는다" 조항 | 지표는 좋아지지만 장문 기사가 시간 초과로 죽는다 | `docs/deliveries/2026-07-27-ai-relevance-axis-delivery.md` §5 |
| 2026-07-27 | 관련성 판정자의 범위를 좁히기 | 독자가 원하는 AI 기업 재무 뉴스가 함께 잘린다 | `docs/superpowers/specs/2026-07-27-ai-relevance-axis-design.md` |
| 2026-07-28 | 해석층 문체 후보 5종(3칸 구조 · 침묵 허가 · 반사실 · 조건부 · 관계형) · 메타 언급 금지 변형 · 라벨 `(해석)` → `(통찰)` | 전부 통찰 4% 정체 — 문제는 문체가 아니라 재료 · 라벨은 신뢰 경계 표시 | `docs/deliveries/2026-07-28-interp-layer-quality-delivery.md` §3 · §6 |
| 2026-08-10 | 수집 시간 상한 대안 4종(`DOWNLOAD_TIMEOUT` 만 축소 · `socket.setdefaulttimeout` · 소스 병렬화 · 전역 3층 예산) | 전달 기록 §5 참조 | `docs/deliveries/2026-08-10-fetch-timeout-delivery.md` §5 |
| 2026-09-23 | 사용자별 발송 시각 분산 | 같은 run 의 결과를 공유해 두 번째 수신자부터 비용 0 — 전원 같은 시각 유지 | 사용자 결정(저장소 문서 없음) |
| 2026-10-18 | 교차 소스 중복 차단(주제당 상한 · 같은 사건 묶기 · 소스 순위로 한 장만 · 2차 소스 일괄 제외) | 같은 사건의 다른 시각은 중복이 아니다 | `docs/deliveries/2026-10-28-cited-rereport-dedup-delivery.md` |
| 2026-10-20 | 핵심 3 을 LLM 이 한 번에 고르기 · 등급(회사 목록)까지 LLM 에 맡기기 | 7일 실측에서 논란·타사 발표를 큰 발표로 골랐다 — LLM 은 라벨만, 배분은 코드 | `src/briefing/core/top_picks.py` 머리 주석 |
| 2026-10-28 | 재보도에 "새 정보를 더했나" 판정 · 재보도 판정자의 사고 끄기 | 0/12 제거로 실패 · 끄면 경계 쌍을 놓친다 | `docs/superpowers/specs/2026-10-28-cited-rereport-dedup-design.md` |
| 2026-10-30 | 핵심 3: 큰 발표 중요도 절대 문턱(≥4) · "연구 결과 → other" · 중요도 앵커 · 번갈아 채우기 · 중요도 우선 | 점수가 3~4 에 뭉치고 run 마다 흔들린다 | `docs/deliveries/2026-10-30-top-picks-priority-delivery.md` §2 |
| 2026-10-31 | 밴드 쏠림 대책: 특정 소스만 수정 · 같은 소스 3장째부터 한 줄 · 커뮤니티 소제목/태그 · 표시 단계 "상위 3" · 선별 프롬프트 수정 · 라벨 호출 앞당기기 | 쏠림은 한 소스만의 현상이 아니다 · 검증된 요약을 숨긴다 — 하려면 별도 설계(B-001) | `docs/work_note/Oct-2026/261030-improve-today-briefing/README.md` #4 · #4b |
| 2026-11-01 | 허브 페이지 대책으로 RSS · 사이트맵 · 발행 뒤 중복 판정 / anthropic-eng 소스 제거 / 팀 페이지를 새 소스로 · 메인 목록 대체 | 같은 README 의 각 행 참조 | 같은 README(+ 행 3개) |

### 보류 (조건이 생기면 다시)

| 날짜 | 보류한 제안 | 다시 볼 조건 | 출처 |
|---|---|---|---|
| 2026-10-30 | 분야 라벨 다수결(3회 호출) | 분야 흔들림이 핵심 3 을 자주 바꿀 때 | `docs/work_note/Oct-2026/261030-improve-today-briefing/README.md` #3 |
| 2026-10-31 | 중요도 2 이하 카드를 압축하는 문턱 | B-001 설계에서 | 같은 README #4b |
| 2026-10-31 | PyTorch KR 캡 3 + 새 글끼리만 선별 | 캡의 뜻이 "사용자당 상한"이 아니게 되는 점을 받아들일 때 — 코드는 브랜치 `draft/4b-fresh-first-cap3` | 같은 README #4b |
| 2026-11-02 | 창 밖 페이지를 경고 없이 버리기(B-007 의 B안) | B-008(날짜 추출)을 고친 뒤 — 지금 하면 날짜 오류가 로그에서 사라진다 | B-007 |

## 닫힌 항목

아직 없음(2026-11-18 이후 끝난 항목을 여기에 옮긴다).
