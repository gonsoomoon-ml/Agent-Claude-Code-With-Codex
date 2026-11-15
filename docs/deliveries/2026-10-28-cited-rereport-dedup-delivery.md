# 재보도 dedup — 이미 보낸 원문을 옮긴 기사 빼기 — 전달 기록 (2026-10-28)

> **상태: SHIPPED · LIVE · 정기 첫 run 검증 대기** — main `c074f4c`(origin 동기화, 브랜치 `feat/cited-rereport-dedup` fast-forward) · `deploy_runtime` READY v63 → **v64**(2026-10-28 14:12Z, ARN 불변 `briefing_agent-b9uh7rDAqL`)
> 스펙 `docs/superpowers/specs/2026-10-28-cited-rereport-dedup-design.md` · 플랜 `docs/superpowers/plans/2026-10-28-cited-rereport-dedup.md` · 발단 = 10-25 카드 "Anthropic says one AI agent beats many subagents"(The Decoder) — 원문(Claude Blog)이 10-22 에 이미 나감

## 1. 무엇이 바뀌었나

- **인용 키:** 수집 때 기사 본문 안의 다른 사이트 링크를 `cite_key`(URL 키 + 첫 경로 언어 코드 제거 — `/de/`·`/ko/`·`/zh-cn/`)로 뽑아 run 동안 들고 다닌다(`FetchedArticle.cited` → `curate(cited_out=)`). source-store 에는 저장하지 않는다. 대상 경로 = html 리스팅·사이트맵(`_extract_article`)·RSS 전문. 피드 요약 폴백·Gateway·헤드라인 칸은 키 없음(검사 안 함).
- **쌍 찾기(사용자별, 기존 같은 기사 dedup 뒤):** (a) 인용 키가 이 사용자에게 지난 90일 보낸 기사 URL(`published_keys(url_index=)`)에 걸림 · (b) 오늘 다른 생존 후보 URL 에 걸림. 서로 인용이면 빅테크 1차 글을 남기고, 아니면 발행이 이른 쪽을 남긴다. 한쪽이라도 날짜만 있으면 같은 날은 판정하지 않는다.
- **판정:** Haiku 5.5(`RELEVANCE_MODEL_ID`)에게 "B 는 주로 A 와 같은 발표에 대한 글인가"를 묻는다. 같으면 B 를 빼고 A 는 유지한다. 판정 실패·예외는 B 유지(fail-open). 판정 결과는 run 메모로 사용자 간 공유한다. **thinking 을 끄지 않음·1500 토큰**(§2) — 켜짐이 보장되는 것은 아니다(§6, 2026-11-14 정정).
- **관측:** `[WARN pipeline rereport] <user>: 재보도 제외 — <B> ← <A> (<reason>)` · `판정 실패 — 통과(fail-open): <B>`. 제외 건수는 기존 `deduped` 집계(`이전 발행 N건 제외(ledger)` dprint)에 합쳐진다.
- **재생 도구:** `scripts/dedup_audit/rereport_replay.py`(프로덕션 읽기 전용 + 실제 판정자).

## 2. 근거·게이트

- 실험(7 run, 사용자 1명): 후보 125 × 보낸 기사 1,590 ≈ 20만 쌍 → 인용으로 걸린 쌍 12. "새 정보를 더했나" 판정은 0/12 로 실패했고, "같은 발표인가" 판정은 10 제외·2 유지.
- **머지 게이트**(`rereport_replay.py --since 2026-10-21 --until 2026-10-27 --expect-dropped 10 …`): 결과 **판정 13 · 제외 10 · PASS**. 제외 10건 = The Decoder 6 + PyTorch Korea 4. 유지 3건 = gitai · AAIF 4개 프로젝트 묶음 · Google AI "AI Quest"(실험에 없던 쌍).
- ★ **게이트가 판정자 설정 결함을 잡았다:** spec 처음 판은 관련성 판정자처럼 `thinking: disabled`·300 토큰이었는데, 이 설정으로는 제외 9 → 재실행 8 로 흔들렸고 AAIF 기증 한국어 심층 글을 3/3 놓쳤다. 13쌍 × 3회 비교에서 끔 36/39, 실험판(thinking 켬) 39/39·흔들림 0 → thinking 켬으로 정정(spec §4.3). 관련성·선별 판정자는 그대로 끈다.
  - ★ **2026-11-14 정정:** "켬"은 `thinking: disabled` 를 보내지 않는다는 뜻일 뿐이다. Haiku 5.5 는 필요할 때만 사고해서(effort 기본) 운영 설정 104회 호출 중 사고 블록은 31회뿐이었다. "39/39·흔들림 0"은 그 13쌍에서만 참이고, 출시 뒤 놓친 쌍이 나왔다(§6).
- 최종 리뷰(별도 리뷰어): Critical 0. Important 2건 수정 뒤(`c074f4c`) 게이트 재실행 PASS(13·10).
  - 영어 경로와 겹치는 언어 코드(uk·id·it·ar·no·hi·he·el·da)는 지우지 않는다 — `/uk/technology` 등이 다른 글과 같은 키가 되는 오탐을 막는다.
  - 서로 인용 쌍에서 날짜만 있는 발행일을 자정으로 비교하지 않는다(같은 날이면 판정하지 않음).
- 테스트 807 passed · ruff clean.

## 3. 배포

| 항목 | 값 |
|---|---|
| 런타임 | `briefing_agent-b9uh7rDAqL` **v64** READY 14:12:23Z · env 19개(새 env 없음 — `RELEVANCE_LLM_ENABLED=1`·`RELEVANCE_MODEL_ID=global.anthropic.claude-haiku-5-5`) |
| IAM | 변경 없음 — Converse 는 기존 `bedrock:InvokeModel` 로 커버 |
| ★ 함께 실린 변경 | **`37c6f22` 원문 상한 `MAX_SOURCE_CHARS` 8,000 → 20,000자**(다른 세션 `261028-aritcles-more-than-9000-chars`, 사용자 결정으로 동반 배포). 그 세션이 같은 체크아웃에서 main 대신 이 feature 브랜치에 커밋해 브랜치 안에 들어왔다. 그 세션의 순차 trial(5기사 × 8K/20K): author 13~19s · claim 당 검증 최대 3.1s · 검증 입력 claim 당 +21% · 34/35 VERIFIED. 재보도 판정 입력은 게이트에서 검증한 앞 8,000자를 유지한다 |
| 하지 않은 것 | `deploy_scheduler`(DRY_RUN 리셋 함정) · Gateway 재배포(`cited` 필드 추가는 호환, 기본 off) · `deploy_api`(webapi 무관) |

## 4. 첫 run 검증 체크리스트 (2026-10-29 05:00 KST = 10-28 20:00Z)

CloudWatch `/aws/bedrock-agentcore/runtimes/briefing_agent-b9uh7rDAqL-DEFAULT`:
- [ ] `[WARN pipeline rereport] … 재보도 제외 — B ← A (reason)` — 줄마다 B 가 정말 A 의 재보도·번역인지 확인한다. 다른 주제 글이 빠졌으면 `REREPORT_SYSTEM` 조정 후보.
- [ ] `판정 실패 — 통과(fail-open)` 가 없거나 드묾. 많으면 Converse 오류나 텍스트 블록 없음(사고에 토큰 소진)을 의심한다.
- [ ] `재보도 단계 실패` 줄 없음.
- [ ] (20K) 이미 보낸 기사를 다시 받아 `source_id` 가 바뀐 경우가 `[WARN pipeline dedup] … url 키 일치`/`title 키 일치` 로 걸러졌는지 확인 + `uv run python scripts/dedup_audit/replay.py audit --since 2026-10-29` → 중복 발송 0.
- [ ] sent-log 7명 `status=sent`.
- [ ] 1주(~11-04) 동안 `pipeline rereport` 줄 반복 검토(spec §7 사후 관측).

## 5. 남긴 것(Minor, 보류)

- 같은 날 A←B←C 사슬에서 C 의 제외 여부가 소스 순서에 따라 달라진다(A 는 항상 유지).
- URL 에 `)` 가 있으면 본문 링크가 잘린다 — 그 링크를 놓칠 뿐 B 는 유지된다.
- 2번째 사용자부터 판정 메모를 확인하기 전에 A 를 source-store 에서 한 번 더 읽는다(하루 수 회).
- spec §7 의 파이프라인 수준 테스트 일부 없음 — "기존 dedup 이 먼저 돈다"·같은 날/서로 인용·판정 실패 warn.
- 파이프라인 dprint `이전 발행 N건 제외(ledger)` 문구에 재보도 제외가 섞인다(종류는 warn 라벨로 구분).
- `cite_key("https://x.com/de")` → 호스트만 남은 키(보낸 기사는 경로가 있어 무해).

## 6. 후속 (2026-11-14) — 판정 답 순서: 이유 먼저, 값 나중

> **상태: 구현·검증 완료 · 미병합 · 미배포** — 브랜치 `worktree-rereport-reason-first`(worktree `.claude/worktrees/rereport-reason-first`)

- **관찰(최근 7회 발송 점검):** 이미 보낸 원문의 한국어 소개 글(PyTorch Korea) 2건이 링크로 걸려 판정까지 갔는데 "다름"으로 통과했다 — Hugging Face "Transformers Model Integration Contracts"(11-03) → 소개 글(11-05), Anthropic Engineering "The components of agent memory"(11-07) → 소개 글(11-09). 같은 기간 한국어 소개 12건 중 10건은 걸렀다. 판정 이유에는 "A 의 한국어 소개"라고 적으면서 값은 `false` 였고, 일부 응답은 첫 JSON 뒤에 스스로 `true` 로 정정했다(코드는 첫 JSON 만 읽는다).
- **원인:** 답 형식이 값(`same`) 먼저·이유 나중이라, 사고 없이 답할 때 값을 쓴 뒤에 따져 본다. 원문이 8,000자에서 잘리는 것(19,994자·9,720자)만으로는 설명되지 않는다 — 맞게 걸러진 소개 글 7건도 원문이 8,000자를 넘는다.
- **고친 것:** `REREPORT_SYSTEM` 끝줄을 `{"reason": …, "same": …}` 순서로(`src/briefing/core/retrieval/rereport.py`). 파서·토큰 상한·비용은 그대로.
- **실험**(정답을 사람이 붙인 47쌍 = 게이트 주간 12 + 출시 뒤 발송된 쌍 17 + 운영이 제외한 쌍 18, 운영과 같은 모델):

  | 변형 | 놓친 2쌍 | 나머지 45쌍 | 비고 |
  |---|---|---|---|
  | 운영 그대로 | 0/10 | 90/90 | |
  | **답 순서만 바꿈(채택)** | 20/20 | 225/225 | 쌍마다 5회·흔들림 0 |
  | effort=high | 8/10 | 90/90 | 메모리 쌍 3/5 |
  | 본문 20,000자 | 10/10 | 88/90 | 맞게 빼던 AnySpeechRecognizer 소개 글을 놓침 |
  | 마지막 JSON 읽기 | 4/10 | 90/90 | 스스로 정정한 응답만 구제 |

- **경계 2쌍(채점 제외) 판정 변화:** Mistral Large 4 한국어 소개(11-03, ← Hugging Face "Welcome Le Chonk")는 유지 → 제외(8/8). Gemini 4 Hydrogen 원 발표(← Search 글, 11-12 운영에서 제외됨)는 유지 쪽으로 기울지만 여전히 갈린다(8회 중 유지 6) — 별도 문제로 남긴다.
- **재생 게이트:** 2회 모두 판정 12 · 제외 9 · 유지 3(gitai · AAIF 묶음 · AI Quest) — 기대값 9 로 **PASS**. ★ 기대값이 10 → **9** 로 바뀌었다: 발단이 된 10-25 The Decoder 기사가 그 뒤 수정돼 본문에 원문 링크가 없다(코드 변경과 무관 — 옛 프롬프트로도 12쌍). `rereport_replay.py` docstring 예시도 9 로 고쳤다.
- **스펙·플랜은 고치지 않았다**(`docs/README.md` 규칙 ② 불변 역사): 스펙 §4.3 의 "thinking 기본(켬)"·응답 JSON 순서, 플랜의 프롬프트 문구·게이트 명령(`--expect-dropped 10`)은 2026-10-28 시점 기록이다. 현재 진실 = 이 절 + `rereport.py` + `docs/README.md` 색인.
- **도구·데이터:** `docs/work_note/Nov-2026/261114-duplicate-articles-7days/`(7회 발송 점검 · 47쌍 목록 · 변형별 판정 결과 · 게이트 출력).
- **테스트:** `tests/test_rereport.py::test_rereport_prompt_asks_reason_before_same`(RED → GREEN) + 이유 먼저 형식 파싱 확인. `uv run pytest` 전체 통과 · ruff clean.
- **배포 뒤 볼 것:** `pipeline rereport` 줄에 한국어 소개 글 제외가 늘어나는지, 월간 모음·다른 제품 글이 빠지지 않는지(1주).

## 7. 후속 (2026-11-14) — 같은 사이트의 다른 페이지를 링크한 재보도도 판정

> **상태: 구현·검증 완료 · 미병합 · 미배포** — §6 과 같은 브랜치 `worktree-rereport-reason-first`, 커밋 `9fbf572`

- **관찰(관리자 발송 17회, run_date 10-28~11-13):** 재보도가 원문 기사 주소 대신 그 사이트의 다른 페이지를 링크하면 쌍 찾기에 걸리지 않아 판정 없이 통과했다. 놓친 중복 7쌍. 예: The Decoder "Claude for Manufacturing"(11-13)은 전날 보낸 Claude Blog 글이 아니라 제품 페이지 `claude.com/solutions/manufacturing` 을 링크했다. 링크 대상은 제품 페이지 · 프로그램 페이지(`deepmind.google/fairwind-program`) · 기술 보고서 · 모델 모음(`huggingface.co/collections/…`)이다.
- **사용자 결정(2026-11-14):** 이런 글은 중복이다. 범위는 통과한 글(B)이 **News & Media·Community 매체 글일 때만** — 그때만 같은 사이트 쌍을 판정자에게 묻는다.
- **측정**(`same_site_measure.py`, 쌍마다 판정 2회): 같은 사이트 후보 627쌍 중 2회 모두 "같은 발표"는 10쌍(위 7쌍 + §6 에서 고친 한국어 소개 글 3쌍 — 이 3쌍은 원문 주소도 정확히 링크한다).

  | B 매체 분야 | 후보 쌍 | 같은 발표 |
  |---|---|---|
  | Community (PyTorch Korea) | 199 | 4 |
  | News & Media (The Decoder) | 172 | 6 |
  | 그 밖 — Anthropic 115 · Google 89 · AWS 33 · Independent Voices 12 · AI Labs 7 | 256 | 0 |

  10쌍의 A 와의 날짜 차는 0~5일이다(3일 이내 8쌍 · 4일 이내 9쌍) → 후보 기간은 7일.
- **고친 것**(`9fbf572`):
  - `rereport_dedup.drop_rereports` 에 (c) 단계를 더했다. B 가 News & Media·Community 매체 글이고(`SAME_SITE_B_CATEGORIES`), B 가 링크한 호스트가 최근 7일 안에 보냈거나 오늘 함께 보낼 기사(A)의 호스트와 같으면 판정한다.
  - 호스트는 정확히 같아야 한다 — `anthropic.com` 과 `claude.com` 은 다른 사이트로 본다.
  - 정확히 걸린 링크는 기존 (a)(b) 가 맡는다. B 가 정확히 인용한 기사는 (c) 후보에서 뺀다(서로 인용해 일부러 판정하지 않은 쌍을 다시 묶지 않게).
  - 같은 매체끼리는 묻지 않는다. 후보는 오늘 기사 먼저, 다음에 최근에 보낸 순서이고 첫 "같음"에서 멈춘다.
  - `article_identity`: `cite_host` · `SAME_SITE_WINDOW_DAYS = 7` · `published_keys(recent_hosts=)`. `pipeline`: 사용자별 `recent_hosts` 연결.
  - 판정자 · 프롬프트 · 파서(`retrieval/rereport.py`)는 그대로다.
- **매체 분야는 물을 범위만 정한다.** 빼는 결정은 쌍마다 판정자가 한다 — 2026-10-18 에 기각한 "2차 소스 일괄 제외"가 아니다. 그 밖 매체를 범위에 넣지 않은 이유: 256쌍 중 같은 발표가 0쌍이라 잡을 것이 없고, 원 발표 글이 형제 글의 재보도로 빠질 길만 생긴다.
- **관측(새 로그 줄):** `[WARN pipeline rereport] <user>: 재보도 제외(같은 사이트) — <B> ← <A> (<reason>)` · `<user>: 새 판정 N쌍 · 제외 M건`. 판정 메모를 사용자 간에 공유하므로 `새 판정` 줄은 그 쌍을 처음 만난 사용자에게만 찍힌다.
- **재생**(`rereport_replay.py`, 관리자 발송분, 2026-11-14):

  | 범위 | 판정한 쌍 | 제외 | 확인 |
  |---|---|---|---|
  | 10-28~11-13 (17회) | 323 (정확히 링크 18 · 같은 사이트 305) | 10 (정확히 링크 3 · 같은 사이트 7) | 측정의 10건과 일치 · 측정 후보 밖 판정 0 · 측정과 다른 판정 0 (`same_site_diff.py`) |
  | 10-21~10-27 (게이트 주간) | 222 (정확히 링크 12 · 같은 사이트 210) | 10 (정확히 링크 9 · 같은 사이트 1) | gitai · AAIF 묶음 유지 |

  - 같은 사이트로 새로 빠지는 7건: 10-28 The Decoder Nemotron 3.5 Transcribe ← Hugging Face · 10-28 The Decoder Gemini 4 Carbon ← DeepMind · 11-01 PyTorch Korea Gemini 4 Carbon ← DeepMind · 11-04 The Decoder provable inference ← Anthropic Research · 11-10 The Decoder Gemini 4 Carbon 정식 출시 ← DeepMind · 11-12 The Decoder Gemini 4 Hydrogen ← Google AI(Search 글) · 11-13 The Decoder Claude for Manufacturing ← Claude Blog.
  - 정확히 링크 3건은 §6 의 한국어 소개 글이다(Mistral Large 4 11-03 · MIC 11-05 · agent memory 11-09).
  - 게이트 주간의 같은 사이트 1건 = 10-25 The Decoder "one AI agent beats many subagents" ← Claude Blog. 이 기능의 발단이 된 기사이고, §6 에서 원문 링크가 사라져 놓치게 됐던 쌍이다.
- ★ **게이트 기대값이 다시 바뀌었다(§6 의 "9"를 대체한다):** 기본 실행은 **제외 10**, `--exact-only`(정확히 링크한 쌍만)는 제외 9 다. `run_gate.sh` 기본값과 `rereport_replay.py` docstring 예시도 10 이다. 2026-11-15 에 `run_gate.sh` 로 다시 돌려 둘 다 **PASS** — 기본 실행 판정 222 · 제외 10, `--exact-only` 판정 12 · 제외 9.
- **판정 호출 수:** run 당 약 2쌍 → 평균 약 23쌍 · 최대 50쌍(재생 24회 합계 545쌍). 호출은 순차이고 판정 메모를 공유하므로 대부분 run 의 첫 사용자 차례에 몰린다 — 호출 수뿐 아니라 그 사용자의 처리 시간도 는다.
- **정정(측정 집계):** 저장된 `same-site-measure.txt` 끝줄의 "2회 모두 다름 617"은 **다름 616 + 2회 모두 판정 실패 1** 이다. 집계가 판정 실패를 "다름"에 섞어 셌다(도구는 고쳤고, `same-site-analyze.txt` 가 실패를 따로 센다).
  - 실패한 쌍 = 10-29 The Decoder "Paris-based Mistral releases "Le Chonk,"…" ← Hugging Face "Welcome Le Chonk". 판정자는 "같은 발표"(`"same": true`)라고 답하지만, 이유 문장 안의 큰따옴표(`("Le Chonk")`)를 이스케이프하지 않아 응답 JSON 이 깨진다 → 판정 실패 → B 유지.
  - 이 쌍은 현재 답 순서로 12회 호출 중 11회 깨졌다. 저장된 것은 9회 전부 실패(측정 2 · 재생 1 · `judge-raw-probe-lechonk.txt` 6)이고, 저장하지 않은 첫 확인 3회 중 2회가 실패였다.
  - 다른 쌍에서는 나오지 않았다 — 저장된 같은 사이트 판정 1,799회 중 실패는 이 쌍의 3회뿐이고(`judge-fail-scan-20261115.txt`), §6 의 47쌍 실험 671회에는 0회다. 운영 로그(10-28~11-14)에 `판정 실패` 줄은 0건인데, 운영은 run 당 약 2쌍만 묻고 호출 수를 기록하지 않아 비율로 읽을 수는 없다.
  - 이 절의 변경이나 §6 의 답 순서 때문에 생긴 것이 아니다 — 옛 답 순서(값 먼저)로 물어도 같은 쌍이 6회 중 5회 깨진다(`judge-raw-probe-lechonk-same-first.txt`). **고치지 않았다(별도 문제 ⑥, 사용자 결정 대기).**
- **남은 문제(사용자 결정 대기):** ④ 원문이 발송된 적 없고 재보도 둘만 나감(Claude Fable 5.2 출시) · ⑤ 원 발표 글이 형제 글의 재보도로 빠짐(Gemini 4 Hydrogen, 11-12) — 이 절의 변경 뒤에는 그날 The Decoder 기사도 Search 글의 재보도로 빠져 Search 글만 남는다 · ⑥ 위 판정 응답 JSON 깨짐.
- **스펙·플랜은 고치지 않았다**(규칙 ②): 스펙의 "링크가 가리키는 쌍만"·"run 당 ~2건"은 2026-10-28 시점 기록이다. 현재 진실 = 이 절 + `rereport_dedup.py` 머리말 + `docs/README.md` 색인.
- **도구·데이터:** `docs/work_note/Nov-2026/261114-duplicate-articles-7days/` 의 `tools/same_site_*` · `same-site-*`(측정 627쌍 · 분석 · 재생 2회 · 대조).
- **테스트:** `tests/test_rereport_dedup.py` · `tests/test_article_identity.py` · `tests/test_pipeline.py` 에 같은 사이트 규칙 테스트(RED → GREEN). 가드 7개는 한 줄씩 지워 테스트가 잡는지 확인했다(`same_site_mutate.py`). `uv run pytest` 전체 통과 · ruff clean.
- **배포 뒤 볼 것(첫 run):**
  - [ ] `재보도 제외(같은 사이트)` 줄마다 B 가 정말 A 의 재보도인지. B 가 News & Media·Community 가 아닌 매체인 줄이 있으면 버그다.
  - [ ] `새 판정 N쌍` 이 50 을 크게 넘지 않는지.
  - [ ] run 소요 시간(첫 사용자) — 판정 호출이 순차로 약 20회 는다.
  - [ ] `판정 실패 — 통과(fail-open)` 줄 수 — 호출이 늘어난 만큼 드러날 수 있다(문제 ⑥).
