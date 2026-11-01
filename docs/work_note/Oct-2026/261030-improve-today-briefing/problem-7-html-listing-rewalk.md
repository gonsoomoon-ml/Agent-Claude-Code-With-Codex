# #7 — 날짜 없는 목록(html 리스팅) 소스의 매일 재열람: 같은 옛 글을 다시 열고 페이지 날짜로 버림 (문제 정의, 2026-10-31)

> 상태: **정의 기록 · dive-in(원인 상세·선택지) 미착수 — 사용자 검토 대기.** 저장소 코드 무변경.
> 측정 도구(읽기 전용): `tools/html_listing_waste.py`(운영과 같은 규칙으로 목록 재현, 페이지별 폐기 사유 기록 — 출력 보존
> `html-listing-replay-20261031.txt`) · `tools/undated_published.py`(ledger 의 html 소스 카드 목록) · `tools/hub_cards.py`(허브 카드 원자료) · `tools/hub_recipients.py`(허브 카드가 7명 ledger 에 다 있는지) ·
> `tools/anthropic_eng_history.py`(소스별 일별 카드 수).
> §6 에 이 조사에서 드러난 **새 항목 2건**(허브 페이지 카드 발행 · anthropic-eng 0건)을 같이 기록한다 — (a)는 독자 영향이 있어 #7 자체보다 우선.

## 1. 무엇이 일어나는가 (메커니즘)

- `kind: html` 소스 7개 = anthropic · anthropic-eng · claude-blog · anthropic-research · google-dev · meta-research · pytorch-kr-news. 목록 페이지에
  날짜가 없어 **글을 열어 봐야 날짜를 안다**(RSS·사이트맵 소스는 목록에 날짜가 있어 창 밖 글은 열지 않는다).
- `fetch_generic_html`(`retrieval/sources.py`): 목록 → `_article_links`(목록 경로 한 단계 아래 `{path}/{slug}` 링크; `article_path` 가 있으면 그
  접두 아래) → 링크를 **순서대로** 열어 `_extract_article` → `_is_stale(published, window_hours)` 로 창(48h) 밖이면 버림 → **풀**(`select: llm`
  이면 `_SELECT_POOL`=12, 아니면 `max_items` 또는 5)을 채우거나 **예산**(`_SOURCE_BUDGET_S`=180s, 요청당 `_FETCH_TIMEOUT_S`=20s)을 넘을 때까지.
- 어제 "창 밖"으로 버린 URL 을 기억하는 장치가 없다 → **매 run 같은 옛 글을 다시 연다.** 새 글이 풀만큼 있는 날이 드물어 사실상 매일 목록 전체.
- 가시성: 창 밖 폐기와 HTTP 실패(`continue`)는 **로그가 없다.** 경고가 남는 것은 스텁(<500자 `fetch stub`)·offsite·예산 초과·요청 타임아웃뿐.
  목록 링크가 0개면 경고 없이 빈 결과(§6-b).
- `_is_stale("")` = False — 날짜를 못 뽑은 페이지는 **통과**(fail-open). 오늘 재현에선 0건(§2.3).

## 2. 관찰

### 2.1 로컬 재현 — 2026-10-31(토) 운영과 같은 순서·중단 규칙, `tools/html_listing_waste.py`

| 소스 | 목록 링크 | 연 페이지 | 남은 글 | 버린 이유 | 시간 |
|---|---|---|---|---|---|
| anthropic | 26 | 26 | 0 | 창 밖 24 · 스텁 2(Product/Security 허브) | 3s |
| anthropic-eng | 0 | 0 | 0 | 목록에 글 링크가 없음(§6-b) | 0s |
| claude-blog | 10 | 10 | 0 | 창 밖 10 | 4s |
| anthropic-research | 22 | 22 | 0 | 창 밖 22 | 2s |
| google-dev | 38 | 38 | 1 | 창 밖 24 · 응답 없음 12(네비·외부 링크) · 본문 없음 1 | 23s |
| meta-research | 18 | 18 | 0 | 창 밖 17(Muse 고정 글 2 = offsite 경고 포함) · 응답 없음 1 | 8s |
| pytorch-kr-news | 30 | 30 | 4 | 창 밖 25 · 스텁 1(카테고리 설명) | 44s |
| **합계** | 144 | **144** | **5** | 창 밖 122(85%) · 응답 없음 13 · 스텁 3 · 본문 없음 1 · 날짜 없음 0 | ≈85s |

- 토요일이라 새 글이 적지만, 평일도 풀(5·12)을 채우는 소스는 드물어 연 페이지 수는 비슷하다(PTK 는 평일 48h 새 글 ≈5건 < 풀 12 → 30건 전부).
- anthropic 목록 26 링크 중 7개는 글이 아니라 **허브 페이지**(announcements·partnerships·product·security·features·policy·safeguards) — §6-a.
- google-dev 의 "응답 없음" 12 는 목록 경로 아래 네비 링크(`/community`·`/program`·`/publish`·`/products`…)와 외부 단축 링크 — 매일 12번 실패 요청.
- meta-research 의 Muse 고정 글 2건은 날짜가 2026-04-08·2022-11-18 로 추출돼 창 밖 + canonical 이 다른 호스트 → 매일 `fetch offsite` 경고(#1 에서 본 것).

### 2.2 운영 로그 — CloudWatch 2026-10-21~30(정기 run 10회 + 시험 발송)

| 경고 | 줄 수 | 뜻 |
|---|---|---|
| `[WARN fetch stub]` pytorch-kr-news "'새로운 소식' 카테고리의 설명" | 16 | 매 run 같은 카테고리 페이지(#8) |
| `[WARN fetch stub]` anthropic Security / Product | 16 / 15 | 매 run 같은 허브 2개(#8) |
| `[WARN fetch offsite]` meta-research Muse 고정 글 2건 | 14(+v65 새 문구 2) | 매 run 같은 옛 글 |
| `fetch budget`/요청 타임아웃 | 1(claude-blog) | 드묾 |

창 밖 폐기는 로그가 없어 운영에서 직접 셀 수 없다 — 위 재현(§2.1)이 추정치의 근거.

### 2.3 fail-open(날짜 없음 → 통과)의 실제

오늘 144 페이지 중 날짜를 못 뽑은 페이지 0. 10일 ledger 의 html 소스 카드 69장(`tools/undated_published.py`) 중 "목록·허브가 카드가 된" 2장(§6-a)은
**날짜로 통과**한 것(허브 페이지의 추출 날짜 = 맨 위 글 날짜)이지 fail-open 이 아니다. fail-open 의 실제 사례는 확인되지 않았다.

## 3. 왜 문제인가

- **품질 문제가 아니다.** 창 밖으로 버린 글은 원래 메일에 실릴 글이 아니므로 독자가 보는 메일은 바뀌지 않는다. LLM 호출도 없다.
- **낭비:** 매 run HTTP ≈140회 · ≈1.5분(13분 run 의 일부). 10일이면 ≈1,400 페이지 요청 중 카드는 69장(§2.3).
- **예의(politeness):** 커뮤니티 사이트(PTK Discourse)에 매일 30회, Meta 18회, Anthropic 26회 — **같은 옛 페이지를** 매일.
- **노이즈:** 같은 WARN 이 매일 찍혀(#8) 진짜 신호(새 스텁·새 offsite)를 가린다. 10-30 #1 에서 Muse 경고를 "큰 발표 누락"으로 오진한 원인이기도 하다.
- 우선순위: **낮음**(독자 영향 0). §6-a 가 독자 영향이 있어 먼저 다룰 가치가 있다.

## 4. 범위

- **안:** html 리스팅 7개 소스의 재열람(어제 창 밖 URL 을 기억할지 · 목록 순서를 믿고 조기 중단할지 · 폐기 사유 가시성) · 네비 링크 실패 요청(google-dev).
- **밖:** RSS·사이트맵 소스(창 밖은 열지 않음) · 카드 품질 · 선별/dedup 순서(#4b) · 스텁 경고 자체(#8 — 단 원인이 같아 함께 풀릴 수 있음).

## 5. (참고) 토론 전 선택지 후보 — 미승인, dive-in 때 다시 정리

1. **창 밖 URL 기억:** 창 밖으로 버린 URL 을 소스별로 기록(DDB 작은 표 또는 source-store 메타)해 다음 run 은 열지 않는다. 가장 직접적.
   위험 = 날짜가 바뀌는 페이지(허브·수정 글)는 영구 제외 — 허브 문제(§6-a)엔 오히려 득이지만 "옛 글이 갱신되어 다시 신선해지는" 경우를 잃는다(현 정책상 허용 안 하는 경우라 손실 없음 추정).
2. **최신순 신뢰 조기 중단:** 연속 N건이 창 밖이면 멈춘다. 위험 = 목록이 최신순이 아닌 소스(anthropic 목록은 허브·고정 링크가 섞임, PTK 는 최신순) → 소스별 플래그 필요.
3. **기계용 목록으로 갈아타기:** 날짜가 있는 RSS/사이트맵(사이트별 조사 필요 — PTK `/c/news/14.rss` 는 robots 차단, anthropic.com 사이트맵 유무 미조사).
4. **그대로 둔다:** 하루 140 요청·1.5분 수용, #8 노이즈만 따로 처리.

## 6. 이 조사에서 드러난 새 항목 2건

### (a) Anthropic News **허브 페이지가 카드로 발행됨** — 독자 영향 있음, #8 보다 우선

> **상태(2026-11-01): 구현 C(사용자 승인 "go") — 작업 트리, 미커밋·미배포.** 관문 = 카탈로그 `exclude_paths`(아는 비기사 URL 을 목록
> 단계에서 제거) + `page_type: article`(선언된 og:type/JSON-LD 가 기사가 아니면 skip + `[WARN fetch non-article]`, 모르는 새 허브용).
> 근거·기각 선택지는 README 행과 `hub-signals-20261101.txt`·`tools/hub_signals.py`·`tools/feed_sitemap_probe.py`·
> `tools/sitemap_lastmod_vs_published.py`·`tools/gate_replay.py`. 아래 정의는 발견 당시 기록 그대로.

- **메커니즘:** `_article_links` 는 `/news/<slug>` 를 전부 글로 본다. anthropic 목록에는 허브 7개가 섞여 있고, 허브 본문 = 최신 글들의 제목·리드 모음,
  trafilatura 날짜 = 맨 위 글의 날짜 → **허브에 새 글이 48h 안에 올라온 날 "신선한 글"로 통과.** product·security 는 <500자라 스텁으로 걸러져 경고만(#8);
  announcements·partnerships·features·policy·safeguards 5개는 카드 자격.
- **발행 기록(관리자 ledger 10-21~30, `tools/hub_cards.py`):**
  - 10-21 run `/news/announcements` → **PUBLISH "Announcements"**(동결 본문 1,438자, 앞부분 "Announcements - Oct 21, 2026 Physicist Christopher Stubbs joins…"). 같은 run 에 Christopher Stubbs 글 카드도 발행.
    card-cache 에서 카드를 못 찾아(키 불일치) 원장 사실만 기록.
  - 10-28 run `/news/partnerships` → **PUBLISH "Partnerships"**(1,712자, 앞부분 "Partnerships - Oct 27, 2026 Expanding our partnership with GSA…"). 같은 run 에 GSA 글 카드도 발행.
- **독자가 본 것(Partnerships — 7명 ledger 모두에 있음, `tools/hub_recipients.py`):** 헤드라인 "Partnerships". 요약 = GSA 40% 할인(10-27 글)에 **Accenture(09-18 글)·TCS·Gates Foundation·PwC** 의 옛 소식을
  한 글처럼 이어 붙임. claims 전부 VERIFIED(동결 허브 본문에 그 문장들이 있으니 certifier 도 맞게 통과) → **"✓ 검증" 도장을 단 옛 소식 재탕 + 같은 메일의 GSA 카드와 중복.**
- **재발 양상:** URL 키 dedup 이 재발행은 막아 **허브당 최대 1회**(Announcements 는 10-28 에도 10-28 날짜로 신선했지만 카드 없음 = dedup). 10-01~10-30 ledger 에 허브 카드는 이 2장뿐 —
  policy(10-15 갱신)·safeguards(10-14 갱신)는 창 안이던 10-14/15 run 에도 카드가 **없었다** → 허브가 갱신돼도 항상 카드가 되는 건 아니다(풀 5 가 목록 앞쪽 새 글로 먼저 차면
  뒤쪽 허브는 열지 않음 — 추정, dive-in 때 확인). 남은 허브 3개(features·policy·safeguards)도 조건이 맞는 날 1회씩 나올 수 있다.
- dive-in 때 볼 질문(결론 아님): 같은 run 의 GSA 카드와 왜 중복으로 안 잡혔나(식별 키 url/title/hash 가 서로 다름 · v64 재보도 판정의 적용 범위) ·
  허브 판별 신호(본문에 날짜가 여러 개 · 목록 경로 아래 또 다른 목록 · 제목이 한 단어) · 소스별 제외 목록 vs 제너릭 휴리스틱(카탈로그 원칙 = 매체별 코드 0).

### (b) anthropic-eng 가 **0건 수집 중**(조용한 실패)

- 오늘 목록 HTML 325KB · href 142개 · `/engineering/` 글 링크 **0**(클라이언트 렌더링 셸로 보임; `<title>` 은 "Engineering \ Anthropic") → `fetch_generic_html` 이
  **경고 없이** 빈 결과를 돌려준다.
- ledger 09-01~10-30(`tools/anthropic_eng_history.py`): 카드 6장 = "Best practices for Claude Code" 문서 페이지 **5회**(10-10 감사의 dedup 구멍 사례, 10-16 수정) +
  10-13 "Redesigning source control at Anthropic"(연구 목록에도 있는 글) → 실제 글 1편. **10-13 이후 0.** 고장 시점 = 10-13 이후, 정확한 시작일 미상(0링크·창 밖 폐기 모두 로그 없음).
- 영향: Anthropic Engineering 글(월 수 편, 사용자 1순위 관심 = Anthropic 1차 글)이 빠진다. 7명 모두.
- dive-in 때 볼 질문: 목록이 언제 JS 셸로 바뀌었나 · 대체 경로(RSS/사이트맵 · 연구 목록과 겹치는지) · "목록 링크 0 = 경고"(가시성, silent-failure 계열).

## 7. 재현

```
# 목록 재현(네트워크만, 저장소·DDB 무변경 · ≈1.5분)
uv run python docs/work_note/Oct-2026/261030-improve-today-briefing/tools/html_listing_waste.py
# 10일 ledger 의 html 소스 카드(허브 의심 표시)
BACKEND=dynamo uv run python docs/work_note/Oct-2026/261030-improve-today-briefing/tools/undated_published.py --since 2026-10-21 --until 2026-10-30
# 허브 카드 2장 원자료 + Anthropic Engineering 카드 URL
BACKEND=dynamo uv run python docs/work_note/Oct-2026/261030-improve-today-briefing/tools/hub_cards.py
BACKEND=dynamo uv run python docs/work_note/Oct-2026/261030-improve-today-briefing/tools/hub_recipients.py
# 소스별 일별 카드 수(anthropic-eng 마지막 카드 날짜)
BACKEND=dynamo uv run python docs/work_note/Oct-2026/261030-improve-today-briefing/tools/anthropic_eng_history.py --since 2026-09-01 --until 2026-10-30
# 운영 경고
aws logs filter-log-events --region us-east-1 --log-group-name /aws/bedrock-agentcore/runtimes/briefing_agent-b9uh7rDAqL-DEFAULT \
  --start-time <epoch_ms> --filter-pattern '"WARN fetch"' --query 'events[].message' --output text
```
