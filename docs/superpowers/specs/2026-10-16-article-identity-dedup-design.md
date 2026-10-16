# 기사 신원 dedup — 같은 기사를 같은 사용자에게 두 번 보내지 않기 (설계)

- **상태:** DRAFT (2026-10-16) — 결정 확정: source-store join + lookback 90일(§6), 구현 전
- **발단:** 2026-10-10 사용자 요청 "최근 4주간 중복 발행 기사가 있는지 확인" → 프로덕션 DDB 감사로 중복 실재 확인
- **선행 설계:** `2026-07-11-late-post-window-dedup-design.md` (ledger cross-day dedup 도입 — 이 문서는 그 dedup 의 구멍을 메운다)

## 요약

- **문제:** 같은 기사가 같은 사용자에게 반복 발송된다. 첫 발송(07-08)부터 2026-10-15 까지 **8개 기사, 초과 배달 45장**.
- **원인 3층:** ① 수집층이 블로그 리스팅의 *문서 페이지*를 새 글로 오인 ② 기사 신원 = 본문 해시라 원문이 조금만 고쳐져도 새 기사 ③ dedup 기억이 7일뿐.
- **해결:** 층마다 한 겹씩 — ① canonical 호스트 검사 ② URL·제목 신원 키(과거 기사 메타는 source-store join) ③ lookback 90일 + pagination. 측정된 45장을 전부 막고, 오탐 0건(실데이터 검증).

---

## 1. 감사 결과 (실증)

측정 = `briefing-ledger` PUBLISH 행 × `briefing-sent-log` status=sent(실제 발송된 브리핑만) × `briefing-source-store`(URL·제목 join).

| 기사 | 소스 | 재발행 날짜(예) | 초과 장수 | 막는 층 |
|---|---|---|---|---|
| Best practices for Claude Code | anthropic-eng | 07-18 이후 **14회**(본인) · 09-25·09-26·10-02·10-06(동료) | **28** | ① |
| ML Drift: Next-Gen GPU AI/ML Inference at the Edge | google-dev | 10-08 → 10-09 | 6 | ② URL |
| Preparing for the 2026 US midterms | anthropic | 10-14 → 10-15 | 6 | ② URL |
| cognizant-anthropic | anthropic | 07-27 → 07-28 | 1 | ② URL |
| self-service-data-analytics-in-slack | claude-blog | 08-13 → 08-14 | 1 | ② URL |
| how-an-anthropic-field-marketer-uses-claude-code | claude-blog | 08-24 → 08-25 | 1 | ② URL |
| scaling-cloud-migrations-with-agentic-ai | aws-ml | 08-20 → **10-02 (43일 뒤)** | 1 | ③ lookback |
| Strands+AgentCore 발전설비진단 | aws-kr-tech | 09-22 → 09-23 (slug 오타 수정 `arae`→`narae`) | 1 | ② 제목 |
| **합계** | | | **45** | |

**중복이 아니었던 것(감사 함정):**
- URL 정규화에서 쿼리를 지우면 AI Times(`articleView.html?idxno=…`, `idxno`=기사 ID) 전 기사가 한 URL 로 뭉쳐 가짜 중복이 나온다 — 실제는 138기사 = 138 URL.
- 퍼지 제목 유사도는 템플릿 제목(`Introducing Claude Sonnet 5.5 on AWS` vs `Haiku 5.5`, GPT-6 Sol vs GPT-6.1 Sol)을 오탐 — 별개 기사.

## 2. 근본 원인

### ① 수집층 — 문서 페이지를 새 글로 오인 (Best practices 28장)

```
anthropic.com/engineering (리스팅, 링크 25개)
  └ /engineering/claude-code-best-practices        ← 25개 중 유일하게 블로그 밖으로 나감
       308 ──► code.claude.com/docs/en/best-practices   (자주 수정되는 Claude Code 문서)
                 JSON-LD: dateModified 만 있음, datePublished 없음
                 trafilatura date = 최종 수정일 (예 2026-10-06)
  → _is_stale(date, 48h) = False  → 문서가 수정될 때마다 "그날 발행된 새 글"
```

- 리스팅은 최신순인데 이 링크는 2025-06 글과 2025-03 글 사이에 있다 = 원래 2025년 봄 블로그 글이 문서로 이전됨. 날짜만 수정일이라 25개 중 유일하게 48h 창 안.
- 지난 4주 `anthropic-eng` 카드는 이 글 4장뿐(리스팅상 진짜 최신 글은 2026-05-25).

### ② 신원층 — 기사 신원 = 본문 해시

- `source_id = sha256(정규화 본문, 앞 ~8000자)`. 원문이 고쳐지면(문단 수정, 오타 수정) 새 해시 → dedup 은 새 기사로 본다.
- 48h 창(html 소스)은 같은 글을 이틀 연속 후보로 만든다 — 그 사이 원문이 수정되면 dedup 통과(ML Drift·midterms·claude-blog 2건·cognizant).
- 8000자 상한 뒤쪽이 수정되면 해시는 같다(09-25 Best practices = 08-21 과 같은 해시) — 이때는 ③이 구멍.

### ③ 기억층 — lookback 7일

- `since = run_date - 7d`. 같은 기사가 8~14일 간격(Best practices) 또는 43일 뒤(aws-ml, RSS 재등장)로 돌아오면 통과.
- 7일은 "겹침은 최대 48h" 가정에서 정한 값 — 고쳐진 옛 글이 다시 "새 글"로 들어오는 경우는 그 가정 밖.

## 3. 배경 — DB 스키마 (DynamoDB us-east-1, 행 수는 2026-10-16 기준)

```
┌─ briefing-users (7) ────────────────────────────────────────────┐
│ PK user_id                                                      │
│ recipient · sources[] · lens · depth · send_hour(5) · timezone  │
└─────────────────────────────────────────────────────────────────┘
┌─ briefing-source-store (1,576) ──  TTL 없음(영구, 정본) ─────────┐
│ PK source_id = sha256(정규화된 본문)        ← 본문이 바뀌면 다른 키 │
│ url · title · media("AI Times") · text(앞 ~8000자)              │
│ fetched_at  ※ 이름과 달리 실제로는 "기사 발행일"(curation.py)      │
│ 쓰기 = 조건부 put(first-wins, 덮어쓰지 않음)                      │
└─────────────────────────────────────────────────────────────────┘
┌─ briefing-card-cache (997) ──  TTL ttl(30일) ───────────────────┐
│ PK cache_key                                                    │
│   사실층 = sha256("fact|source_id|모델|프롬프트버전")               │
│   해석층 = sha256(source_id|lens|fact_key|해석버전)                │
│ card_json (검증 완료 카드)                                        │
└─────────────────────────────────────────────────────────────────┘
┌─ briefing-ledger (4,297) ──  TTL 없음(07월부터 전부 남음) ─────────┐
│ PK user_id   SK "run_date#source_id"   (예 "2026-10-08#7a8e72…") │
│ run_date · source_id · card_key · decision(PUBLISH|QUARANTINE)  │
│ headline        ※ URL·제목은 저장하지 않음 (ledger.py 원칙)        │
└─────────────────────────────────────────────────────────────────┘
┌─ briefing-sent-log (235) ──  TTL 없음 ──────────────────────────┐
│ PK user_id   SK run_date                                        │
│ status · sent_at · recipient · message_id · published ·         │
│ quarantined · duration_ms · cost_usd                            │
└─────────────────────────────────────────────────────────────────┘

연결(포인터):
  ledger.source_id ───────► source-store.source_id   (url · title · 원문)
  ledger.card_key  ───────► card-cache.cache_key      (보낸 카드)
  sent-log(user, run_date) ◄─► ledger(user, sk 앞부분 run_date)
```

## 4. 배경 — 매일 아침 실행 흐름 (현재)

```
EventBridge(매시) → Lambda(fire-and-return) → AgentCore runtime(add_async_task)
 └ dispatch()
    ├ users_due_now ◄── briefing-users        (send_hour=5 KST 인 사용자)
    ├ run_briefing(due 사용자, run_date)
    │  ├ curate()  ── 모든 사용자 소스의 합집합, run당 1회
    │  │   fetch: RSS / html(리스팅 → 링크 → trafilatura 본문·날짜)
    │  │   → window 필터 (RSS 24h, html 48h; html 은 페이지 날짜 기준)
    │  │   → require_ai 필터(Haiku) → 캡/선별(pick-K)
    │  │   → freeze ──► briefing-source-store  (source_id = 본문 해시)
    │  └ 사용자마다
    │     ├ dedup ◄── ledger.query(user, 최근 7일)
    │     │     PUBLISH 이고 run_date < 오늘 인 source_id 집합
    │     │     → 오늘 후보의 source_id 가 집합에 있으면 제외   ← 구멍
    │     ├ 기사마다 _process:
    │     │   사실층: card-cache 히트? 아니면 claude -p 작성 → codex 검증 → gate ──► card-cache
    │     │   해석층: card-cache 히트? 아니면 lens 해석 → 가드        ──► card-cache
    │     │   ledger.append(run_date, user, source_id, card_key, decision, headline) ──► ledger
    │     └ 이메일 render
    └ 사용자마다 발송: should_deliver? → sent-log.already_sent? → SES → ──► sent-log
```

## 5. 설계 — 3층 방어 (★ = 새로 추가)

### ① 수집층: canonical 호스트 검사 (`retrieval/sources.py`, html 리스팅 경로)

- 이미 호출 중인 `trafilatura.bare_extraction` 이 canonical URL(`doc.url`)을 돌려준다 → **추가 요청 없음**.
- 규칙: canonical 호스트가 리스팅 호스트와 다르면 버린다. **fail-open:**
  - canonical 이 없으면 통과.
  - 한쪽이 다른 쪽의 dot-suffix 면 통과(서브도메인: `blog.x.com` ↔ `x.com`).
  - 호스트 비교는 소문자·`www.` 제거 후.
- 버릴 때마다 `_debug.warn`(DEBUG 무관, CloudWatch 도달) — 무엇을 왜 버렸는지.
- 실측(2026-10-10, html 소스 4곳 링크 77개): cross-host = **best-practices 1건뿐**(최종 URL·canonical 모두 `code.claude.com`). 정상 글 오탐 0.

### ② 신원층: 기사 신원 키 3종 (`pipeline.py` dedup + 신규 키 함수 모듈)

| 키 | 정의 | 잡는 사례 |
|---|---|---|
| `source_id` | 기존 본문 해시 | 같은 바이트 재등장 |
| URL 키 | scheme·`www.`·`#fragment`·끝 슬래시 제거, 호스트 소문자. **쿼리는 유지**(AI Times `idxno`) | 원문 수정(ML Drift·midterms 등) |
| (매체, 제목 키) | 제목 소문자·기호/공백 제거, **매체와 묶음**, 최소 길이 미만이면 키 없음(일반 제목 보호) | slug 변경(AWS KR) |

- 셋 중 **하나라도** 이전 PUBLISH 와 일치하면 제외 + `_debug.warn`(어느 키로 걸렸는지 — 오탐 관측용).

### ③ 기억층: lookback 90일 + pagination

- `DEDUP_LOOKBACK_DAYS=90` — `.env` 에서 관리(코드 기본값도 90). 7일 → 90일.
- **왜 90일:** 관측된 최장 재등장 간격 43일(aws-ml)의 약 2배 여유. 전체 이력은 시간이 선형으로 늘지만(1년 뒤 ~3초), 90일 창은 비용이 **고정**(~0.7초)된다.
- **대가:** 90일이 지난 뒤 같은 기사가 다시 "새 글"로 들어오면 한 번 더 나간다 — 관측 사례 없음, 유일한 반복 유형(문서 페이지)은 ①이 수집 단계에서 끊는다.
- **필수:** `DynamoLedger.query` 에 `LastEvaluatedKey` 루프. 현재는 첫 페이지(1MB)만 읽어 넘으면 **조용히 잘린다**(본인 계정 90일치 ≈ 1,500행·0.5MB — 카드 수가 늘면 1MB 초과 가능).

### join 실측 (2026-10-16, 사용자 7명)

| 기간 | ledger 조회 | 과거 기사(사용자 합집합) | BatchGet 호출 | join 시간 |
|---|---|---|---|---|
| 90일 (07-18~) | 7페이지·0.2초 | 1,530 | 16회 | 0.6초 |
| 전체 이력 (07-08~) | 7페이지·0.2초 | 1,700 | 17회 | 0.5초 |
| 1년 뒤 추정 · 전체 이력 | — | ~7,000 | ~70회 | ~3초 |
| 1년 뒤 추정 · 90일 | — | ~1,800 | ~18회 | ~0.7초(고정) |

### 메타가 없는 과거 기사 — fail-open

- 07-24 이전 ledger 행의 72%(293/406)는 source-store 원본이 없다 — `305ed18`(2026-08-01) 이전 source-store 에 **7일 TTL** 이 있어 만료됨. 07-25 이후는 100% 해석된다.
- 메타가 없는 id 는 **해시 키로만** 비교(URL·제목 키 없음) — 막을 근거가 없으면 막지 않는다. run 끝에 "meta 미해결 N건" warn 1줄로 관측.
- 90일 창은 곧 이 구간(07-24 이전)을 벗어나므로 미해결은 자연히 0 으로 수렴한다.

### 제안 dedup 흐름 (§4 의 dedup 블록만 교체)

```
사용자마다:
  ledger.query(user, ★since=오늘-90일, ★pagination 끝까지)
     │  PUBLISH 이고 run_date < 오늘
     ▼
  과거 source_id 목록 ──► ★source-store.get_meta(ids)
     │                      BatchGetItem 100개씩, url·title·media 만
     │                      ★run 메모: 사용자들이 결과 공유(사실상 run당 1회)
     │                      원본 없음 → 해시 키로만(fail-open)
     ▼
  seen = { source_id }
       ∪ { URL 키 }            예 "developers.googleblog.com/ml-drift-…"
       ∪ { (매체, 제목 키) }      예 ("AWS Korea Tech Blog", "strandsagents와…")

오늘 후보 기사(FrozenSource 에 url·title·media 이미 있음)
  → 같은 키 3개 계산 → 하나라도 seen 에 있으면 제외 + ★warn 로그(어느 키로 걸렸는지)
```

예시(ML Drift, 10-09): 후보 해시 `974be6` 는 처음 보는 해시라 현행은 통과. 10-08 PUBLISH 행의 `7a8e72` → source-store → URL `developers.googleblog.com/ml-drift-…` → 오늘 후보와 URL 키 같음 → **제외**.

## 6. 결정 — 과거 기사의 URL·제목을 어디서 가져오나 → **① source-store join (2026-10-16 확정)**

| | ① source-store join (추천) | ② ledger 비정규화 + 백필 |
|---|---|---|
| 방식 | dedup 때 과거 `source_id` 로 source-store 를 batch 조회 | ledger 행에 url·title 저장, 기존 행은 백필 스크립트 |
| 스키마·인터페이스 | 무변경(SourceStore 에 `get_meta` 추가만) | `append` 시그니처 변경(Local·Dynamo·Null·테스트 fake) |
| 프로덕션 작업 | 없음 | 프로덕션 DDB 일회성 쓰기 |
| 적용 시점 | 배포 첫날부터 전체 이력 | 백필 완료 후 |
| 설계 원칙 | `ledger.py` "URL 은 source-store join, 중복 저장 금지" 준수 | 원칙 위반 → docstring 수정 필요 |
| 비용 | run당 batch ~15회(1~2초), 1년 뒤 ~80회(~10초) | ledger 조회만 |

- **추천 ①:** 바꾸는 곳이 가장 적고 되돌리기 쉽다. 9~13분 런에서 몇 초는 무시 가능. 사용자·이력이 크게 늘어 join 이 문제될 때 ②로 옮겨도 늦지 않다.
- source-store 는 first-wins(불변)라 ②로 복사해도 값이 어긋나지는 않는다 — ②의 단점은 정합성이 아니라 변경 범위.

## 7. 유지하는 것 (재론 금지 — 선행 설계의 의미론 3결정)

1. **PUBLISH 만** dedup — QUARANTINE 은 사용자가 받지 않았으므로 재도전.
2. **strictly-earlier** (`run_date < 오늘`) — 같은 날 재실행 = 강제 재발송 런북 보존.
3. **`run_date` 빈값이면 off** — 순서 비교 불가한 ad-hoc 경로는 현행.

## 8. 범위 밖

- **C. "처음 본 날" 기준 신선도**(html 새 글 판단을 페이지 날짜 대신 최초 목격일로) — ①~③이 측정된 45장을 전부 덮으므로 보류.
- `fetched_at` 이름 정정(실제 = 발행일) — 별건.
- dedup 이 캡/선별 *뒤*에 있어 중복 기사가 캡 자리를 차지하는 2차 효과 — 관측 안 됨, 보류.
- **별건(무음 정지):** `claude.com/blog` 가 `claude.com/resources/articles` 로 redirect 되는데 `_article_links` 는 `/blog/{slug}` 만 찾음 → `claude-blog` 소스 10-05 이후 카드 0장. 이 설계와 별도로 다룬다.

## 9. 오탐 근거 (2026-10-10 실측)

- **URL 키:** source-store 1,458건 중 같은 URL 에 해시 여러 개 = 9개 URL, **전부 제목 1종**(같은 기사의 수정본) → 서로 다른 기사가 URL 을 공유한 사례 0.
- **제목 키(매체 내):** 서로 다른 URL 이 같은 (매체, 제목)을 가진 사례 = 1건, 그것이 AWS KR slug 수정(진짜 중복) → 오탐 0.
- **canonical 검사:** html 4소스 링크 77개 중 cross-host 1건(best-practices) → 오탐 0.

## 10. 검증·합격 기준

- **재생 테스트(머지 게이트):** 프로덕션 덤프(ledger·source-store·sent-log)를 *새 dedup 코드*에 그대로 통과시켜:
  - 층별로 막힘: ① 28 · ② URL 15 · ③ 1 · ② 제목 1 = **45**
  - AI Times 서로 다른 URL 138개 중 막힘 **0**
  - 같은 날 재실행은 재발송(의미론 2)
- **단위 테스트:** URL 키(쿼리 유지·`www`·끝 슬래시·fragment), 제목 키 최소 길이, canonical fail-open(없음·서브도메인), ledger 여러 페이지 조회, Local/Dynamo 파리티, `get_meta` 누락 id → 해시로만 비교, lookback 경계(정확히 90일 전 포함·91일 전 제외), run 메모(두 번째 사용자는 재조회 없음).
- **사후 관측:** 배포 후 2주간 감사 스크립트(이번 감사 로직)로 초과 배달 0 확인 + CloudWatch dedup warn 라인 검토.

## 11. 변경 범위·배포

| 파일 | 변경 |
|---|---|
| `core/retrieval/sources.py` | ① canonical 호스트 검사(html 경로) |
| `core/pipeline.py` | ② 키 3종 dedup + ③ 전체 이력 조회 |
| 신규 키 함수 모듈(`core/` 하위) | URL 키·제목 키 정규화 |
| `core/stores/source_store.py` · `core/stores/dynamo.py` | `get_meta(ids)`(Local·Dynamo) + `DynamoLedger.query` pagination |
| `core/config.py` · `.env` | `dedup_lookback_days`(`DEDUP_LOOKBACK_DAYS`, 기본 90) — `.env` 활성 라인도 함께 |
| `tests/` | §10 단위·재생 테스트 |

- **배포:** `deploy_runtime` 만(테이블 스키마·CFN 무변경, webapi 무관). 대기 중인 main `22a358c`(미상 출처 키 warn)도 함께 실린다.
