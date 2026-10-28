# 재보도 dedup — 이미 보낸 원문을 옮긴 기사 빼기 (설계)

- **상태:** DRAFT (2026-10-28) — 사용자 검토 완료(서로 인용 시 빅테크 우선 반영), 구현 전
- **발단:** 사용자가 10-25 카드 "Anthropic says one AI agent beats many subagents…"(The Decoder)를 보고 "같은 내용이 여러 매체로 여러 번 실렸다" → 10-22 에 원문(Claude Blog)이 이미 나갔음을 확인.
- **선행:** `2026-10-16-article-identity-dedup-design.md`(같은 기사 재발송 차단 — 해시·URL·제목 키). 이 문서는 그 위에 **다른 기사지만 같은 발표를 옮긴 글**을 막는 한 단계를 더한다.

## 요약

- **결정(사용자, 2026-10-28):** 공식 발표를 옮긴 재보도와, 이미 보낸 원문의 한국어 소개(번역·요약)는 **중복**이다. 원문을 참고만 한 **다른 주제**의 글(새 도구·여러 항목 묶음)은 남긴다.
- **방법:** ① 기사 본문 안의 **다른 사이트 링크**가 이미 보냈거나 오늘 함께 보낼 기사 URL 을 가리키면 후보 쌍으로 잡고(코드, 비용 0) ② 그 쌍만 Haiku 가 "B 는 주로 A 와 같은 발표에 대한 글인가"를 판정해 같으면 B 를 뺀다.
- **규모:** 지난 7 run 에서 전수 비교 125×1,590 ≈ 20만 쌍 → 링크 색인으로 **12쌍(run 당 ~1.7)** → 판정 결과 **10쌍 제외 · 2쌍 유지**(기대와 일치). Haiku 호출 하루 ~2회, 사용자 수와 무관.

---

## 1. 결정 경위 (재론 금지 목록 포함)

| 날짜 | 결정 |
|---|---|
| 2026-10-18 | 같은 사건의 **다른 시각**(공식·매체 분석·AWS 제공·후기)은 중복 아님. 기각(재제안 금지): 고유 이름 묶음+주제 상한 · Haiku 같은 사건 클러스터링 · 소스 순위로 한 장만 · 2차 소스 일괄 제외 |
| 2026-10-28 | **공식 발표를 옮긴 재보도는 중복** — 10-18 의 "다시 볼 조건(시각까지 같은 반복이 패턴)"에 해당(1주에 The Decoder 재보도 3건+) |
| 2026-10-28 | **이미 보낸 원문의 한국어 소개도 중복** — 카드가 이미 한국어라 번역은 새 정보가 아니다 |
| 2026-10-28 | gitai(Anthropic 설계를 참고한 새 도구)·AAIF 4개 프로젝트 합류(Skills 는 넷 중 하나)는 **유지** |

**이 설계가 10-18 기각 목록과 다른 점:** 같은 사건을 *추측해서 묶지 않는다*. B 가 A 를 **본문에서 직접 링크**한 경우에만, 그 한 쌍을 판정한다.

## 2. 실측 (2026-10-28, 사용자 1명 기준 지난 7 run = 10-21~10-27)

### 2.1 링크 색인이 비교 쌍을 줄이는 정도

| 방식 | 비교 쌍 |
|---|---|
| 모든 후보 × 90일 안에 보낸 기사 | 125 × 1,590 ≈ 198,750 |
| 본문 안·다른 사이트 링크가 보낸 기사를 가리킴 | **12** |

- **함정 1(실측):** 페이지 전체의 `href` 를 쓰면 사이드바·메뉴 링크(The Decoder 는 모든 글이 같은 자사 글 3개를 링크) 때문에 거짓 후보가 쏟아진다 → **본문 안 링크 + 다른 사이트**만 쓴다.
- **함정 2(실측):** The Decoder 는 원문을 `claude.com/de/resources/…`(독일어판 경로)로 링크했다 → **언어 경로 정규화** 필요(§4.1).
- **같은 날:** 12쌍 중 3쌍(Google Cloud·OpenAI 모델, 미공개 모델 정렬 평가, Genie 4)은 원문과 재보도가 **같은 run** 에 들어왔다 → 과거뿐 아니라 오늘 후보끼리도 본다.
- **역순(재보도가 먼저, 원문이 나중):** 2주(252건) 실측 **0건** → 범위 밖(§8).

### 2.2 판정 기준 비교 (Haiku 5.5, 같은 12쌍)

| 기준 | 제외 | 결과 |
|---|---|---|
| "B 가 A 에 없는 정보를 더했나" | **0 / 12** | 실패 — 재보도는 늘 세부(인용·수치·반응)를 조금 더한다. **재제안 금지** |
| "B 는 주로 A 와 같은 발표에 대한 글인가(번역·요약·세부 추가 포함)" | **10 / 12** | 채택 — 기대와 일치 |

| 판정 | 쌍(B ← A) |
|---|---|
| 제외 10 | The Decoder: subagent 통합 ← Claude Blog · Claude Duet ← Claude Blog · 전갈 독소 ← Anthropic Research · Genie 4 ← DeepMind · 미공개 모델 정렬 평가 ← Anthropic Research · Google Cloud OpenAI 모델 ← Google Cloud Blog / PyTorch Korea: MPS FP8 ← HF · TorchNeuron ← HF · Agent Skills AAIF 기증 ← Anthropic · ThinkingBox ← HF |
| 유지 2 | PyTorch Korea: gitai ← Anthropic source control(새 도구) · AAIF 4개 프로젝트 합류 ← Anthropic Skills 기증(넷 중 하나) |

## 3. 흐름

```
┏━━━━━━━━━━━━━━━━━━ run 1회 · 전 사용자 공유 ━━━━━━━━━━━━━━━━━━┓
┃ curate()  ← 모든 사용자 소스의 합집합                            ┃
┃   fetch (RSS 전문 / html 리스팅 → 기사 HTML)                     ┃
┃   → canonical·window·AI 관련성·캡/선별 (기존)                     ┃
┃   → ★ 인용 URL 추출: 본문 안 · 다른 사이트 링크 → 인용 키          ┃
┃   → freeze ──► source-store                                      ┃
┃   cited[source_id] = {인용 키…}   ← run 동안만(저장 안 함)         ┃
┃ 공유 메모: meta_memo(기존) · ★ judge_memo[(A,B)] → same/different  ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━ 사용자마다 ━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ ① 후보 = 구독 소스의 기사                                         ┃
┃ ② [기존] 같은 기사 차단: ledger 90일 + source-store join → seen    ┃
┃ ③ ★ 재보도 차단                                                   ┃
┃    B 의 인용 키가 (a) seen 의 URL(지난 90일 받은 기사) 또는          ┃
┃                  (b) 오늘 이 사용자 후보 A 의 URL 에 걸리나?        ┃
┃       아니오 → 통과                                (거의 전부)     ┃
┃       예 → judge_memo[(A,B)] 재사용, 없으면 Haiku 1회 (하루 ~2쌍)   ┃
┃            A 본문 = source-store(과거) 또는 오늘 동결본(같은 날)     ┃
┃            same=true → B 제외(A 유지) + warn                       ┃
┃            same=false → 통과 · 오류 → 통과 + warn (fail-open)       ┃
┃ ④ 카드(첫 사용자가 만들고 재사용) → ledger → render → SES            ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛
```

**사용자별로 판정하는 이유:** "이미 받았나"는 사람마다 다르다(가입 시점 — 10-15 추가된 cw-hasunyu, 소스 선택 — Claude Blog 없이 The Decoder 만 구독). 사용자별로 남는 일은 메모리 집합 조회뿐이고, source-store 조회·Haiku 판정은 run 메모로 사용자 간 공유된다.

### 예시 (실데이터 — 10-25 run, 사용자 1명)

```
B = The Decoder "Anthropic says one AI agent beats many subagents…" (52624f70…, 4,717자)
  본문 링크 10개 → 다른 사이트 6개 → 인용 키
    claude.com/resources/articles/building-agents-when-to-fold-subagents-…  ← /de/ 제거
    claude.com/resources/articles/seeing-like-an-agent · …the-anatomy-of-effective-commerce-agents
    claude.dev/blog/… · github.com/anthropics/single-agent-loop-kit · platform.claude.com/docs/…
② 기존 dedup: 해시·URL·제목 모두 다름 → 통과
③ 인용 키 6개를 보낸 URL 집합(~1,600)에서 조회 → building-agents-… 만 걸림(10-22 발송) = A
   judge_memo 없음 → get_source(A=169d22a6…, 7,998자) → Haiku:
   {"same": true, "reason": "subagent 통합 권고와 migration kit — A 와 같은 발표, 인용·비교·반응만 더함"}
   → B 제외, warn, judge_memo 저장 → 나머지 6명은 Haiku 없이 같은 결과
```

## 4. 구성 요소

### 4.1 인용 키 추출 — `core/retrieval/sources.py`

- **어디서:** 기사 HTML 이 있는 두 경로 — html 리스팅의 기사 페이지(`fetch_generic_html` → `_extract_article`), RSS 전문 추적(`_fetch_feed` 의 `full_text` 페이지). 피드 요약 폴백(페이지 없음)·Gateway 경로·헤드라인 전용 소스는 인용 키 없음(검사 안 함).
- **본문 안 링크만:** trafilatura 본문 추출 결과의 링크(사이드바·메뉴·관련 글 목록 제외).
- **다른 사이트만:** 기사 자신의 호스트와 같은 호스트(`www.` 무시)는 버린다.
- **정규화 = 인용 키:** 기존 `url_key`(scheme·`www.`·fragment·끝 슬래시 제거, 쿼리 유지) + **언어 경로 제거**: 첫 경로 조각이 언어 코드(`de`·`ko`·`ja`·`fr`·`es`·`zh-cn` 같은 ISO 639-1 / 639-1-국가 형태)면 제거. **비교 양쪽(인용 키·보낸 URL·오늘 후보 URL)에 같은 함수**를 쓴다 — AWS KR(`aws.amazon.com/ko/blogs/tech/…`)처럼 저장 URL 에도 언어 경로가 있기 때문.
- **전달:** `FetchedArticle` 에 인용 키 필드(기본 빈 값 → 기존 생성자·Gateway JSON 무변경) → `curate` 의 선택 인자 `cited_out: dict | None = None`(기본 None — 반환 타입·기존 호출 무변경)에 `source_id → 인용 키` 를 채워 파이프라인에 넘긴다. **source-store 에 저장하지 않는다**(§8 역순 참고).

### 4.2 후보 쌍 찾기 — `core/pipeline.py` (기존 dedup 직후)

- **(a) 과거:** B 의 인용 키 ∩ "이 사용자에게 지난 90일 보낸 기사의 인용 키화 URL". 기존 `published_keys` 가 만드는 메타(url)를 쓰고, **URL → source_id** 역참조를 함께 얻는다(A 본문을 읽으려면 필요).
- **(b) 같은 날:** B 의 인용 키 ∩ "오늘 이 사용자의 다른 후보(②를 통과한 것) URL".
  - A 가 ③에서 이미 빠진 기사면 (b) 의 A 로 쓰지 않는다 — 결과적으로 둘 다 빠지는 일을 막는다.
  - **서로 인용**(A↔B 둘 다 서로를 링크)이면 남길 쪽(A)을 이렇게 정한다(사용자 결정 2026-10-28):
    1. **빅테크 1차 글을 남긴다** — 한쪽만 빅테크 소스면 그쪽이 A. 빅테크 판별 = 기존 `top_picks.big_org` 를 소스의 `카탈로그 category + 매체 이름`에 적용(5대 기업 Anthropic·OpenAI·Amazon·Google·Meta — 새 목록 없음. 현재 카탈로그: AWS 3·Anthropic 5·Google 5·Meta Research 1 = 빅테크, The Decoder·PyTorch Korea·HF·Simon Willison 등 = 아님).
    2. 둘 다 빅테크이거나 둘 다 아니면 **발행 시각이 이른 쪽**이 A.
    3. 시각이 없거나 같으면 판정하지 않고 둘 다 통과(fail-open).
- B 의 인용 키가 여러 A 에 걸리면, 걸린 A 마다 판정하되 하나라도 same 이면 B 제외.
- 기존 의미론 유지: (a) 는 PUBLISH 만·strictly-earlier(같은 날 재실행은 재발송)·`run_date` 빈값이면 off — `published_keys` 그대로.

### 4.3 Haiku 판정 — `core/retrieval/relevance_bedrock.py` 패턴 + 새 판정 모듈

- **DI seam:** `rereport_fn(a_text, b_text) -> bool | None`(True=같은 발표, False=다른 주제, None=판정 실패). `run_briefing` 인자로 받고, **None(미주입)이면 ③ 전체 off** — 기존 테스트·로컬 무변경.
- **프로덕션 주입:** `runtime/agentcore_runtime.py::_production_fns` 의 `relevance_llm_enabled` 묶음에 추가 → scheduled·trial 이 같은 판정자를 쓴다(2026-07-27 trial 우회 결함 재발 방지).
- **모델:** `RELEVANCE_MODEL_ID`(현재 Haiku 5.5) 재사용 — 새 env 없음. Converse, `thinking: disabled`, `temperature` 미지정(Haiku 5.5 는 거부 — 실측), 텍스트 블록 탐색(기존 `_converse_text` 재사용).
- **입력:** A 본문·B 본문 각 최대 8,000자(source-store 동결본 상한과 같음).
- **프롬프트 핵심(실험 판):** "Article A was already sent. B links to A. Is B mainly a report about the SAME announcement or content as A? SAME = covers A's announcement as its main news, even if it translates (e.g. Korean write-up), summarizes, adds details, quotes, reactions or comparisons. DIFFERENT = B's main subject is a different product, project, release or event, and A is only background, inspiration, or one item among several equal items." 응답 JSON `{"same": bool, "reason": "<한 문장>"}`.
- **실패 처리:** 호출 오류·JSON 없음·키 없음 → None → B 통과 + warn. 브리핑을 막지 않는다.
- **메모:** `judge_memo[(A_sid, B_sid)]` — run 동안 사용자 간 공유. 실패(None)도 메모해 같은 run 에서 재호출하지 않는다. 영구 캐시는 두지 않는다(한 쌍은 48h 창 때문에 많아야 2 run 에 나타남).

### 4.4 관측

- 제외 시 `_debug.warn("pipeline rereport", "<user>: 재보도 제외 — <B 제목> ← <A 제목> (<reason>)")` — DEBUG 무관·CloudWatch 도달.
- 판정 실패 시 `_debug.warn("pipeline rereport", "<user>: 판정 실패 — 통과(fail-open): <B 제목>")`.
- 사용자 브리핑의 기존 `deduped` 집계에 포함한다(별도 숫자 없음 — 종류는 warn 라벨로 구분).

## 5. 오탐 방지 원칙

- **링크가 없으면 판정하지 않는다** — 같은 사건 추측 묶기를 하지 않는 것이 10-18 기각 목록과의 경계.
- **판정 실패·애매함은 남긴다**(fail-open) — 기사를 잃는 것이 중복 1장보다 나쁘다.
- **A 는 언제나 유지** — 빠지는 것은 인용한 쪽(B)뿐.

## 6. 비용

| 항목 | 양 |
|---|---|
| 인용 키 추출 | 이미 받은 HTML 을 한 번 더 파싱(추가 요청 없음) — 기사당 수십 ms |
| 후보 쌍 찾기 | 사용자당 집합 조회, 1ms 미만 |
| A 본문 읽기 | 걸린 쌍만 — 하루 ~2건 `get_source` |
| Haiku 판정 | 하루 ~2회(쌍당 1회, 사용자 공유) · 입력 ~5K 토큰 → 1센트 미만 |

## 7. 검증·합격 기준

- **재생 게이트(머지 조건):** 지난 7 run(10-21~10-27) 의 실제 발송 기사로 ③을 재생(기사 HTML 재수집 → 인용 키 → 실제 판정자):
  - 제외 = §2.2 의 **10쌍**, 유지 = gitai·AAIF 묶음 **2쌍**, 그 밖의 제외 **0**.
  - 재생 도구 = `scripts/dedup_audit/` 에 추가(프로덕션 읽기 전용).
- **단위 테스트:** 본문 안 링크만·다른 사이트만 · 언어 경로 정규화(`/de/`·`/ko/` 양쪽) · (a) 과거 쌍 · (b) 같은 날 쌍 · 서로 인용 · A 가 이미 빠진 경우 · 여러 A 에 걸림 · 판정 메모 공유(두 번째 사용자 호출 0) · 판정 실패 fail-open · `rereport_fn` 미주입 시 off · 기존 dedup 이 먼저 돈다.
- **사후 관측:** 배포 후 1주 CloudWatch `pipeline rereport` 라인 검토 — 잘못 빠진 글(다른 주제)이 보이면 프롬프트 조정.

## 8. 범위 밖 (알려진 한계)

- **역순**(재보도가 먼저 나가고 원문이 나중에 들어옴) — 2주 실측 0건. 필요해지면 동결 시 인용 키를 source-store 에 함께 저장(스키마 무변경)해 "과거 발송 기사가 오늘 후보를 인용했나"를 본다.
- **원문을 링크하지 않은 재보도** — 확인한 사례는 모두 링크가 있었다. 임베딩 유사도 등은 같은 사건 묶기에 가까워 하지 않는다.
- **헤드라인 칸**(제목·링크 전용 소스) — 본문이 없어 대상 아님. 헤드라인↔카드 중복은 기존 `headlines.py` 가 담당.
- **Gateway 경로** — 기본 off, 인용 키 없음(검사 안 함).

## 9. 변경 범위·배포

| 파일 | 변경 |
|---|---|
| `src/briefing/core/retrieval/sources.py` | 본문 링크 추출 → 인용 키, `FetchedArticle` 필드 |
| `src/briefing/core/retrieval/curation.py` | 인용 키 맵을 파이프라인으로 전달 |
| `src/briefing/core/article_identity.py` | 언어 경로 정규화 키 함수 · 보낸 URL → source_id 역참조 |
| 신규 판정 모듈 + `src/briefing/core/retrieval/relevance_bedrock.py` | Haiku 판정 함수·Bedrock 조립 |
| `src/briefing/core/pipeline.py` | ③ 재보도 차단 단계 · `rereport_fn` 인자 · judge_memo |
| `src/briefing/runtime/agentcore_runtime.py` | `_production_fns` 에 `rereport_fn` 추가 |
| `scripts/dedup_audit/` | 재생 게이트 |
| `tests/` | §7 단위 테스트 |

- **배포:** `deploy_runtime` 만. 새 env·IAM·테이블 변경 없음(Converse 는 기존 `bedrock:InvokeModel` 로 커버, 모델은 `RELEVANCE_MODEL_ID` 재사용). `deploy_scheduler` 는 돌리지 않는다(dry-run 리셋 함정).
