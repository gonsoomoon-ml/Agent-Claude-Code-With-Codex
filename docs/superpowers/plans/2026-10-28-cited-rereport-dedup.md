# 재보도 dedup — 구현 플랜 (Implementation Plan)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 이미 보냈거나 오늘 함께 보낼 원문을 본문에서 링크한 기사 중, 주로 같은 발표를 옮긴 글(재보도·한국어 소개)을 메일에서 뺀다.

**Architecture:** 수집 때 기사 본문 안의 다른 사이트 링크를 인용 키로 뽑아 run 동안 들고 다닌다. 사용자별 기존 dedup 뒤에, 인용 키가 보낸 URL(지난 90일) 또는 오늘 후보 URL 에 걸린 쌍만 Haiku 가 "같은 발표인가"를 판정하고, 같으면 인용한 쪽(B)을 뺀다. 판정 로직은 순수 함수(`drop_rereports`)로 두어 파이프라인과 재생 게이트가 같은 코드를 쓴다.

**Tech Stack:** Python 3.12 · trafilatura 2.1 · boto3 bedrock-runtime Converse · pytest · ruff · UV

**Spec:** `docs/superpowers/specs/2026-10-28-cited-rereport-dedup-design.md`

## Global Constraints

- 언어: 식별자·로그·CLI 영어, docstring·주석 한국어(CLAUDE.md).
- **fail-open 전부:** 판정 실패·JSON 없음·예외·발행 시각 모름 → B 를 남긴다. 브리핑을 막지 않는다.
- **A 는 언제나 유지** — 빠지는 것은 인용한 쪽(B)뿐.
- 판정 모델 = `settings.relevance_model_id`(현재 `global.anthropic.claude-haiku-5-5`), 새 env·IAM·테이블 없음. Converse + **thinking 기본(켬)·maxTokens 1500**(`additionalModelRequestFields` 없음), `temperature` 미지정(Haiku 5.5 거부). ★ 2026-10-28 게이트 정정 — 끄면 AAIF 기증 쌍 3/3 놓침·9→8 흔들림, 켜면 39/39(spec §4.3).
- 판정 입력: A·B 본문 각 최대 **8,000자**.
- `rereport_fn` 미주입(None)이면 재보도 단계 전체 off — 기존 테스트·로컬 무변경.
- 기존 `published_keys` 의미론 무변경(받은 기사 = PUBLISH·QUARANTINE · strictly-earlier · `run_date` 빈값 off).
- 빅테크 판별 = `top_picks.big_org(f"{category} {media}")` 가 빈 문자열이 아님(새 목록 없음).
- warn 라벨 `"pipeline rereport"`. 제외 건수는 기존 `deduped` 집계에 더한다.
- 커밋 메시지 끝: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`

## Review Focus

1. **언어 코드가 아닌 두 글자 첫 경로**(`/ai/…`, `/ml/…`) — 지우면 다른 글끼리 같은 키가 된다 → Task 1 `test_cite_key_keeps_non_locale_two_letter_segment`.
2. **링크가 없는 기사**(RSS 피드 요약 폴백·Gateway) — 인용 키가 비어 판정 대상이 아니어야 한다 → Task 2 `test_fetch_feed_summary_fallback_has_no_cited`.
3. **Gateway JSON 왕복**(`asdict` → JSON → `FetchedArticle(**a)`) — 새 필드 때문에 깨지면 안 된다 → Task 2 `test_fetched_article_json_roundtrip_with_cited`.
4. **판정자가 깨진 응답·예외** — B 는 남고 warn → Task 4 `test_llm_rereport_returns_none_on_bad_json`, Task 5 `test_drop_rereports_keeps_b_when_judge_fails`.
5. **같은 날 A 자신이 빠진 경우**(사슬·서로 인용) — 둘 다 빠지면 안 된다 → Task 5 `test_drop_rereports_dropped_a_is_not_used`.

---

## 파일 구조

| 파일 | 책임 | Task |
|---|---|---|
| `src/briefing/core/article_identity.py` | `cite_key`(언어 경로 정규화) · `published_keys(url_index=…)` 역참조 | 1 |
| `src/briefing/core/retrieval/sources.py` | 본문 링크 → 인용 키, `FetchedArticle.cited` | 2 |
| `src/briefing/core/retrieval/curation.py` | `curate(cited_out=…)` | 3 |
| `src/briefing/core/retrieval/rereport.py` (신규) | 판정 프롬프트·`llm_rereport`·`RereportVerdict`·`RereportFn` | 4 |
| `src/briefing/core/retrieval/relevance_bedrock.py` · `src/briefing/runtime/agentcore_runtime.py` | `make_bedrock_rereport` · `_production_fns` 주입 | 4 |
| `src/briefing/core/rereport_dedup.py` (신규) | `drop_rereports` 순수 로직(쌍 찾기·서로 인용·메모·fail-open) | 5 |
| `src/briefing/core/pipeline.py` | `rereport_fn` 인자 · 생존자 분리 · `drop_rereports` 호출 · warn | 5 |
| `scripts/dedup_audit/rereport_replay.py` (신규) | 재생 게이트(프로덕션 읽기 전용 + 실제 판정자) | 6 |

---

### Task 1: 인용 키 정규화 + 보낸 URL 역참조

**Files:** Modify `src/briefing/core/article_identity.py` · Test `tests/test_article_identity.py`

**Interfaces:**
- Produces:
  - `cite_key(url: str) -> str` — `url_key(url)` 결과에서 **첫 경로 조각이 언어 코드면 제거**. 언어 코드 = 소문자 `{ar,cs,da,de,el,en,es,fi,fr,he,hi,hu,id,it,ja,ko,nl,no,nb,pl,pt,ro,ru,sv,th,tr,uk,vi,zh}` 단독 또는 뒤에 `-xx`(국가 2자)·`-xxxx`(문자 체계 4자)·`-ddd`(숫자 3자). 키 없으면 `""`.
  - `published_keys(..., memo, url_index: dict[str, str] | None = None)` — 기존 반환 그대로, `url_index` 를 주면 **메타가 해석된** 받은 기사마다 `url_index[cite_key(meta.url)] = source_id` 를 채운다(같은 키면 최근 run_date 쪽).

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_article_identity.py` 에 추가:

```python
from briefing.core.article_identity import cite_key

def test_cite_key_strips_locale_segment():
    assert cite_key("https://claude.com/de/resources/articles/x") == "claude.com/resources/articles/x"
    assert cite_key("https://aws.amazon.com/ko/blogs/tech/y/") == "aws.amazon.com/blogs/tech/y"
    assert cite_key("https://example.com/zh-cn/a") == "example.com/a"
    assert cite_key("https://example.com/es-419/a") == "example.com/a"

def test_cite_key_keeps_non_locale_two_letter_segment():
    assert cite_key("https://blog.example.com/ai/post") == "blog.example.com/ai/post"

def test_cite_key_keeps_query_and_empty():
    assert cite_key("https://www.aitimes.com/news/articleView.html?idxno=1") == "aitimes.com/news/articleView.html?idxno=1"
    assert cite_key("/relative") == ""

def test_published_keys_fills_url_index(tmp_path):
    from briefing.core.article_identity import published_keys
    from briefing.core.stores.ledger import LocalLedger
    from briefing.core.stores.source_store import SourceStore
    store, led = SourceStore(str(tmp_path / "s")), LocalLedger(str(tmp_path / "l"))
    fs = store.freeze(url="https://claude.com/resources/articles/a", title="Title long enough here",
                      raw_text="본문", fetched_at="2026-10-22", media="Claude Blog")
    led.append("2026-10-22", "u", fs.source_id, "k", "PUBLISH", "H")
    led.append("2026-10-22", "u", "gone", "k", "PUBLISH", "H")            # 원본 없음 → 색인 없음
    idx: dict = {}
    published_keys(led, store, "u", "2026-10-25", 90, {}, url_index=idx)
    assert idx == {"claude.com/resources/articles/a": fs.source_id}
```

- [ ] **Step 2: 실패 확인** — Run: `uv run pytest tests/test_article_identity.py -q` · Expected: `ImportError: cannot import name 'cite_key'`
- [ ] **Step 3: 구현** — `cite_key` 와 `published_keys` 의 `url_index` 인자(기본 None, 기존 호출 무변경).
- [ ] **Step 4: 통과 확인** — Run: `uv run pytest tests/test_article_identity.py tests/test_pipeline.py -q && uv run ruff check src tests` · Expected: 전부 PASS, ruff clean
- [ ] **Step 5: 커밋** — `feat(dedup): cite_key(언어 경로 정규화) + published_keys url_index 역참조`

---

### Task 2: 본문 인용 키 추출

**Files:** Modify `src/briefing/core/retrieval/sources.py` · Test `tests/test_sources.py`

**Interfaces:**
- Consumes: Task 1 `cite_key`
- Produces:
  - `FetchedArticle.cited: tuple[str, ...] = ()` — 마지막 필드, 기본값(위치 생성자 5개 인자·Gateway JSON 무변경). **tuple**(JSON 직렬화 가능).
  - `_body_links(html_text: str) -> list[str]` — `trafilatura.extract(html_text, output_format="markdown", include_links=True)` 결과의 `](http…)` 링크(본문 안만 — 2026-10-28 실험에서 사이드바 제외 확인).
  - `_cited_keys(html_text: str, page_url: str) -> tuple[str, ...]` — `_body_links` 를 `cite_key` 로 정규화, **페이지 자신과 같은 호스트(첫 `/` 앞, cite_key 기준) 제거**, 빈 키 제거, 중복 제거·정렬.
  - `_extract_article` 와 `_fetch_feed` 의 전문 페이지 경로가 `cited=_cited_keys(page, url)` 로 채운다. 피드 요약 폴백(페이지 본문 미사용)은 `()`.

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_sources.py` 에 추가(오프라인 HTML):

```python
_CITING_HTML = _ARTICLE_HTML.replace(
    "<p>We are upgrading",
    '<p>See <a href="https://claude.com/de/resources/articles/orig">the post</a> and '
    '<a href="https://www.anthropic.com/news/same-site">ours</a>. We are upgrading',
).replace("<body>", '<body><nav><a href="https://claude.com/nav-only">nav</a></nav>')

def test_cited_keys_body_only_cross_site_locale_normalized():
    from briefing.core.retrieval.sources import _cited_keys
    keys = _cited_keys(_CITING_HTML, "https://www.anthropic.com/news/opus")
    assert keys == ("claude.com/resources/articles/orig",)     # /de/ 제거 · 같은 사이트·nav 제외

def test_extract_article_sets_cited():
    from briefing.core.retrieval.sources import _extract_article
    art = _extract_article(_CITING_HTML, "https://www.anthropic.com/news/opus", "anthropic")
    assert art.cited == ("claude.com/resources/articles/orig",)

def test_fetch_feed_summary_fallback_has_no_cited(monkeypatch):
    from briefing.core.retrieval import sources as s
    entry = {"title": "T", "link": "https://x/a", "summary": _ARTICLE, "published_parsed": None}
    monkeypatch.setattr("feedparser.parse", lambda _u: types.SimpleNamespace(entries=[entry]))
    monkeypatch.setattr(s, "_http_get", lambda _u: "")        # 전문 페이지 못 받음 → 피드 요약 폴백
    assert s._fetch_feed("https://feed", "k", window_hours=0)[0].cited == ()

def test_fetched_article_json_roundtrip_with_cited():
    import json
    from dataclasses import asdict
    a = FetchedArticle("k", "https://x/a", "t", "본문", "2026-10-25", cited=("claude.com/a",))
    b = FetchedArticle(**json.loads(json.dumps(asdict(a))))   # Gateway 경로와 같은 왕복
    assert tuple(b.cited) == ("claude.com/a",)
```

(`FetchedArticle` import 가 파일 상단에 없으면 추가. 기존 `_extract_body` 를 4-tuple 로 가짜 처리하는 테스트는 그대로 둔다 — `_cited_keys` 는 `_extract_body` 와 별개로 HTML 을 읽는다.)

- [ ] **Step 2: 실패 확인** — Run: `uv run pytest tests/test_sources.py -q` · Expected: 신규 4개 FAIL(`ImportError: _cited_keys` / `unexpected keyword 'cited'`)
- [ ] **Step 3: 구현** — 위 Interfaces 그대로. 전문 경로 호출부 2곳(`_extract_article` 반환, `_fetch_feed` 의 전문 사용 분기)만 `cited` 를 채운다.
- [ ] **Step 4: 통과 확인** — Run: `uv run pytest tests/test_sources.py tests/test_curation.py tests/test_gateway.py -q && uv run ruff check src tests` · Expected: 전부 PASS
- [ ] **Step 5: 커밋** — `feat(retrieval): 본문 인용 키 추출 — 본문 안·다른 사이트 링크(언어 경로 정규화)`

---

### Task 3: curate 가 인용 키 맵을 넘긴다

**Files:** Modify `src/briefing/core/retrieval/curation.py` · Test `tests/test_curation.py`

**Interfaces:**
- Consumes: Task 2 `FetchedArticle.cited`
- Produces: `curate(..., cited_out: dict[str, tuple[str, ...]] | None = None)` — 동결된 기사마다 `art.cited` 가 비어 있지 않으면 `cited_out[fs.source_id] = art.cited`(같은 source_id 는 처음 것). 반환 타입·기존 호출(`pipeline.py`·`runtime/supervisor.py`) 무변경.

- [ ] **Step 1: 실패하는 테스트 작성**

```python
def test_curate_fills_cited_out(tmp_path):
    from briefing.core.retrieval.curation import curate
    from briefing.core.retrieval.sources import FetchedArticle, Source
    from briefing.core.stores.source_store import SourceStore
    src = Source("s", "S", "https://s.com/feed", "rss", "en", category="News & Media")
    arts = [FetchedArticle("s", "https://s.com/a", "t1", "본문 a", "2026-10-25", cited=("claude.com/x",)),
            FetchedArticle("s", "https://s.com/b", "t2", "본문 b", "2026-10-25")]
    out: dict = {}
    by_key = curate(SourceStore(str(tmp_path)), [src], fetch_article_fn=lambda *_: arts, cited_out=out)
    sid_a = next(fs.source_id for fs in by_key["s"] if fs.url.endswith("/a"))
    assert out == {sid_a: ("claude.com/x",)}
```

- [ ] **Step 2: 실패 확인** — Run: `uv run pytest tests/test_curation.py -q` · Expected: `TypeError: … unexpected keyword argument 'cited_out'`
- [ ] **Step 3: 구현** — 인자 추가 + freeze 직후 채우기.
- [ ] **Step 4: 통과 확인** — Run: `uv run pytest tests/test_curation.py tests/test_pipeline.py -q` · Expected: PASS
- [ ] **Step 5: 커밋** — `feat(curation): cited_out — 인용 키 맵을 파이프라인에 전달`

---

### Task 4: Haiku 재보도 판정자

**Files:** Create `src/briefing/core/retrieval/rereport.py` · Modify `src/briefing/core/retrieval/relevance_bedrock.py`, `src/briefing/runtime/agentcore_runtime.py` · Test `tests/test_rereport.py`(신규), `tests/test_relevance_bedrock.py`, `tests/test_runtime.py`

**Interfaces:**
- Produces:
  - `class RereportVerdict(NamedTuple): same: bool | None; reason: str` — `same=None` = 판정 실패.
  - `RereportFn = Callable[[str, str], RereportVerdict]` — `(a_text, b_text)`.
  - `MAX_JUDGE_CHARS = 8000`
  - `REREPORT_SYSTEM: str` — 아래 문구 그대로(2026-10-28 실험판).
  - `llm_rereport(a_text: str, b_text: str, *, invoke: Callable[[str, str], str]) -> RereportVerdict` — user 메시지 = `"<A>\n{a[:8000]}\n</A>\n\n<B>\n{b[:8000]}\n</B>"`, 응답에서 첫 `{…}` JSON 파싱 → `same` 이 bool 이면 그 값, 아니면 None. **어떤 예외도 밖으로 내지 않는다**(None + reason 에 예외 이름).
  - `make_bedrock_rereport(settings) -> RereportFn` — 자체 `client.converse`(system 분리·thinking 기본·`REREPORT_MAX_TOKENS=1500`, 텍스트 블록 없으면 ""). ~~`_converse_text(..., max_tokens=300)` 재사용~~ — Task 6 게이트에서 정정.
  - `_production_fns`: `relevance_llm_enabled` 묶음에 `fns["rereport_fn"] = make_bedrock_rereport(settings)`.

`REREPORT_SYSTEM`(정확한 문구):

```
Article A was already sent to our reader. Article B was published later and links to A.
Question: is B mainly a report about the SAME announcement or content as A?

SAME (answer true): B covers A's announcement/finding/release as its main news — even if B translates it
(e.g. a Korean write-up), summarizes it, adds some extra details, quotes, reactions or comparisons.
DIFFERENT (answer false): B's main subject is something else — a different product, project, release or event —
and A is only cited as background, inspiration, or one item among several equal items.

Answer only JSON: {"same": true|false, "reason": "<one short sentence>"}
```

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# tests/test_rereport.py
from briefing.core.retrieval.rereport import MAX_JUDGE_CHARS, llm_rereport

def test_llm_rereport_parses_same():
    v = llm_rereport("A", "B", invoke=lambda s, u: 'ok {"same": true, "reason": "same launch"}')
    assert v.same is True and v.reason == "same launch"

def test_llm_rereport_returns_none_on_bad_json():
    assert llm_rereport("A", "B", invoke=lambda s, u: "no json").same is None

def test_llm_rereport_returns_none_on_exception():
    def boom(s, u): raise RuntimeError("throttled")
    v = llm_rereport("A", "B", invoke=boom)
    assert v.same is None and "RuntimeError" in v.reason

def test_llm_rereport_truncates_inputs():
    seen = {}
    llm_rereport("a" * 9000, "b" * 9000, invoke=lambda s, u: seen.setdefault("u", u) and '{"same": false, "reason": "x"}')
    assert seen["u"].count("a") == MAX_JUDGE_CHARS and seen["u"].count("b") == MAX_JUDGE_CHARS
```

`tests/test_relevance_bedrock.py`(기존 가짜 client 패턴 그대로): `make_bedrock_rereport` 가 `modelId == settings.relevance_model_id`, `additionalModelRequestFields` 없음(thinking 기본 — Task 6 정정), `inferenceConfig == {"maxTokens": 1500}`(temperature 없음)으로 Converse 를 부르고, 응답 텍스트 `'{"same": true, "reason": "r"}'` → `RereportVerdict(True, "r")`.
`tests/test_runtime.py::test_production_fns_wires_judge_when_enabled` 에 `assert "rereport_fn" in fns` 추가.

- [ ] **Step 2: 실패 확인** — Run: `uv run pytest tests/test_rereport.py tests/test_relevance_bedrock.py tests/test_runtime.py -q` · Expected: `ModuleNotFoundError: …rereport` 등
- [ ] **Step 3: 구현** — 위 Interfaces 그대로.
- [ ] **Step 4: 통과 확인** — 같은 명령 · Expected: PASS, `uv run ruff check src tests` clean
- [ ] **Step 5: 커밋** — `feat(rereport): Haiku 재보도 판정자 — "B 는 주로 A 와 같은 발표인가"(fail-open)`

---

### Task 5: 재보도 제외 로직 + 파이프라인 연결

**Files:** Create `src/briefing/core/rereport_dedup.py` · Modify `src/briefing/core/pipeline.py` · Test `tests/test_rereport_dedup.py`(신규), `tests/test_pipeline.py`

**Interfaces:**
- Consumes: Task 1 `cite_key`·`published_keys(url_index=)` · Task 3 `curate(cited_out=)` · Task 4 `RereportFn`·`RereportVerdict` · 기존 `top_picks.big_org`
- Produces:
  - `drop_rereports(survivors: list[tuple[FrozenSource, str]], *, cited: Mapping[str, tuple[str, ...]], sent_index: Mapping[str, str], get_source: Callable[[str], FrozenSource], judge: RereportFn, memo: dict[tuple[str, str], RereportVerdict]) -> dict[str, tuple[FrozenSource, RereportVerdict]]` — 반환 = `{빠질 B source_id: (A, 판정)}`. 순서:
    1. **(a) 과거:** B 의 인용 키가 `sent_index` 에 있으면 A = `get_source(sent_index[k])`(실패하면 그 키 건너뜀).
    2. **(b) 같은 날:** B 의 인용 키가 다른 생존자 A 의 `cite_key(A.url)` 와 같고, A 가 이미 빠질 목록에 없을 때.
       서로 인용(A 의 인용 키에 `cite_key(B.url)` 도 있음)이면 유지 쪽 결정: ① `big_org(f"{cat} {fs.media}")` 가 한쪽만 참이면 그쪽 유지 ② 아니면 `fetched_at`(발행일, date-only 는 자정) 이른 쪽 유지 ③ 파싱 불가·같음 → 이 쌍은 판정하지 않음.
    3. 쌍마다 `memo[(A.source_id, B.source_id)]` 를 쓰고 없으면 `judge(A.text, B.text)` 결과를 저장(None 포함).
    4. 한 B 에 걸린 A 중 **하나라도 `same is True`** 면 B 를 반환에 넣는다. `None`·`False` 는 남긴다.
  - `run_briefing(..., rereport_fn: RereportFn | None = None)` — None 이면 이 단계 off.
- **파이프라인 변경:** `curate(…, cited_out=cited)` · `rereport_memo: dict = {}`(run 공유) · 사용자마다 `published_keys(…, url_index=idx)` → 기존 신원 dedup 으로 **생존자 목록을 먼저 만들고** → `rereport_fn` 이 있으면 `drop_rereports(생존자, cited=cited, sent_index=idx, get_source=store.get_source, judge=rereport_fn, memo=rereport_memo)` → 빠질 B 마다 `deduped += 1` 과 `_debug.warn("pipeline rereport", f"{u.id}: 재보도 제외 — {B.title[:50]} ← {A.title[:50]} ({v.reason[:80]})")` → 나머지만 `_process`. 판정 실패(None)가 있었던 쌍은 `_debug.warn("pipeline rereport", f"{u.id}: 판정 실패 — 통과(fail-open): {B.title[:50]}")`(같은 run 에서 쌍당 1회). `drop_rereports` 자체 예외 → warn 후 이 사용자는 재보도 단계 off.

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_rereport_dedup.py`(FrozenSource 를 직접 만들어 쓰는 순수 테스트):

| 테스트 | 준비 | 기대 |
|---|---|---|
| `test_drop_rereports_past_pair_same` | B 인용 `claude.com/a`, `sent_index={"claude.com/a": "A1"}`, judge→`(True,"r")` | `{B.sid: (A1, …)}` |
| `test_drop_rereports_past_pair_different_keeps_b` | judge→`(False,"x")` | `{}` |
| `test_drop_rereports_keeps_b_when_judge_fails` | judge→`(None,"err")` | `{}` |
| `test_drop_rereports_same_day_pair` | 생존자 A(url `https://claude.com/a`)·B(인용 `claude.com/a`), judge→True | B 만 빠짐, A 유지 |
| `test_drop_rereports_mutual_prefers_big_tech` | A=(media "The Decoder", cat "News & Media") · B=(media "Claude Blog", cat "Anthropic"), 서로 인용, judge→True | **The Decoder 쪽이 빠짐**(Claude Blog 유지) |
| `test_drop_rereports_mutual_both_big_earlier_wins` | 둘 다 빅테크, fetched_at `2026-10-21` vs `2026-10-22` | 10-22 쪽이 빠짐 |
| `test_drop_rereports_mutual_unknown_time_keeps_both` | 둘 다 비빅테크, fetched_at `""` | `{}` · judge 호출 0 |
| `test_drop_rereports_dropped_a_is_not_used` | A 가 (a) 로 빠짐, C 가 A 를 인용 | C 는 A 기준으로 판정되지 않음(남음) |
| `test_drop_rereports_any_same_drops` | B 가 A1·A2 인용, judge A1→False·A2→True | B 빠짐 |
| `test_drop_rereports_memo_reused` | 같은 memo 로 두 번 호출 | judge 호출 1회 |

`tests/test_pipeline.py` 통합(기존 `_dedup_kw`·`_fetch_one`·`_user` 재사용, `FetchedArticle(..., cited=…)` 를 내주는 fetch fake):
- `test_rereport_off_when_fn_missing` — `rereport_fn` 미주입이면 원문 다음 날 인용 기사도 발행.
- `test_rereport_drops_citing_article_next_day` — 10-22 원문 발행 → 10-25 인용 기사 + judge→True → 그 사용자 발행 0, stderr 에 `"재보도 제외"`.
- `test_rereport_judge_called_once_for_two_users` — 사용자 2명, judge 호출 횟수 1.

- [ ] **Step 2: 실패 확인** — Run: `uv run pytest tests/test_rereport_dedup.py tests/test_pipeline.py -q` · Expected: `ModuleNotFoundError: …rereport_dedup` / `unexpected keyword 'rereport_fn'`
- [ ] **Step 3: 구현** — `drop_rereports` 와 파이프라인 변경(위 Interfaces 그대로).
- [ ] **Step 4: 통과 확인** — Run: `uv run pytest -q && uv run ruff check src tests` · Expected: 실패 0, ruff clean
- [ ] **Step 5: 커밋** — `feat(pipeline): 재보도 제외 — 인용 쌍만 Haiku 판정, 서로 인용 시 빅테크 우선(fail-open)`

---

### Task 6: 재생 게이트

**Files:** Create `scripts/dedup_audit/rereport_replay.py`

**Interfaces:**
- Consumes: Task 1 `cite_key`·`published_keys(url_index=)` · Task 2 `_cited_keys` · Task 4 `make_bedrock_rereport` · Task 5 `drop_rereports` · 기존 `load_settings`
- Produces: CLI `rereport_replay.py --user-prefix 445814b8 --since 2026-10-21 --until 2026-10-27 [--expect-dropped N] [--expect-kept-title SUBSTR ...]` — run_date 마다: 그 사용자 실제 발송 PUBLISH·QUARANTINE 기사를 생존자로, 기사 페이지를 다시 받아 `_cited_keys` → `cited`, 그 run 이전 기록으로 `published_keys(url_index=)` → `drop_rereports`(실제 판정자) → 판정한 쌍·제외 목록 출력. 기대값과 다르면 종료코드 1. 프로덕션 DDB·Bedrock 은 읽기/호출만.

- [ ] **Step 1: 스크립트 작성**
- [ ] **Step 2: 머지 게이트 실행** — Run: `uv run python scripts/dedup_audit/rereport_replay.py --user-prefix 445814b8 --since 2026-10-21 --until 2026-10-27 --expect-dropped 10 --expect-kept-title gitai --expect-kept-title "AAIF에 Agent Skills"`
  Expected: 판정한 쌍 12 · 제외 10(The Decoder 6 + PyTorch Korea 4 — spec §2.2 목록) · gitai·AAIF 묶음 유지 · `PASS`.
  실제(2026-10-28): 판정 **13** · 제외 10 · PASS — 13번째 = Google AI "AI Quest" ← Google Research connectomics(유지 — 실험 목록에 없던 쌍. 실험은 PUBLISH 만·다른 언어 경로 정규화를 썼다, 정확한 원인은 미확인).
  다르면 머지하지 않는다 — 판정자는 temperature 를 못 고정하므로, 1건 차이는 같은 명령 1회 재실행 후 같은 쌍이 또 갈리면 프롬프트를 의심한다.
- [ ] **Step 3: 커밋** — `feat(scripts): 재보도 재생 게이트 — 7 run 실데이터로 제외 10·유지 2 확인`

---

### Task 7: 출하 (Step 2 부터 사용자 확인 후)

- [ ] **Step 1: 최종 검증** — `uv run pytest -q && uv run ruff check src tests scripts` + Task 6 게이트 PASS
- [ ] **Step 2: main 머지·push** (사용자 확인) — `git switch main && git pull --ff-only && git merge --ff-only feat/cited-rereport-dedup && git push origin main`
- [ ] **Step 3: 배포** (사용자 확인) — `uv run python -m briefing.runtime.deploy_runtime` → READY·ARN 불변. 새 env 없음. `deploy_scheduler` 실행 금지(dry-run 리셋 함정).
- [ ] **Step 4: 사후 관측** — 첫 run 뒤 CloudWatch `pipeline rereport` 라인 확인(제외 건의 B ← A 와 reason 이 맞는지), 1주 반복. 잘못 빠진 다른 주제 글이 보이면 `REREPORT_SYSTEM` 조정.
- [ ] **Step 5: 문서** — `docs/deliveries/<배포일>-cited-rereport-dedup-delivery.md` · `docs/README.md` 상태 SHIPPED·LIVE · `design/architecture/system-map.md` §3 dedup 줄에 재보도 단계 추가.
