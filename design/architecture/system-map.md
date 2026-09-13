# 시스템 지도 (System map) — 이 시스템은 어떻게 생겼나

> **이 문서 = 전경(前景) 지도.** 배포 지형부터 신뢰 경계까지 7장의 그림으로 시스템 전체를 훑는다.
> 카드 *한 장*이 만들어지는 클로즈업은 [`pipeline-flow.md`](./pipeline-flow.md), 왜 이 구조인지의 근거는
> [`four-component-analysis.md`](./four-component-analysis.md) · [`card-layering-analysis.md`](./card-layering-analysis.md) 를 본다.

**읽는 법.** 각 절 끝의 `▸ 코드` 는 그림이 가리키는 실제 코드 위치다(`파일:라인`). 그림과 코드가 어긋나면
코드가 옳다 — 이 문서를 고쳐라. 라인 번호는 2026-09-13 기준이며, 함수명이 같이 적혀 있으니
번호가 밀렸어도 `grep` 으로 찾을 수 있다.

**이 문서는 변하는 수치를 본문에 박지 않는다.** 테스트 개수·소스 개수·비용 같은 값은 커밋마다 변해서,
문서에 적어두면 반드시 낡는다(실제로 README·CLAUDE.md 의 테스트 수가 서로 다르게 낡아 있었다).
그런 값은 [부록](#부록-변하는-값은-명령으로-확인한다) 의 명령으로 확인한다.

---

## 0. 한 문장으로

**결정론 파이썬 코드(gate)가 오케스트레이터이고, 두 LLM 하니스는 그 밑에서 서로를 볼 수 없는 상태로
각각 작성과 검증을 맡는다.** 신뢰는 모델이 똑똑해서가 아니라 *정보 흐름을 구조적으로 끊었기* 때문에 생긴다.

---

## 1. 배포 지형 — 5개 단위가 어디 있나

```
        ┌─────────────────────────────────────────────────────────────┐
사용자→ │ ④ Web UI      CloudFront(SPA) + HTTP API(Lambda/FastAPI)    │
브라우저│               GET /catalog  /sample   POST /trial  PUT /profile│
        └──────────────────────────┬──────────────────────────────────┘
                                   │ 프로필 쓰기 (lens·sources·send_hour·depth)
                                   ▼
 ┌──────────────┐  시간당 1회  ┌──────────────────┐  invoke(mode=scheduled)
 │ ⑤ EventBridge├────tick─────►│ ⑤ Lambda "poker" ├──────────────────┐
 │   Scheduler  │              │ fire-and-return  │  ~2초 후 즉시 반환 │
 └──────────────┘              └──────────────────┘                  ▼
                                                    ┌──────────────────────────────┐
 ┌────────────────────────────────┐                 │ ② AgentCore Runtime          │
 │ ③ DynamoDB (us-east-1)         │◄── 읽기/쓰기 ──►│  컨테이너에 claude+codex 번들 │
 │  source-store  (정본 원문)      │                 │  add_async_task → 최대 8h    │
 │  card-cache    (검증 카드)      │                 └───────────┬──────────────────┘
 │  ledger        (발행 이력)      │                             │
 │  users / trials / sent-log     │                             │ SES SendEmail
 └────────────────────────────────┘                             ▼
                                                        ┌────────────────┐
 ┌────────────────────────────────┐   기본 OFF          │  사용자 메일함  │
 │ ① AgentCore Gateway (MCP)      │◄─ GATEWAY_ENABLED=1 └────────────────┘
 │  fetch_article │ get_source    │
 │  discover_feed │ ← 이 3개뿐    │   ※ gate/author/certify 는 미노출
 └────────────────────────────────┘
```

**⑤ Lambda 가 "찌르고 바로 돌아오는(fire-and-return)" 이유.** Lambda 는 15분 하드 캡이 있는데 브리핑 한 번은
9~13분, 길면 46분까지 걸린다. 그래서 Lambda 는 Runtime 을 깨우고 `accepted` ack 만 받고 끝낸다
(`read_timeout=110`, 재시도 0 — invoke 가 비멱등이라). 실제 작업은 Runtime 안 `add_async_task` 가
최대 8시간 세션으로 붙든다. **긴 작업을 Lambda 밖으로 밀어낸 구조.**

**① Gateway 의 화이트리스트가 3개뿐인 건 보안이 아니라 아키텍처 불변식이다.** `lambda_handler` 의 dispatch 는
if/elif 3개로 하드코딩돼 있어 MCP 호출에서 `certify()` 로 가는 *코드 경로가 존재하지 않는다*.
검증자를 도구로 노출하면 작성자가 자기를 채점할 수 있게 된다.

> ▸ 코드 — `scheduler/lambda_handler.py:44` `handler` · `:36` `_build_client` /
> `runtime/agentcore_runtime.py:44` `briefing_entrypoint` / `gateway/gateway_handler.py:30` `lambda_handler` /
> `core/stores/backends.py:17` `make_stores`(local↔dynamo 단일 토글)

---

## 2. 하루의 제어 흐름 — 누가 누구를 언제 부르나

```
 매시 정각 (EventBridge)
     │
     ▼
 handler(event)                        ← scheduler/lambda_handler.py:44
     │  invoke_agent_runtime(payload={mode:"scheduled", now_utc, run_date, dry_run})
     ▼
 briefing_entrypoint(payload)          ← runtime/agentcore_runtime.py:44
     │  task_id = app.add_async_task("scheduled_briefing")
     │  threading.Thread(_bg).start()
     ├──────────────► yield {"type":"accepted"}   ─── Lambda 는 여기서 끝
     │
     ▼ (백그라운드)
 dispatch(settings, store, users, now) ← scheduler/dispatch.py:22
     │
     ├─ users_due_now(users, now_utc)                  ← due.py:17  ★ 순수함수
     │     각 user.timezone 으로 변환 → local.hour == send_hour ?
     │     예) 07:00 KST 사용자 → UTC 22:00 tick 에서만 due
     │     ▸ due 0명이면 여기서 끝 (하루 23번은 아무것도 안 함)
     │
     ├─ run_briefing(settings, store, due_users, ...)  ← core/pipeline.py:49  ★ 그림 3
     │
     └─ for b in briefings:
            should_deliver(b)?          → b.published > 0 이어야 함 (fail-closed)
            sent_log.already_sent()?    → 같은 run_date 재실행 = 멱등
            deliver_fn(b)               → SES SendEmail  ★ 유일한 비가역 지점
            sent_log.mark_sent(record={sent_at, published, quarantined,
                                       duration_ms, cost_usd, message_id})
```

**사용자가 100명이어도 EventBridge 규칙은 1개다.** 흔한 설계는 사용자별 크론 규칙을 만드는 건데
(규칙 수 = 사용자 수, 쿼터 폭발), 여기선 규칙을 시간당 1개로 고정하고 `users_due_now` 라는 **순수 함수**가
"지금 누가 due 인가"를 계산한다. 시계를 인자로 주입하니 "07:00 KST = 전날 22:00 UTC" 같은 타임존 경계를
AWS 없이 단위 테스트로 못박을 수 있다.

**비가역 조치가 딱 한 줄(`deliver_fn(b)`)로 좁혀져 있고 그 앞에 게이트가 3개다** — `published > 0` ·
`already_sent` · (그 전에) gate 의 PUBLISH 판정. 이 저장소의 설계 습관: *되돌릴 수 없는 일은 한 곳에 모으고
앞을 두껍게 막는다.*

> ▸ 코드 — `scheduler/due.py:17` `users_due_now` / `scheduler/dispatch.py:22` `dispatch` /
> `scheduler/deliver.py:16` `should_deliver` · `:21` `make_ses_deliver`

---

## 3. 파이프라인 내부 — `run_briefing` 한 번

```
 run_briefing(settings, store, users, ...)
 │
 │ ① 수집 대상 = 모든 사용자 선택의 합집합 (1회만 페치)
 │    fetch_set(u.sources for u in users)  →  [Source, ...]
 │
 ▼
 curate(store, targets)                                   ← retrieval/curation.py:42
 │   for source in targets:                     ┌── 소스 하나 실패해도 continue
 │     ├─ fetch  (rss=feedparser / html=trafilatura / auto=피드 자동발견)
 │     │         소스별 window_hours(late-post 보정 48h) · max_items
 │     ├─ 필터 ①  require_ai ?  → Haiku 판정자(폴백=키워드)로 AI 무관 기사 컷
 │     ├─ 필터 ②  캡 초과 ?     → select=llm 이면 Haiku pick-K, 아니면 최신순 K
 │     └─ freeze()  ─────► sha256(정규화 텍스트) = source_id 로 **동결**
 │                          ▲ author 도 certifier 도 *이 바이트*를 본다 (anti-cheat)
 ▼
 {source_key: [FrozenSource, ...]}
 │
 ▼ for u in users:                       ← 여기서부터 사용자별
   │
   ├─ ledger 조회 → prior_published (이전 run 에서 PUBLISH 한 source_id 제외)
   │                 ※ window 48h 가 만든 런 겹침을 명시적으로 제거
   │
   └─ for fs in 이 사용자의 기사들:
         ┌──────────────────────────────────────────────────────┐
         │ try:  _process(fs, u, ...)      ★ 카드별 격리(비협상) │
         │ except: warn 하고 이 카드만 드롭 — 브리핑은 계속       │
         └──────────────────────────────────────────────────────┘
                            │
                            ▼
                    ┌───────────────┐
                    │  그림 4·6 참조 │  사실층 → 검증 → 해석층
                    └───────┬───────┘
                            ▼
         render_email(cards, u, ...)   ← PUBLISH 카드만, depth 로 밀도 조절
                            ▼
                    UserBriefing(cards, email, published, quarantined,
                                 cost_usd, duration_ms)
```

**카드를 감싼 `try/except` 는 장애 대응으로 태어난 코드다.** 2026-07-02 아침, 카드 하나의 author 타임아웃이
브리핑 *전체*를 무너뜨려 발송이 0건이 됐다. 배치 처리에서 "부분 실패를 흡수하는 경계를 어디에 그을 것인가"가
곧 가용성이고, 여기서 그 경계는 **카드 1장**이다. (`(카드, category)` 를 튜플로 묶어 도는 것도 이 때문 —
카드가 드롭될 때 positional zip 이 어긋나지 않게.)

**동결(freeze)이 이 시스템의 anti-cheat 장치다.** 작성자가 기사를 페치하면 자기가 가져온 텍스트를 자기가
요약하고 그걸 검증받게 되니 "검증"이 무의미해진다. 그래서 페치는 fabric(파이프라인)이 하고, sha256 으로
주소를 매겨 얼려두고, author 와 certifier 는 *같은 source_id* 를 읽는다. **정규화 함수가 딱 하나인 것도 같은
이유** — 두 곳에서 정규화하면 바이트가 갈린다. (그래서 `normalize` 를 바꾸면 모든 source_id 가 바뀐다:
원장이 쌓인 뒤로는 사실상 고정이다.)

> ▸ 코드 — `core/pipeline.py:49` `run_briefing` · `:107-113` 카드별 격리 · `:137` `_process` /
> `core/retrieval/curation.py:42` `curate` · `:22` `_DEFAULT_MAX_ITEMS=5` · `:23` `_SELECT_POOL=12` /
> `core/retrieval/selection.py:38` `llm_select` · `:33` `latest_k` /
> `core/stores/source_store.py:66` `freeze` · `:32` `normalize` / `core/render.py:142` `render_email`

---

## 4. ★ 핵심 — verify-before-publish gate 와 정보 차단벽

이게 이 프로젝트의 존재 이유다.

```
                    ┌──────────────── gate.produce_card() ────────────────┐
                    │        (결정론 파이썬 코드 = 신뢰의 원천)              │
                    └──────────────────────┬──────────────────────────────┘
                                           │
       ┌───────────────────────────────────┴──────────────────────────────┐
       │                                                                  │
       ▼                                                                  ▼
┌──────────────────────────┐                              ┌──────────────────────────┐
│  AUTHOR   `claude -p`    │                              │ CERTIFIER  `codex exec`  │
│  ─────────────────────   │                              │ ──────────────────────   │
│  clean dir (빈 임시폴더)  │                              │ clean dir (빈 임시폴더)   │
│  --system-prompt 만 통제 │                              │ --skip-git-repo-check    │
│  timeout 360s            │                              │ timeout 120s             │
│  Bedrock 라우팅 = 호출 env│                              │ ~/.codex/config.toml 소유 │
│                          │                              │  (우리 .env 가 아님)      │
│  받는 것:                │                              │  받는 것: envelope 4필드  │
│   • 동결 원문            │        ╔═══════════╗         │   • source_excerpt       │
│   • lens 지침            │        ║  차단벽    ║         │   • claim_text           │
│   • user skill.md        │        ║           ║         │   • claim_type           │
│   • 오늘 날짜            │        ║ narration ║         │   • schema               │
│                          │        ║  누설 0   ║         │                          │
│  내는 것:                │        ╚═══════════╝         │  못 보는 것:              │
│   summary                │                              │   ✗ author 의 추론/설명   │
│   why_it_matters         │                              │   ✗ lens · skill · user   │
│   claims[] (원자적)      │                              │   ✗ 다른 claim 들         │
│   ※ headline 은 안 만듦  │                              │   ✗ repo CLAUDE.md/AGENTS │
│     (= 기사 원제목)      │                              └──────────────────────────┘
└──────────────────────────┘
```

**Maker-Checker 루프** (`max_attempts=2`):

```
  draft_fn(source, user)  ──►  card{claims: C1..Cn}
        │
        ▼
  reroute_claim_types(card)        ★ author 의 라벨을 무시하고 코드가 재분류
        │                            숫자가 있으면 무조건 arithmetic
        ▼
  for attempt in 1..2:
     verdicts = verify_fn(card)     ── claim 마다 envelope 조립 → certify()
        │
        ├─ BLOCKED 없음 ─────────────────────────────► PUBLISH ✓ (attempt 기록)
        │
        └─ BLOCKED 있음 ─┬─ attempt 1 → revise_claims(prior, failed_ids)
                         │      ▲
                         │      └── 피드백 = **실패한 claim 의 id 목록뿐**
                         │          "왜 실패했는지"는 절대 안 알려줌
                         │          (알려주면 = teaching to the test = 상관 재발생)
                         │
                         └─ attempt 2 소진 → _degrade_or_quarantine()  ★ 그림 5
```

**"왜 두 개의 하니스인가"의 진짜 답은 차단벽이다.** 같은 모델에게 "네 요약을 검증해봐"라고 하면 그건
확인 도장(confirmation pass)이지 검증이 아니다. 두 조건이 동시에 충족돼야 독립 재도출이 된다 —
ⓐ **다른 모델 계열**(Claude ↔ GPT), ⓑ **작성자의 추론을 안 보여줌**. `_build_envelope` 가 동결본에서
4필드만 뽑아내는 **화이트리스트** 방식인 이유가 이것이다(블랙리스트면 새 필드가 생길 때마다 샌다).

**clean dir 이 비협상인 이유**가 여기서 드러난다. `codex exec` 를 저장소 폴더에서 돌리면
`AGENTS.md`/`CLAUDE.md` 가 자동 로드돼 certifier 가 "이 프로젝트는 뉴스 브리핑을 만들고 있다"를 알게 된다.
그 순간 조용히 상관관계가 생긴다 — 에러도, 경고도 없이. **그래서 이 저장소에는 `AGENTS.md` 를 두지 않는다.**

**재도출 피드백이 id 목록뿐**인 게 미묘하지만 결정적이다. 흔한 Maker-Checker 는 검증자 피드백을 전부 넘겨
작성자가 "정답에 맞춰 쓰게" 만든다. 그러면 2라운드 결과는 1라운드보다 *덜* 독립적이다. 여기선
"C3 이 실패했다, 원문을 다시 봐라"만 주고 이유는 안 준다.

> ▸ 코드 — `core/gate.py:95` `produce_card` · `:57` `_build_envelope` · `:44` `reroute_claim_types` ·
> `:67` `verify_card` / `core/authoring/author.py:290` `_run_author`(clean dir) · `:29` `_AUTHOR_TIMEOUT_S=360` ·
> `:183` `revise_claims` · `:360` `_build_revise_prompt` /
> `core/verification/certifier.py:143` `_run_codex`(clean dir) · `:32` `_CODEX_CMD` · `:33` `_CODEX_TIMEOUT_S=120` ·
> `:126` `_build_codex_prompt`

---

## 5. claim 판정 → 카드 결정 (결정론 게이트의 심장)

```
 certify(claim_id, envelope)                            ← certifier.py:59
 │
 ├── claim_type == "arithmetic" ──► _certify_arithmetic()        ← :84
 │                                   ★ LLM 을 아예 안 부른다. 순수 파이썬.
 │                                   numeric.scan(claim) vs numeric.scan(source)
 │                                   네임스페이스 분리: 수량 / 월 / 서수 / 퍼센트
 │                                     ("July"=월 7 이 수량 7 을 정당화하면 안 됨)
 │                                   값 대조 — "eight months" ↔ "8개월" 매칭
 │                                            "four trillion" ↔ "4조" 매칭
 │
 └── claim_type == "entailment" ──► _certify_entailment()        ← :195
                                     codex exec (clean dir, envelope only)
                                     실패·타임아웃·파싱불가 → DEMOTED (절대 VERIFIED 아님)

                              ▼
        ┌─────────────────────────────────────────┐
        │  VERIFIED   원문이 claim 을 함의함        │
        │  DEMOTED    원문으로 판단 불가 → '(미확인)'│
        │  BLOCKED    원문이 claim 과 모순          │
        └─────────────────────────────────────────┘
                              ▼
   _degrade_or_quarantine(card, verdicts)               ← gate.py:138

        core claim 이 BLOCKED ?  ──── YES ──►  QUARANTINE  (카드 spine 붕괴)
              │ NO
        VERIFIED 가 0건 ?        ──── YES ──►  QUARANTINE  (발행할 게 없음)
              │ NO
              └──────────────────────────────►  PUBLISH (열화 발행)
                                                 BLOCKED claim 은 드롭
                                                 DEMOTED 는 '(미확인)' 라벨로 생존
```

**arithmetic claim 은 LLM 이 아니라 코드가 판정한다.** 이게 이 시스템에서 가장 저평가된 설계다 —
숫자 검증은 결정론적이라 byte-stable 하고, 무료고, 재현 가능하다. 실제로 자기 데이터를 감사해보니
BLOCK 47건 중 **파이썬 산술 46건 : codex 1건** 이었다(2026-08-25,
[`docs/work_note/260825-AI-Day-Session-Title/`](../../docs/work_note/260825-AI-Day-Session-Title/)).
즉 "듀얼 하니스"의 무게중심은 실은 *결정론 게이트*였다.

**그 코드가 순진한 문자열 비교였다면 반대로 재앙이었다.** 원문은 영어("eight months"), claim 은
한국어("8개월")라 표층 대조는 원리적으로 실패한다 — 2026-07-17 이전엔 BLOCKED 243건이 *전부* 위양성이었다.
`numeric.scan` 의 값 기반 대조로 243→6 으로 줄이면서 catch-rate 100% 를 유지했다.
**정규화를 조금이라도 순진하게 하면 catch-rate 가 반토막** 나는 게 실증돼서, 이제 eval set 이 머지 게이트다.

**서수 하한(`_ORD_NUMERIC_MIN = 10`)의 사연.** 서수는 원문의 서수로 정당화하는 게 원칙인데, 한국어
'제109조'를 영어 원문은 'Article 109'(맨숫자)로 쓴다. 그렇다고 작은 서수까지 수량으로 정당화하면
'one of three co-chairs'(수량 3)가 '제3자 감사'(서수 3)를 VERIFIED 로 만든다 — 적대 검증에서 실증됐다.
법조문 번호는 실질적으로 두 자리 이상이라 이 하한이 동치는 지키고 누수는 막는다.

**QUARANTINE 을 "사람이 전수 검토"로 정의하지 않은 것도 실전 판단이다.** 대량 처리에서 사람 큐는 안 읽히고,
안 읽히는 큐는 silent drop 과 같다. 그래서 BLOCKED claim 만 드롭하고 검증된 부분집합을 발행하되,
**핵심 claim 이 막히면 카드 전체를 격리**한다. fail-closed 는 지켜진다 — **드롭 ≠ 발행**.

> ▸ 코드 — `core/verification/certifier.py:59` `certify` · `:84` `_certify_arithmetic` · `:195` `_certify_entailment` ·
> `:39` `_ORD_NUMERIC_MIN` / `core/verification/numeric.py` `scan`·`contains` / `core/gate.py:138` `_degrade_or_quarantine`

---

## 6. 2층 카드 — 왜 사실과 해석을 쪼갰나

```
  기사 1건 (source_id = sha256)
        │
        ▼
 ┌═══════════════════════════════════════════════════════════════┐
 ║  사실층 (fact layer)                    ★ 전 사용자 공유       ║
 ║  ────────────────────────────────────────────────────────────  ║
 ║  headline = 기사 원제목 (author 가 제목을 만들지 않음)          ║
 ║  summary  = 3~5문장                                            ║
 ║  claims[] = 요약의 모든 사실을 덮는 원자 단위                   ║
 ║                                                                ║
 ║  author 를 general lens · skill 없음 으로 호출  ← 그래서 공유가능║
 ║  → certifier 가 claim 마다 검증                                 ║
 ║                                                                ║
 ║  캐시 키: fact_card_key(source_id | author_model | PROMPT_VER)  ║
 ║           └─ lens·skill 이 키에 없음 = 사용자 1000명이 1장 공유 ║
 └═══════════════════════════════════════════════════════════════┘
        │
        │ verified_claims(fact)  ← VERIFIED 인 claim 만 다음 층에 넘김
        ▼
 ┌───────────────────────────────────────────────────────────────┐
 │  해석층 (interpretation layer)          (source, lens) 당 1회  │
 │  ───────────────────────────────────────────────────────────   │
 │  입력: [이미 발행된 요약] + VERIFIED claims + 동결 원문         │
 │  지시: "요약이 담지 않은 것 중 독자가 알아야 할 것을 써라"       │
 │  출력: why_it_matters (1~3문장) + based_on: [C1, C4]           │
 │                                                                │
 │  ▼ 결정론 lint (gate._interp_lint) — certifier 를 안 거치므로   │
 │    ① why 비어있지 않음                                          │
 │    ② based_on ⊆ VERIFIED claim ids                             │
 │    ③ 본문에 claim id 잔존 없음   ("역할 분리(C4, C5)가" 유출 방지)│
 │    ④ why 의 모든 숫자 ∈ (원문 ∪ VERIFIED claims)  ← 수치 밀수 차단│
 │                                                                │
 │  실패하면 → 사실층 why 로 폴백 (카드는 안 죽음, 층별 격리)      │
 │  캐시 키: interp_card_key(source_id|lens|fact_key|INTERP_VER)   │
 └───────────────────────────────────────────────────────────────┘
        │
        ▼
  render_email  ─►  ┌──────────────────────────────────────┐
                    │ 01  기사 원제목                       │
                    │ 📰 도메인 · 발행일 · 원문 →            │
                    │ 요약 · 원문 사실        ← lens 없음!   │
                    │ (요약 본문)                           │
                    │ ┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈  │
                    │ 사실들을 엮으면 · {lens} 관점 (해석)    │
                    │ (해석 본문 — 좌측 코럴 바)             │
                    │ ✓ 다른 AI 에이전트가 요약의 사실 N건 검증│
                    │   [· 미확인 M] [· 제외 K]             │
                    └──────────────────────────────────────┘
   ※ 요약 라벨에 lens 가 **없는** 게 2층화의 가시적 결과다 — 요약은 공통 사실층이라
     개인화 라벨을 붙이면 거짓말이 된다. 개인화는 아래 해석 블록으로 재정박됐다.
```

**2층화의 동기는 순전히 경제학이었다.** 원래 캐시 키에 `skill_md` 가 들어 있어 사용자마다 키가 달랐고
공유가 사실상 0이었다. 검증(비싼 부분)을 lens 와 무관한 층으로 내리자 비용이 O(기사 × 사용자) 에서
**O(기사) + O(기사 × lens)** 로 떨어졌다. lens 개수는 카탈로그가 정하는 작은 상수라(사용자 수와 무관),
사용자가 아무리 늘어도 검증 비용은 안 는다.

**캐시 키가 곧 무효화 장치**라는 게 이 저장소의 반복되는 함정이다. 2026-07-27 에 claim id 유출을 고쳤는데
사용자 메일엔 계속 유출된 문장이 나왔다 — **캐시 히트가 `interpret_card` 를 통째로 우회**했기 때문이다
(TTL 30일). 그래서 `INTERP_PROMPT_VERSION` 을 키 성분으로 직접 넣었다. `fact_key` 연쇄는 *사실층* 계약만
실어 나르므로 해석층 개정은 그 연쇄에 없다. **계약을 고치면 상수를 범프해야 하고, 안 하면 고침이 라이브에
안 닿는다.**

**해석층이 "요약을 보게" 만든 개정(interp-v1.2)이 가장 큰 품질 점프였다.** 이전 인터프리터는 claims 만 보고
자기가 무엇을 반복하는지 몰라서, 산출의 92%가 "요약만 읽고도 알 수 있는 말"이었다. 문체를 바꾸는 후보 5종은
전부 통찰률 4% 근처에서 정체했는데, **재료를 바꾸자(요약을 보여주고 "버린 것을 찾아라") 4%→36%** 로 뛰었다
(n=60 대응표본 · McNemar p=0.0000). **프롬프트 문제로 보이는 것이 사실은 *입력* 문제인 경우.**

> ▸ 코드 — `core/stores/cache.py:33` `fact_card_key` · `:43` `interp_card_key` /
> `core/authoring/author.py:42` `PROMPT_VERSION` · `:49` `INTERP_PROMPT_VERSION` · `:231` `build_interp_user_prompt` /
> `core/gate.py:219` `interpret_card` · `:192` `_interp_lint` · `:181` `_strip_claim_citations` · `:164` `verified_claims` /
> `core/pipeline.py:137` `_process`(2층 조립) / 설계 근거 = [`card-layering-analysis.md`](./card-layering-analysis.md)

---

## 7. 신뢰 경계 — 누가 무엇을 볼 수 있나

```
                    │ 동결  │ lens  │ user   │ author │ certifier │ 다른   │
                    │ 원문  │ 지침  │skill.md│ 추론   │ 판정근거  │ claim  │
 ───────────────────┼───────┼───────┼────────┼────────┼───────────┼────────┤
 gate (파이썬)      │  ✓    │  ✓    │   ✓    │   ✓    │    ✓      │   ✓    │
 author (claude -p) │  ✓    │  ✓    │   ✓    │  자신  │    ✗      │   ✓    │
 certifier (codex)  │  ✓    │  ✗    │   ✗    │   ✗    │   자신    │   ✗    │
 해석층 (claude -p) │  ✓    │  ✓    │   ✗¹   │   ✗    │  VERIFIED │VERIFIED│
                    │       │       │        │        │  claim만  │  만    │
 render (파이썬)    │ 링크만│  ✓    │   ✗    │   ✗    │  개수만²  │   ✗    │
 ───────────────────┴───────┴───────┴────────┴────────┴───────────┴────────┘

 ¹ v1 의 의도적 절충 — skill 을 주입하면 (source, lens) 공유가 깨진다.
   ※ 부작용: 사용자 skill.md 가 해석층에는 효력이 없다.
 ² 독자에게는 "사실 N건 검증"만 — 개별 claim 텍스트는 비노출(불변식)
```

**코드로 강제되는 불변식들:**

```
 author.py        →  certifier 를 import 하지 않음        (자기 채점 불가)
 gate.py          →  certify() 를 호출하는 유일한 모듈
 _build_envelope  →  화이트리스트 4필드 (블랙리스트 아님)
 _run_author      →  cwd = tempfile.mkdtemp()            (repo 컨텍스트 0)
 _run_codex       →  cwd = tempfile.mkdtemp()            (AGENTS.md 로드 0)
 pipeline         →  _FACT_USER = lens:general, skill:"" (사실층 user-blind)
 gateway_handler  →  dispatch 화이트리스트 3개           (MCP→certify 경로 부재)
```

**이 표의 각 ✗ 는 문서상의 약속이 아니라 코드 구조로 강제된다.** "certifier 에게 lens 를 주지 말자"가
규칙이면 언젠가 깨지지만, `_build_envelope` 가 4필드 dataclass 를 반환하면 lens 를 넘길 *방법이 없다*.
신뢰 속성을 규율이 아니라 타입과 프로세스 경계로 만든 것.

**해석층만 certifier 를 안 거치는 유일한 발행 텍스트다** — 그런데 카드엔 "✓ 검증" 배지가 붙는다.
이 비대칭이 위험(trust laundering: 검증 배지 아래 미검증 문장을 밀수)이라 결정론 lint 4종이 그 자리를
대신한다. 특히 ④ 숫자 밀수 검사가 핵심 — 해석이 "3배 성장"이라 쓰면 그 "3"이 원문이나 VERIFIED claim 에
실제로 있어야 통과한다. `based_on` 을 카드에 이식해 저장하는 것도 사후 감사를 위해서다(검사 후 폐기하면
"이 해석이 근거를 옳게 골랐나"를 나중에 물을 수 없다).

> ▸ 코드 — `core/pipeline.py:31` `_FACT_USER` / `core/gate.py:57` `_build_envelope` /
> `core/authoring/author.py:8`(불변식 주석) / `core/verification/certifier.py:126` `_build_codex_prompt` /
> `core/render.py:84` `_trust_line` / 근거 = [`four-component-analysis.md`](./four-component-analysis.md) §6

---

## 부록: 변하는 값은 명령으로 확인한다

| 알고 싶은 것 | 명령 |
|---|---|
| 테스트 개수·통과 여부 | `uv run pytest -q` |
| 린트 | `uv run ruff check src tests` |
| 출처 개수·목록 | `grep -c "^- key:" src/briefing/core/retrieval/catalog.yaml` |
| 출처 분야(섹션) | `grep "^  category:" src/briefing/core/retrieval/catalog.yaml \| sort -u` |
| lens 목록 | `grep "^- key:" src/briefing/core/lenses.yaml` |
| 무지출 전 파이프라인 | `uv run python -m briefing.local.run` |
| 파이프라인 디버그 추적 | `DEBUG=1 uv run python -m briefing.local.run` (stderr) |
| 실 e2e (과금) | `DEBUG=1 uv run python scripts/e2e_smoke.py` |
| 프로덕션 발송 시각 | DynamoDB `briefing-users` 의 `send_hour` (문서가 아니라 DB 가 진실) |

> ⚠️ 2026-09-13 확인 시점에 `README.md`(176) 와 `CLAUDE.md`(208) 의 테스트 개수가 서로, 또 실제와
> 어긋나 있었다. **문서에 수치를 박으면 반드시 낡는다** — 그래서 이 문서는 위 명령으로 위임한다.

## 관련 문서

| 문서 | 이 지도와의 관계 |
|---|---|
| [`pipeline-flow.md`](./pipeline-flow.md) | **카드 1장 클로즈업** — gate 단계별 흐름의 정본 그림 (이 지도의 그림 4·5 를 확대) |
| [`four-component-analysis.md`](./four-component-analysis.md) | **왜 이 4개 컴포넌트인가** — 신뢰 불변식의 근거 |
| [`card-layering-analysis.md`](./card-layering-analysis.md) | **왜 2층인가** — 그림 6 의 설계 근거 |
| [`retrieval-gateway-analysis.md`](./retrieval-gateway-analysis.md) | content-addressed 동결과 ① Gateway 승격 |
| [`../ux/email-ux-mockup.md`](../ux/email-ux-mockup.md) | 그림 6 맨 아래 카드의 UX 스펙 |
| [`../../docs/README.md`](../../docs/README.md) | 기능별 스펙·플랜·전달 기록 색인 (무엇이 언제 배포됐나) |
| [`../../CLAUDE.md`](../../CLAUDE.md) | 개발 규칙 — 하니스 격리·범위 제약·언어 규칙 |
