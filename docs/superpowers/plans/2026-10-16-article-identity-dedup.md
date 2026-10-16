# 기사 신원 dedup — 구현 플랜 (Implementation Plan)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 같은 기사를 같은 사용자에게 두 번 보내지 않는다 — 원문이 고쳐져도(해시 변경), slug 가 바뀌어도(URL 변경), 문서 페이지가 "새 글"로 보여도.

**Architecture:** 3층 방어. ① 수집층: html 리스팅에서 canonical 호스트가 리스팅 호스트와 다른 링크를 버린다(`sources.py`). ② 신원층: dedup 키를 `source_id` 하나에서 **해시·URL·(매체, 제목) 3종**으로 넓히고, 과거 기사의 URL·제목은 ledger 의 `source_id` 로 **source-store 를 batch join** 해서 얻는다(`article_identity.py` + `get_meta`). ③ 기억층: lookback 7일 → **90일**(`DEDUP_LOOKBACK_DAYS`) + `DynamoLedger.query` pagination.

**Tech Stack:** Python 3.12 · boto3(DynamoDB `BatchGetItem`·`Query`) · trafilatura 2.1 · pytest · ruff · UV

**Spec:** `docs/superpowers/specs/2026-10-16-article-identity-dedup-design.md`

## Global Constraints

- 언어: 식별자·로그 메시지·CLI 는 영어, docstring·주석은 한국어(CLAUDE.md 언어 규칙).
- **dedup 의미론 3결정 유지(재론 금지):** PUBLISH 만 · strictly-earlier(`run_date < 오늘`) · `run_date` 빈값이면 off.
- lookback 기본 **90일**, env 키 `DEDUP_LOOKBACK_DAYS`, 기본값의 단일 소유자 = `core/config.py`(`.env.example` 은 주석 카탈로그 — `tests/test_config.py` 불변식이 동기화를 강제).
- URL 키: scheme·`www.`·`#fragment`·끝 슬래시 제거, **호스트만 소문자**, **쿼리 유지**(AI Times `?idxno=` = 기사 ID), 경로 대소문자 유지.
- 제목 키: NFKC·소문자·`\W` 제거, 정규화 후 **15자 미만이면 키 없음**, **매체와 묶음**.
- **fail-open:** canonical 없음/상대경로/서브도메인 → 통과 · source-store 원본 없음 → 해시로만 비교 · BatchGet 미처리 잔여 → warn 후 진행.
- 관측: URL·제목 키로 막힌 건, canonical 로 버린 건, 메타 미해결 건은 `_debug.warn`(DEBUG 무관·CloudWatch 도달). 해시 일치(48h 겹침의 일상)는 기존대로 `dprint`.
- 테이블 스키마·CFN 무변경. 배포 = `deploy_runtime` 만.
- 문서에 테스트 개수를 적지 않는다(명령이 진실).
- 커밋 메시지 끝: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`

## Review Focus

1. **AI Times 처럼 쿼리가 기사 ID 인 URL** — 서로 다른 `idxno` 가 같은 키로 뭉치면 매일 기사가 사라진다 → Task 1 `test_url_key_keeps_query_article_id`.
2. **canonical 이 없거나 상대경로인 페이지** — 정상 글을 버리면 소스가 조용히 죽는다 → Task 5 `test_is_offsite_rules`(빈값·상대경로·서브도메인).
3. **BatchGet 스로틀(UnprocessedKeys 가 계속 남음)** — 브리핑이 멈추거나 죽으면 안 된다 → Task 2 `test_dynamo_get_meta_gives_up_after_rounds_and_warns`.
4. **잘못된 `DEDUP_LOOKBACK_DAYS`(0·음수·문자·빈값)** — 조용히 dedup 이 꺼지면 안 된다(시작 시 크래시) → Task 3 `test_dedup_lookback_days_rejects_non_positive`.
5. **"Release notes" 같은 짧은 일반 제목·다른 매체의 같은 제목** — 별개 기사를 막으면 안 된다 → Task 1 `test_title_key_short_generic_title_has_no_key`·`test_identity_keys_prefixes_and_media_scope`.

---

## 파일 구조

| 파일 | 책임 | Task |
|---|---|---|
| `src/briefing/core/article_identity.py` (신규) | 신원 키(`url_key`·`title_key`·`identity_keys`·`match_kind`) + 과거 발행 키 집합(`published_keys`) | 1, 4 |
| `src/briefing/core/stores/source_store.py` | `SourceMeta` + `SourceStore.get_meta` | 2 |
| `src/briefing/core/stores/dynamo.py` | `DynamoSourceStore.get_meta`(BatchGet) + `DynamoLedger.query` pagination | 2 |
| `src/briefing/core/config.py` · `.env.example` · `runtime/deploy_runtime.py` · `.env`(로컬, 미커밋) | `dedup_lookback_days` 설정·카탈로그·컨테이너 주입 | 3 |
| `src/briefing/core/pipeline.py` | dedup 블록 교체(키 3종·90일·run 메모·warn) | 4 |
| `src/briefing/core/retrieval/sources.py` | canonical 호스트 검사(`_is_offsite`), `_extract_body` 4-tuple | 5 |
| `scripts/dedup_audit/replay.py` (신규) | 재생 게이트(replay) + 배포 후 관측(audit) — 프로덕션 읽기 전용 | 6 |
| `tests/test_article_identity.py` (신규) · `tests/test_store_meta.py` (신규) · `tests/test_config.py` · `tests/test_runtime.py` · `tests/test_pipeline.py` · `tests/test_sources.py` · `tests/test_dynamo.py` | 각 Task 의 테스트 | 1–5 |

---

### Task 1: 기사 신원 키 모듈

**Files:**
- Create: `src/briefing/core/article_identity.py`
- Test: `tests/test_article_identity.py`

**Interfaces:**
- Consumes: 없음
- Produces:
  - `MIN_TITLE_KEY_CHARS: int = 15`
  - `url_key(url: str) -> str` — 키 없으면 `""`
  - `title_key(title: str) -> str` — 키 없으면 `""`
  - `identity_keys(*, source_id: str, url: str, title: str, media: str) -> frozenset[str]` — 원소는 `"sid:<id>"`·`"url:<key>"`·`"title:<media 소문자>|<key>"`
  - `match_kind(candidate: Iterable[str], seen: Collection[str]) -> str` — `"sid"`|`"url"`|`"title"`|`""`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_article_identity.py`:

```python
"""article_identity — 기사 신원 키(해시·URL·매체+제목). 2026-10 중복 발송 감사의 실제 사례로 고정한다."""
from briefing.core.article_identity import identity_keys, match_kind, title_key, url_key

_MLDRIFT = "ML Drift: Next-Gen GPU AI/ML Inference at the Edge"
_AWSKR = "Strands Agents와 Amazon Bedrock AgentCore을 이용한 발전설비진단 구현하기"


def test_url_key_strips_scheme_www_fragment_trailing_slash():
    assert url_key("https://www.Anthropic.com/news/foo/#top") == "anthropic.com/news/foo"
    assert url_key("http://anthropic.com/news/foo") == "anthropic.com/news/foo"


def test_url_key_keeps_query_article_id():
    """AI Times 는 쿼리 idxno 가 기사 ID — 지우면 전 기사가 한 키로 뭉친다(감사 함정)."""
    a = url_key("https://www.aitimes.com/news/articleView.html?idxno=216103")
    b = url_key("https://www.aitimes.com/news/articleView.html?idxno=216105")
    assert a == "aitimes.com/news/articleView.html?idxno=216103"
    assert a != b


def test_url_key_keeps_path_case():
    k = url_key("https://www.anthropic.com/engineering/AI-resistant-technical-evaluations")
    assert k.endswith("/AI-resistant-technical-evaluations")


def test_url_key_empty_or_relative_is_no_key():
    assert url_key("") == ""
    assert url_key("/news/foo") == ""
    assert url_key("u1") == ""


def test_title_key_normalizes_case_space_punct():
    assert title_key(_MLDRIFT) == title_key("ml drift — next gen gpu ai ml inference at the edge")


def test_title_key_short_generic_title_has_no_key():
    assert title_key("Release notes") == ""
    assert title_key("제목") == ""


def test_title_key_korean():
    assert title_key(_AWSKR) != ""
    assert title_key(_AWSKR) == title_key(_AWSKR.replace(" ", "  "))


def test_identity_keys_prefixes_and_media_scope():
    k = identity_keys(source_id="abc", url="https://x.com/a", title="A long enough article title", media="X Blog")
    assert {s.split(":", 1)[0] for s in k} == {"sid", "url", "title"}
    other = identity_keys(source_id="def", url="https://y.com/b", title="A long enough article title", media="Y Blog")
    assert match_kind(other, k) == ""          # 다른 매체의 같은 제목은 별개 기사


def test_match_kind_url_when_hash_differs():
    """ML Drift(10-08→10-09): 원문 한 문단 수정 → 새 해시, URL 은 같다."""
    prior = identity_keys(source_id="7a8e72", url="https://developers.googleblog.com/ml-drift/",
                          title=_MLDRIFT, media="Google Developers Blog")
    today = identity_keys(source_id="974be6", url="https://developers.googleblog.com/ml-drift",
                          title=_MLDRIFT, media="Google Developers Blog")
    assert match_kind(today, prior) == "url"


def test_match_kind_title_when_slug_changes():
    """AWS KR(09-22→09-23): slug 오타 수정(arae→narae) → URL·해시 둘 다 변경, 제목만 같다."""
    prior = identity_keys(source_id="af78", url="https://aws.amazon.com/ko/blogs/tech/arae-energy/",
                          title=_AWSKR, media="AWS Korea Tech Blog")
    today = identity_keys(source_id="d58a", url="https://aws.amazon.com/ko/blogs/tech/narae-energy/",
                          title=_AWSKR, media="AWS Korea Tech Blog")
    assert match_kind(today, prior) == "title"


def test_match_kind_reports_sid_first():
    k = identity_keys(source_id="s1", url="https://x.com/a", title="A long enough article title", media="X")
    assert match_kind(k, k) == "sid"
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_article_identity.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'briefing.core.article_identity'`

- [ ] **Step 3: 구현**

`src/briefing/core/article_identity.py`:

```python
"""article_identity — "같은 기사인가?"를 판단하는 신원 키(identity key). cross-day 발행 dedup 이 쓴다.

★ source_id(본문 해시)는 "같은 바이트인가"이지 "같은 기사인가"가 아니다 — 원문이 한 문단만 고쳐져도
  새 해시가 된다(2026-10 감사: ML Drift·midterms 등 8기사·45장 중복 발송). 그래서 기사 신원을 키 3종으로 본다:
  - sid:   본문 해시(기존) — 같은 바이트 재등장
  - url:   정규화 URL — 원문 수정(해시 변경)에도 불변
  - title: (매체, 정규화 제목) — slug 변경(URL 변경)에도 불변. 짧은 일반 제목은 키 없음(오탐 방지)
설계: docs/superpowers/specs/2026-10-16-article-identity-dedup-design.md
"""
from __future__ import annotations

import re
import unicodedata
from collections.abc import Collection, Iterable
from urllib.parse import urlparse

MIN_TITLE_KEY_CHARS = 15  # 정규화 후 이보다 짧은 제목은 키 없음 — "Release notes" 류 일반 제목 오탐 방지

_NON_WORD = re.compile(r"\W+")


def url_key(url: str) -> str:
    """URL → 신원 키. scheme·`www.`·fragment·끝 슬래시 제거, 호스트만 소문자.

    ★ 쿼리는 유지한다 — AI Times 는 `articleView.html?idxno=216103` 의 `idxno` 가 기사 ID 다
      (쿼리를 지우면 전 기사가 한 키로 뭉친다 — 2026-10 감사에서 실측된 함정). 경로 대소문자도 유지.
    호스트가 없으면(상대 경로·빈값) "" — 키 없음.
    """
    p = urlparse((url or "").strip())
    host = (p.hostname or "").lower()
    if not host:
        return ""
    if host.startswith("www."):
        host = host[4:]
    query = f"?{p.query}" if p.query else ""
    return f"{host}{p.path.rstrip('/')}{query}"


def title_key(title: str) -> str:
    """제목 → 정규화 키(NFKC·소문자·기호/공백 제거). MIN_TITLE_KEY_CHARS 미만이면 "" — 키 없음."""
    norm = _NON_WORD.sub("", unicodedata.normalize("NFKC", title or "").lower())
    return norm if len(norm) >= MIN_TITLE_KEY_CHARS else ""


def identity_keys(*, source_id: str, url: str, title: str, media: str) -> frozenset[str]:
    """한 기사의 신원 키 집합(접두사로 종류 구분). 제목 키는 매체와 묶는다 — 다른 매체의 같은 제목은 별개."""
    keys: set[str] = {f"sid:{source_id}"} if source_id else set()
    if u := url_key(url):
        keys.add(f"url:{u}")
    if t := title_key(title):
        keys.add(f"title:{(media or '').strip().lower()}|{t}")
    return frozenset(keys)


def match_kind(candidate: Iterable[str], seen: Collection[str]) -> str:
    """candidate 키 중 seen 에 있는 것의 종류. sid → url → title 순으로 하나만 보고, 없으면 ""."""
    hits = {k.split(":", 1)[0] for k in candidate if k in seen}
    for kind in ("sid", "url", "title"):
        if kind in hits:
            return kind
    return ""
```

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest tests/test_article_identity.py -v && uv run ruff check src/briefing/core/article_identity.py tests/test_article_identity.py`
Expected: 전부 PASS, ruff `All checks passed!`

- [ ] **Step 5: 커밋**

```bash
git add src/briefing/core/article_identity.py tests/test_article_identity.py
git commit -m "$(cat <<'EOF'
feat(dedup): 기사 신원 키 모듈 — 해시·URL·(매체,제목) 3종

원문 수정(해시 변경)·slug 변경(URL 변경)에도 같은 기사를 알아본다.
URL 키는 쿼리 유지(AI Times idxno), 제목 키는 15자 미만이면 없음·매체 범위.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: 스토어 — `get_meta` 일괄 조회 + ledger pagination

**Files:**
- Modify: `src/briefing/core/stores/source_store.py` (`FrozenSource` 아래에 `SourceMeta`, `SourceStore` 끝에 `get_meta`)
- Modify: `src/briefing/core/stores/dynamo.py` (import, 상수, `DynamoLedger.query`, `DynamoSourceStore.get_meta`)
- Test: `tests/test_store_meta.py` (신규, 오프라인) · `tests/test_dynamo.py` (DynamoDB Local 가드 통합 1건 추가)

**Interfaces:**
- Consumes: 없음
- Produces:
  - `SourceMeta(url: str, title: str, media: str = "")` — frozen dataclass, `briefing.core.stores.source_store`
  - `SourceStore.get_meta(source_ids: Iterable[str]) -> dict[str, SourceMeta]` — 없는 id 는 결과에서 빠짐(예외 아님)
  - `DynamoSourceStore.get_meta(source_ids: Iterable[str]) -> dict[str, SourceMeta]` — 같은 계약
  - `DynamoLedger.query(user_id, since_date="")` — 반환 형태 불변, 모든 페이지를 읽음
  - `dynamo._BATCH_GET_MAX = 100`, `dynamo._BATCH_GET_ROUNDS = 5`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_store_meta.py`:

```python
"""get_meta(dedup 용 메타 일괄 조회) + DynamoLedger.query pagination — 오프라인(가짜 테이블, AWS 없음)."""
from types import SimpleNamespace

from briefing.core.stores.source_store import SourceMeta, SourceStore


def test_local_get_meta_returns_meta_and_skips_missing(tmp_path):
    store = SourceStore(str(tmp_path))
    fs = store.freeze(url="https://x.com/a", title="T", raw_text="본문", fetched_at="2026-10-01", media="X")
    got = store.get_meta([fs.source_id, "missing-id", fs.source_id])
    assert got == {fs.source_id: SourceMeta(url="https://x.com/a", title="T", media="X")}


class _FakeClient:
    """batch_get_item 응답을 순서대로 내주는 가짜 저수준 클라이언트."""

    def __init__(self, pages):
        self.pages, self.requests = list(pages), []

    def batch_get_item(self, RequestItems):  # noqa: N803 — boto3 인자명 그대로
        self.requests.append(RequestItems)
        return self.pages.pop(0)


def _dynamo_store(client):
    from briefing.core.stores.dynamo import DynamoSourceStore
    s = object.__new__(DynamoSourceStore)          # boto3 연결 없이 — _t 만 가짜로
    s._t = SimpleNamespace(name="tbl", meta=SimpleNamespace(client=client))
    return s


def _item(sid, url="https://x.com/a", title="T", media="X"):
    return {"source_id": {"S": sid}, "url": {"S": url}, "title": {"S": title}, "media": {"S": media}}


def test_dynamo_get_meta_batches_by_100_and_follows_unprocessed(monkeypatch):
    from briefing.core.stores import dynamo
    monkeypatch.setattr(dynamo.time, "sleep", lambda _s: None)
    ids = [f"s{i}" for i in range(150)]
    client = _FakeClient([
        {"Responses": {"tbl": [_item(f"s{i}") for i in range(99)]},
         "UnprocessedKeys": {"tbl": {"Keys": [{"source_id": {"S": "s99"}}]}}},
        {"Responses": {"tbl": [_item("s99")]}},
        {"Responses": {"tbl": [_item(f"s{i}") for i in range(100, 150)]}},
    ])
    got = _dynamo_store(client).get_meta(ids)
    assert len(got) == 150 and got["s99"] == SourceMeta(url="https://x.com/a", title="T", media="X")
    assert [len(r["tbl"]["Keys"]) for r in client.requests] == [100, 1, 50]
    assert client.requests[0]["tbl"]["ExpressionAttributeNames"]["#u"] == "url"   # url 은 예약어 → placeholder


def test_dynamo_get_meta_gives_up_after_rounds_and_warns(monkeypatch, capsys):
    from briefing.core.stores import dynamo
    monkeypatch.setattr(dynamo.time, "sleep", lambda _s: None)
    stuck = {"Responses": {"tbl": []}, "UnprocessedKeys": {"tbl": {"Keys": [{"source_id": {"S": "s0"}}]}}}
    client = _FakeClient([stuck] * dynamo._BATCH_GET_ROUNDS)
    assert _dynamo_store(client).get_meta(["s0"]) == {}          # 죽지 않고 미해결로 진행(fail-open)
    assert "미처리" in capsys.readouterr().err


def test_dynamo_ledger_query_follows_pages():
    from briefing.core.stores.dynamo import DynamoLedger
    calls = []

    def fake_query(**kw):
        calls.append(kw)
        if "ExclusiveStartKey" not in kw:
            return {"Items": [{"run_date": "2026-10-01", "user_id": "u", "source_id": "a", "decision": "PUBLISH"}],
                    "LastEvaluatedKey": {"user_id": "u", "sk": "2026-10-01#a"}}
        return {"Items": [{"run_date": "2026-10-02", "user_id": "u", "source_id": "b", "decision": "PUBLISH"}]}

    led = object.__new__(DynamoLedger)
    led._t = SimpleNamespace(query=fake_query)
    rows = led.query("u", since_date="2026-07-18")
    assert [r["source_id"] for r in rows] == ["a", "b"]           # 두 번째 페이지까지 읽음
    assert calls[1]["ExclusiveStartKey"] == {"user_id": "u", "sk": "2026-10-01#a"}
```

`tests/test_dynamo.py` 끝에 추가(DynamoDB Local 있을 때만 실행 — 기존 `pytestmark` 가드):

```python
def test_dynamo_source_get_meta(backends):
    _, _, store = backends
    from briefing.core.stores.source_store import SourceMeta
    fs = store.freeze(url="https://x.com/meta", title="메타 제목", raw_text="get_meta 통합 본문",
                      fetched_at="2026-10-01", media="X")
    assert store.get_meta([fs.source_id, "nope"]) == {fs.source_id: SourceMeta("https://x.com/meta", "메타 제목", "X")}
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_store_meta.py -v`
Expected: FAIL — `ImportError: cannot import name 'SourceMeta'`

- [ ] **Step 3: 구현 — `source_store.py`**

import 줄 추가(`from dataclasses import ...` 위):

```python
from collections.abc import Iterable
```

`FrozenSource` 클래스 바로 아래에 추가:

```python
@dataclass(frozen=True)
class SourceMeta:
    """dedup 이 쓰는 기사 메타(원문 제외) — get_meta 반환값. 원문(text)을 안 읽어 일괄 조회가 가볍다."""
    url: str
    title: str
    media: str = ""
```

`SourceStore` 클래스 끝(`get_source` 아래)에 추가:

```python
    def get_meta(self, source_ids: Iterable[str]) -> dict[str, SourceMeta]:
        """여러 source_id 의 메타(url·title·media)를 한 번에. 없는 id 는 결과에서 빠진다(예외 아님).

        ★ get_source 와 달리 미스가 정상이다 — 2026-08-01(`305ed18`) 이전 동결본은 7일 TTL 로 만료돼
          ledger 포인터가 dangling 일 수 있다(07-24 이전 행의 72%). 호출자(dedup)가 미스를 해시 비교로 fail-open.
        """
        out: dict[str, SourceMeta] = {}
        for sid in dict.fromkeys(source_ids):
            p = self._path(sid)
            if p.exists():
                d = json.loads(p.read_text(encoding="utf-8"))
                out[sid] = SourceMeta(url=d.get("url", ""), title=d.get("title", ""), media=d.get("media", ""))
        return out
```

- [ ] **Step 4: 구현 — `dynamo.py`**

import 블록 교체:

```python
import json
import time
from collections.abc import Iterable
from dataclasses import asdict

import boto3
from boto3.dynamodb.conditions import Key
from boto3.dynamodb.types import TypeDeserializer
from botocore.exceptions import ClientError

from .. import _debug
from .cache import _deserialize, _serialize
from .source_store import FrozenSource, SourceMeta, content_id, media_from_url, normalize
```

`_CACHE_TTL_DAYS = 30` 아래에 상수 추가:

```python
_BATCH_GET_MAX = 100     # BatchGetItem 한 번의 키 상한(AWS 고정값)
_BATCH_GET_ROUNDS = 5    # UnprocessedKeys(스로틀) 재시도 상한 — 넘으면 남은 id 는 미해결(dedup 은 해시로만 비교)
```

`DynamoLedger.query` 를 통째로 교체:

```python
    def query(self, user_id: str, since_date: str = "") -> list[dict]:
        cond = Key("user_id").eq(user_id)
        if since_date:
            cond = cond & Key("sk").gte(since_date)  # "2026-06-20" <= "2026-06-20#…" 이라 날짜 prefix 로 그날 이후를 range 질의
        kw: dict = {"KeyConditionExpression": cond}
        items: list[dict] = []
        while True:  # ★ 페이지 끝까지 — 첫 페이지(1MB)만 읽으면 조용히 잘린다(90일 lookback ≈ 사용자당 0.5MB, 2026-10)
            resp = self._t.query(**kw)
            items.extend(resp.get("Items", []))
            if "LastEvaluatedKey" not in resp:
                break
            kw["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
        return [{
            "run_date": it.get("run_date", ""), "user_id": it.get("user_id", ""),
            "source_id": it.get("source_id", ""), "card_key": it.get("card_key", ""),
            "decision": it.get("decision", ""), "headline": it.get("headline", ""),
        } for it in items]
```

`DynamoSourceStore` 끝(`get_source` 아래)에 추가:

```python
    def get_meta(self, source_ids: Iterable[str]) -> dict[str, SourceMeta]:
        """BatchGetItem 100개씩 — url·title·media 만 투영(원문 제외). 없는 id 는 빠진다(SourceStore.get_meta 파리티).

        UnprocessedKeys(스로틀)는 짧은 backoff 로 최대 _BATCH_GET_ROUNDS 회 재시도, 그래도 남으면 warn 후 미해결로 둔다
        — dedup 은 미해결을 해시 비교로 fail-open 처리하므로 브리핑을 막지 않는다.
        """
        ids = list(dict.fromkeys(source_ids))
        client, name, td = self._t.meta.client, self._t.name, TypeDeserializer()
        out: dict[str, SourceMeta] = {}
        for i in range(0, len(ids), _BATCH_GET_MAX):
            req: dict = {name: {
                "Keys": [{"source_id": {"S": s}} for s in ids[i:i + _BATCH_GET_MAX]],
                "ProjectionExpression": "#s, #u, #t, #m",   # url 등 예약어 회피 — 전부 placeholder
                "ExpressionAttributeNames": {"#s": "source_id", "#u": "url", "#t": "title", "#m": "media"},
            }}
            for attempt in range(_BATCH_GET_ROUNDS):
                resp = client.batch_get_item(RequestItems=req)
                for raw in resp.get("Responses", {}).get(name, []):
                    it = {k: td.deserialize(v) for k, v in raw.items()}
                    out[it["source_id"]] = SourceMeta(url=it.get("url", ""), title=it.get("title", ""),
                                                      media=it.get("media", ""))
                req = resp.get("UnprocessedKeys") or {}
                if not req:
                    break
                time.sleep(0.05 * 2 ** attempt)
            else:
                left = len(req.get(name, {}).get("Keys", []))
                _debug.warn("source meta", f"BatchGet 미처리 {left}건 — 미해결로 진행(dedup 은 해시로만 비교)")
        return out
```

- [ ] **Step 5: 통과 확인**

Run: `uv run pytest tests/test_store_meta.py tests/test_ledger.py tests/test_source_store.py tests/test_backends.py -v && uv run ruff check src tests`
Expected: 전부 PASS(`test_dynamo.py` 는 DDB Local 없으면 skip), ruff `All checks passed!`

- [ ] **Step 6: 커밋**

```bash
git add src/briefing/core/stores/source_store.py src/briefing/core/stores/dynamo.py tests/test_store_meta.py tests/test_dynamo.py
git commit -m "$(cat <<'EOF'
feat(store): get_meta 일괄 메타 조회 + DynamoLedger.query pagination

dedup 이 과거 source_id 의 url·title·media 를 source-store 에서 join 하도록
BatchGetItem(100개씩·원문 제외·스로틀 재시도 후 fail-open). ledger 조회는
1MB 첫 페이지에서 조용히 잘리던 것을 LastEvaluatedKey 루프로.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: 설정 — `DEDUP_LOOKBACK_DAYS` (기본 90)

**Files:**
- Modify: `src/briefing/core/config.py` (상수·`Settings` 끝 필드·`_positive_int`·`load_settings`)
- Modify: `.env.example` (스토어 섹션에 주석 카탈로그 1줄)
- Modify: `src/briefing/runtime/deploy_runtime.py` (`runtime_env` 에 forward)
- Modify(로컬·미커밋): `.env` (활성 라인 — 사용자 env-first 운영)
- Test: `tests/test_config.py` · `tests/test_runtime.py`

**Interfaces:**
- Consumes: 없음
- Produces:
  - `config.DEFAULT_DEDUP_LOOKBACK_DAYS = 90`
  - `Settings.dedup_lookback_days: int = 90` (마지막 필드, 기본값 있음 → 기존 keyword 생성자 무변경)
  - 컨테이너 env `DEDUP_LOOKBACK_DAYS` (문자열)

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_config.py` 끝에 추가:

```python
def test_dedup_lookback_days_default_and_override(monkeypatch):
    monkeypatch.delenv("DEDUP_LOOKBACK_DAYS", raising=False)
    assert load_settings().dedup_lookback_days == 90
    monkeypatch.setenv("DEDUP_LOOKBACK_DAYS", "30")
    assert load_settings().dedup_lookback_days == 30


@pytest.mark.parametrize("bad", ["0", "-5", "abc", ""])
def test_dedup_lookback_days_rejects_non_positive(monkeypatch, bad):
    """오설정이 dedup 을 조용히 끄면 안 된다 — 시작 시 크래시(catalog 로더와 같은 원칙)."""
    monkeypatch.setenv("DEDUP_LOOKBACK_DAYS", bad)
    with pytest.raises(ValueError, match="DEDUP_LOOKBACK_DAYS"):
        load_settings()
```

`tests/test_runtime.py` 의 runtime_env 테스트들 아래에 추가:

```python
def test_runtime_env_forwards_dedup_lookback(tmp_path):
    from briefing.runtime.deploy_runtime import runtime_env
    assert runtime_env(_settings(tmp_path, dedup_lookback_days=45))["DEDUP_LOOKBACK_DAYS"] == "45"
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_config.py tests/test_runtime.py -v -k "dedup"`
Expected: FAIL — `AttributeError: 'Settings' object has no attribute 'dedup_lookback_days'` / `TypeError: ... unexpected keyword argument 'dedup_lookback_days'`

- [ ] **Step 3: 구현 — `config.py`**

`@dataclass(frozen=True) class Settings` 바로 위에 추가:

```python
DEFAULT_DEDUP_LOOKBACK_DAYS = 90  # 발행 dedup 이 돌아보는 기간(일) — 최장 관측 재등장 43일(2026-10 감사)의 ~2배
```

`Settings` 의 마지막 필드(`oauth_provider_name`) 아래에 추가:

```python
    # ── 발행 dedup(2026-10-16) — 같은 기사를 이 기간 안에 다시 보내지 않는다. 기본값이 있어 기존 생성자 무변경 ──
    dedup_lookback_days: int = DEFAULT_DEDUP_LOOKBACK_DAYS
```

`load_settings` 위에 헬퍼 추가:

```python
def _positive_int(raw: str, name: str) -> int:
    """양의 정수 env 파싱 — 아니면 시작 시 크래시(silent 오설정 금지; catalog 로더와 같은 원칙)."""
    try:
        v = int(raw.strip())
    except ValueError:
        raise ValueError(f"{name} 는 양의 정수여야 함 (got {raw!r})") from None
    if v < 1:
        raise ValueError(f"{name} 는 양의 정수여야 함 (got {raw!r})")
    return v
```

`load_settings()` 의 `Settings(...)` 호출 마지막 인자(`oauth_provider_name=...`) 아래에 추가:

```python
        dedup_lookback_days=_positive_int(g("DEDUP_LOOKBACK_DAYS", str(DEFAULT_DEDUP_LOOKBACK_DAYS)),
                                          "DEDUP_LOOKBACK_DAYS"),
```

- [ ] **Step 4: 구현 — `.env.example` · `runtime_env` · `.env`**

`.env.example` 의 `# DDB_ENDPOINT_URL=...` 줄 바로 아래에 추가:

```
# DEDUP_LOOKBACK_DAYS=90                    # 발행 dedup 이 돌아보는 기간(일) — 이 기간 안에 보낸 기사는 다시 안 보냄(최장 관측 재등장 43일)
```

`src/briefing/runtime/deploy_runtime.py` `runtime_env` 의 반환 dict 에서 `"BACKEND": "dynamo",` 줄 아래에 추가:

```python
        "DEDUP_LOOKBACK_DAYS": str(settings.dedup_lookback_days),  # 발행 dedup 기간 — .env 값이 컨테이너로(컨테이너는 .env 미독)
```

`.env`(로컬, gitignore — 커밋 안 함)의 모델 설정 블록 아래에 추가:

```
# ── 발행 dedup (2026-10-16) — 같은 기사를 이 기간(일) 안에 다시 보내지 않는다. 프로덕션 반영 = deploy_runtime 때 ──
DEDUP_LOOKBACK_DAYS=90
```

- [ ] **Step 5: 통과 확인**

Run: `uv run pytest tests/test_config.py tests/test_runtime.py tests/test_relevance.py -v && uv run ruff check src tests`
Expected: 전부 PASS(`test_env_example_documents_all_settings_keys` 포함), ruff `All checks passed!`

- [ ] **Step 6: 커밋**

```bash
git add src/briefing/core/config.py .env.example src/briefing/runtime/deploy_runtime.py tests/test_config.py tests/test_runtime.py
git commit -m "$(cat <<'EOF'
feat(config): DEDUP_LOOKBACK_DAYS(기본 90) — 발행 dedup 기간 설정

양의 정수가 아니면 시작 시 크래시(조용히 dedup 이 꺼지지 않게).
.env.example 카탈로그 + runtime_env 로 컨테이너에 주입.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: 파이프라인 — 신원 키 dedup (source-store join · 90일 · run 메모)

**Files:**
- Modify: `src/briefing/core/article_identity.py` (`published_keys` 추가)
- Modify: `src/briefing/core/pipeline.py` (import, dedup 블록, 메모, 미해결 warn)
- Test: `tests/test_pipeline.py` (dedup 섹션에 추가 — 기존 dedup 3테스트는 그대로 통과해야 함)

**Interfaces:**
- Consumes:
  - Task 1: `identity_keys(...)`, `match_kind(...)`
  - Task 2: `store.get_meta(ids) -> dict[str, SourceMeta]`, `SourceMeta(url, title, media)`, `ledger.query(user_id, since_date)`(전 페이지)
  - Task 3: `config.DEFAULT_DEDUP_LOOKBACK_DAYS`, `settings.dedup_lookback_days`
- Produces:
  - `published_keys(ledger, store, user_id: str, run_date: str, lookback_days: int, memo: dict[str, SourceMeta | None]) -> frozenset[str]`
  - warn 라벨 `"pipeline dedup"` — 본문 `"<user>: <kind> 키 일치 — 이전 발행 기사 제외: <제목>"` / `"source-store 에 원본 없는 이전 발행 <N>건 — 해시로만 비교(fail-open)"`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_pipeline.py` 의 `test_run_briefing_quarantined_retries_next_day` 아래(2층화 섹션 위)에 추가:

```python
# ── 기사 신원 dedup (2026-10-16 — 해시·URL·제목 키 + source-store join + 90일) ──


def _fetch_one(url, title, text):
    """고정된 기사 1건을 내주는 fetch fake — 날마다 본문/URL 을 바꿔 원문 수정·slug 변경을 재현한다."""
    def f(source, _w):
        return [FetchedArticle(source.key, url, title, text, "2026-10-08T00:00:00Z")]
    return f


def _kw(fetch, verdict="VERIFIED"):
    kw = _dedup_kw(verdict)
    kw["fetch_article_fn"] = fetch
    return kw


_MLDRIFT_URL = "https://developers.googleblog.com/ml-drift-next-gen-gpu-aiml-inference-at-the-edge/"
_MLDRIFT = "ML Drift: Next-Gen GPU AI/ML Inference at the Edge"
_AWSKR = "Strands Agents와 Amazon Bedrock AgentCore을 이용한 발전설비진단 구현하기"


def test_dedup_catches_edited_article_by_url(tmp_path, capsys):
    """원문이 고쳐져 해시가 바뀌어도 URL 이 같으면 다음날 제외 — ML Drift(10-08→10-09) 재현."""
    from briefing.core.stores.ledger import LocalLedger

    store, ledger = SourceStore(str(tmp_path / "store")), LocalLedger(str(tmp_path / "led"))
    users = [_user("u", ["aws-ml"])]
    d1 = run_briefing(SimpleNamespace(), store, users, ledger=ledger, run_date="2026-10-08",
                      **_kw(_fetch_one(_MLDRIFT_URL, _MLDRIFT, "원문 v1. 직원 약 100명.")))
    d2 = run_briefing(SimpleNamespace(), store, users, ledger=ledger, run_date="2026-10-09",
                      **_kw(_fetch_one(_MLDRIFT_URL, _MLDRIFT, "원문 v2(한 문단 수정). 직원 약 100명.")))
    assert d1[0].published == 1 and d2[0].published == 0
    assert "url 키 일치" in capsys.readouterr().err


def test_dedup_catches_slug_change_by_title(tmp_path, capsys):
    """slug 오타 수정으로 URL·해시가 둘 다 바뀌어도 같은 매체·같은 제목이면 제외 — AWS KR(09-22→09-23) 재현."""
    from briefing.core.stores.ledger import LocalLedger

    store, ledger = SourceStore(str(tmp_path / "store")), LocalLedger(str(tmp_path / "led"))
    users = [_user("u", ["aws-ml"])]
    run_briefing(SimpleNamespace(), store, users, ledger=ledger, run_date="2026-09-22",
                 **_kw(_fetch_one("https://aws.amazon.com/ko/blogs/tech/arae-energy/", _AWSKR, "arae 본문. 직원 약 100명.")))
    d2 = run_briefing(SimpleNamespace(), store, users, ledger=ledger, run_date="2026-09-23",
                      **_kw(_fetch_one("https://aws.amazon.com/ko/blogs/tech/narae-energy/", _AWSKR, "narae 본문. 직원 약 100명.")))
    assert d2[0].published == 0
    assert "title 키 일치" in capsys.readouterr().err


def test_dedup_lookback_boundary(tmp_path):
    """정확히 lookback 일 전 발행은 막고, 그 하루 뒤에는 다시 보낸다(창 밖)."""
    from briefing.core.stores.ledger import LocalLedger

    store, ledger = SourceStore(str(tmp_path / "store")), LocalLedger(str(tmp_path / "led"))
    users = [_user("u", ["aws-ml"])]
    s = SimpleNamespace(dedup_lookback_days=90)
    assert run_briefing(s, store, users, ledger=ledger, run_date="2026-07-18", **_dedup_kw())[0].published == 1
    assert run_briefing(s, store, users, ledger=ledger, run_date="2026-10-16", **_dedup_kw())[0].published == 0  # 90일 전 = 포함
    assert run_briefing(s, store, users, ledger=ledger, run_date="2026-10-17", **_dedup_kw())[0].published == 1  # 91일 전 = 창 밖


def test_dedup_meta_missing_falls_back_to_hash(tmp_path, capsys):
    """source-store 에 원본이 없는 과거 발행(2026-08-01 이전 TTL 만료분)은 해시로만 비교 — fail-open."""
    from briefing.core.stores.ledger import LocalLedger

    store, ledger = SourceStore(str(tmp_path / "store")), LocalLedger(str(tmp_path / "led"))
    users = [_user("u", ["aws-ml"])]
    ledger.append("2026-10-08", "u", "gone-sid", "k", "PUBLISH", "H")     # 원본 없는(dangling) 포인터
    d = run_briefing(SimpleNamespace(), store, users, ledger=ledger, run_date="2026-10-09",
                     **_kw(_fetch_one(_MLDRIFT_URL, _MLDRIFT, "원문. 직원 약 100명.")))
    assert d[0].published == 1                                            # 막을 근거가 없으면 막지 않는다
    assert "원본 없는 이전 발행 1건" in capsys.readouterr().err


class _CountingStore(SourceStore):
    """get_meta 호출을 세는 store — run 메모(사용자 간 공유)가 재조회를 막는지 확인."""

    def __init__(self, root):
        super().__init__(root)
        self.meta_calls: list[list[str]] = []

    def get_meta(self, source_ids):
        ids = list(source_ids)
        self.meta_calls.append(ids)
        return super().get_meta(ids)


def test_dedup_meta_join_shared_across_users(tmp_path):
    """같은 기사를 받은 두 번째 사용자는 source-store 를 다시 읽지 않는다(run 메모)."""
    from briefing.core.stores.ledger import LocalLedger

    store, ledger = _CountingStore(str(tmp_path / "store")), LocalLedger(str(tmp_path / "led"))
    users = [_user("a", ["aws-ml"]), _user("b", ["aws-ml"])]
    run_briefing(SimpleNamespace(), store, users, ledger=ledger, run_date="2026-10-08",
                 **_kw(_fetch_one(_MLDRIFT_URL, _MLDRIFT, "원문 v1. 직원 약 100명.")))
    store.meta_calls.clear()
    d2 = run_briefing(SimpleNamespace(), store, users, ledger=ledger, run_date="2026-10-09",
                      **_kw(_fetch_one(_MLDRIFT_URL, _MLDRIFT, "원문 v2. 직원 약 100명.")))
    assert [b.published for b in d2] == [0, 0]
    assert len(store.meta_calls) == 1                     # 첫 사용자만 조회, 두 번째는 메모 히트
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_pipeline.py -v -k "dedup"`
Expected: 새 5개 FAIL(예: `test_dedup_catches_edited_article_by_url` 에서 `d2[0].published == 1` — 해시만 비교하므로 통과됨), 기존 3개 PASS

- [ ] **Step 3: 구현 — `article_identity.py` 에 `published_keys` 추가**

import 블록에 추가:

```python
from datetime import date, timedelta
from typing import Any

from .stores.source_store import SourceMeta
```

파일 끝에 추가:

```python
def published_keys(ledger: Any, store: Any, user_id: str, run_date: str, lookback_days: int,
                   memo: dict[str, SourceMeta | None]) -> frozenset[str]:
    """user 가 run_date 이전 lookback_days 안에 PUBLISH 로 받은 기사들의 신원 키 합집합.

    의미론(선행 설계 2026-07-11, 재론 금지): PUBLISH 만(QUARANTINE 은 재도전) · strictly-earlier(run_date 미만 —
    같은 날 재실행 = 강제 재발송 런북 보존). 경계: 정확히 lookback_days 일 전은 포함(sk >= since).
    memo = run 동안 사용자 간 공유하는 {source_id: SourceMeta | None} — 같은 기사를 받은 두 번째 사용자부터는
    source-store 를 다시 읽지 않는다. None = 원본 없음(2026-08-01 이전 TTL 만료분) → 해시 키만(fail-open).
    ledger: `query(user_id, since_date)` · store: `get_meta(ids)` 를 가진 객체(Local·Dynamo 공통).
    """
    try:
        since = (date.fromisoformat(run_date) - timedelta(days=lookback_days)).isoformat()
    except ValueError:
        since = ""  # 형식 밖 run_date — 전체 조회(기존 동작 유지)
    ids = {r["source_id"] for r in ledger.query(user_id, since_date=since)
           if r.get("decision") == "PUBLISH" and r.get("run_date", "") < run_date}
    missing = [i for i in ids if i not in memo]
    if missing:
        found = store.get_meta(missing)
        for i in missing:
            memo[i] = found.get(i)
    keys: set[str] = set()
    for i in ids:
        m = memo[i]
        if m is None:
            keys.add(f"sid:{i}")
        else:
            keys |= identity_keys(source_id=i, url=m.url, title=m.title, media=m.media)
    return frozenset(keys)
```

- [ ] **Step 4: 구현 — `pipeline.py`**

import 교체: `from datetime import date, timedelta` 줄을 **삭제**하고(이 블록 외 사용처 없음), 아래처럼 바꾼다:

```python
from . import _debug, render
from .article_identity import identity_keys, match_kind, published_keys
from .retrieval import sources as src
from .authoring.author import INTERP_PROMPT_VERSION, PROMPT_VERSION
from .stores.cache import CardCache, fact_card_key, interp_card_key
from .config import DEFAULT_DEDUP_LOOKBACK_DAYS, Settings, UserConfig
```

`today = render.format_briefing_date(run_date)` 줄 바로 아래(`for u in users:` 위)에 추가:

```python
    lookback_days = getattr(settings, "dedup_lookback_days", DEFAULT_DEDUP_LOOKBACK_DAYS)
    meta_memo: dict = {}   # source_id → SourceMeta | None — run 동안 사용자 간 공유(dedup join 은 사실상 run당 1회)
```

`# ★ cross-day 발행 dedup — ...` 주석 4줄부터 `prior_published = {...}` 까지(현재 `prior_published` 계산 블록 전체)를 다음으로 교체:

```python
        # ★ cross-day 발행 dedup — "사용자당 기사 1회". 신원 = 해시·URL·(매체,제목) 키 3종(article_identity):
        #   원문 수정(해시 변경)·slug 변경(URL 변경)에도 같은 기사로 본다. 과거 기사 메타는 source-store join.
        #   의미론 3결정(PUBLISH 만 · strictly-earlier · run_date 빈값이면 off)은 published_keys 가 보존.
        seen: frozenset[str] = frozenset()
        if ledger is not None and run_date:
            seen = published_keys(ledger, store, u.id, run_date, lookback_days, meta_memo)
```

루프 안의

```python
            if fs.source_id in prior_published:
                deduped += 1
                continue
```

를 다음으로 교체:

```python
            kind = match_kind(identity_keys(source_id=fs.source_id, url=fs.url, title=fs.title, media=fs.media),
                              seen) if seen else ""
            if kind:
                deduped += 1
                if kind != "sid":  # 새 신원 키로 막힌 건 항상 warn — 오탐이 있으면 여기서 보인다(해시 일치는 48h 겹침의 일상)
                    _debug.warn("pipeline dedup", f"{u.id}: {kind} 키 일치 — 이전 발행 기사 제외: {fs.title[:50]}")
                continue
```

함수 끝의 `return out` 바로 위에 추가:

```python
    unresolved = sum(1 for m in meta_memo.values() if m is None)
    if unresolved:  # 07-24 이전 행(TTL 만료분)이 90일 창을 벗어나면 0 으로 수렴 — 다시 늘면 source-store 이상 신호
        _debug.warn("pipeline dedup", f"source-store 에 원본 없는 이전 발행 {unresolved}건 — 해시로만 비교(fail-open)")
```

- [ ] **Step 5: 통과 확인**

Run: `uv run pytest tests/test_pipeline.py tests/test_ledger.py tests/test_scheduler.py -v && uv run pytest -q && uv run ruff check src tests`
Expected: dedup 신·구 8개 포함 전부 PASS, 전체 스위트 실패 0, ruff `All checks passed!`

- [ ] **Step 6: 커밋**

```bash
git add src/briefing/core/article_identity.py src/briefing/core/pipeline.py tests/test_pipeline.py
git commit -m "$(cat <<'EOF'
feat(pipeline): 기사 신원 dedup — 해시·URL·제목 키 + source-store join + 90일

과거 PUBLISH 의 source_id 를 source-store 에서 일괄 join(run 메모로 사용자 간 공유)해
URL·(매체,제목) 키까지 비교. 원문 수정·slug 변경에도 같은 기사를 다시 보내지 않는다.
의미론 3결정 유지. 새 키로 막힌 건·원본 없는 과거 발행은 warn.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: 수집층 — canonical 호스트 검사 (문서 페이지 차단)

**Files:**
- Modify: `src/briefing/core/retrieval/sources.py` (`_extract_body` 4-tuple, `_fetch_feed` 호출부, `_host`·`_is_offsite` 신설, `_extract_article` 인자, `fetch_generic_html` 호출부)
- Test: `tests/test_sources.py` (기존 `test_extract_article_drops_stub` 의 lambda 2개를 4-tuple 로 수정 + 신규 4개)

**Interfaces:**
- Consumes: 없음(독립 Task)
- Produces:
  - `_extract_body(html_text) -> tuple[str, str, str, str]` = (title, body, date, canonical)
  - `_is_offsite(canonical: str, listing_url: str) -> bool`
  - `_extract_article(html_text, url, source_key, listing_url: str = "") -> FetchedArticle | None`
  - warn 라벨 `"fetch offsite"`

- [ ] **Step 1: 기존 테스트 수정 + 실패하는 테스트 작성**

`tests/test_sources.py` 의 `test_extract_article_drops_stub` 안 lambda 두 개를 4-tuple 로 바꾼다:

```python
        s._extract_body = lambda _h: ("T", "Enable JavaScript and cookies to continue", "", "")
```

```python
        s._extract_body = lambda _h: ("T", _ARTICLE, "", "")
```

같은 파일의 그 테스트 아래에 추가:

```python
# ── canonical 호스트 검사 — 블로그 리스팅의 *문서 페이지*를 새 글로 오인하지 않기(2026-10 감사: Best practices 28장) ──


def test_is_offsite_rules():
    from briefing.core.retrieval.sources import _is_offsite
    listing = "https://www.anthropic.com/engineering"
    assert _is_offsite("https://code.claude.com/docs/en/best-practices", listing) is True   # 실제 사례
    assert _is_offsite("https://www.anthropic.com/engineering/x", listing) is False         # 같은 호스트
    assert _is_offsite("https://anthropic.com/engineering/x", listing) is False             # www 무시
    assert _is_offsite("", listing) is False                                                # canonical 없음 → 통과
    assert _is_offsite("/engineering/x", listing) is False                                  # 상대경로 → 판단 불가 → 통과
    assert _is_offsite("https://x.com/a", "https://blog.x.com/") is False                   # 서브도메인 관계 → 통과
    assert _is_offsite("https://blog.x.com/a", "https://x.com/blog") is False


def test_extract_body_reads_canonical_link():
    html = _ARTICLE_HTML.replace(
        "<head>", '<head><link rel="canonical" href="https://code.claude.com/docs/en/best-practices">')
    from briefing.core.retrieval.sources import _extract_body
    assert _extract_body(html)[3] == "https://code.claude.com/docs/en/best-practices"
    assert _extract_body(_ARTICLE_HTML)[3] == ""                                            # canonical 없음 → ""


def test_extract_article_drops_offsite_canonical(capsys):
    from briefing.core.retrieval import sources as s
    orig = s._extract_body
    try:
        s._extract_body = lambda _h: ("Best practices", _ARTICLE, "2026-10-06",
                                      "https://code.claude.com/docs/en/best-practices")
        assert s._extract_article("<html/>", "https://www.anthropic.com/engineering/claude-code-best-practices",
                                  "anthropic-eng", "https://www.anthropic.com/engineering") is None
        assert "다른 호스트" in capsys.readouterr().err
        assert s._extract_article("<html/>", "https://x/a", "k") is not None   # listing_url 없으면 검사 안 함
    finally:
        s._extract_body = orig


def test_fetch_generic_html_skips_offsite_page(monkeypatch):
    """리스팅 링크가 다른 호스트의 문서로 넘어가면(canonical) 그 링크만 빠진다 — 정상 글은 그대로."""
    from briefing.core.retrieval import sources as s
    docs_page = _ARTICLE_HTML.replace(
        "<head>", '<head><link rel="canonical" href="https://code.claude.com/docs/en/best-practices">')
    pages = {"/news": '<a href="/news/opus">O</a><a href="/news/claude-code-best-practices">B</a>',
             "/news/opus": _ARTICLE_HTML, "/news/claude-code-best-practices": docs_page}
    monkeypatch.setattr(s, "discover_feed", lambda _u: "")
    monkeypatch.setattr(s, "_http_get", lambda u: pages[u.replace("https://www.anthropic.com", "")])
    arts = s.fetch_generic_html(_src(), window_hours=0, max_items=5)
    assert [a.url for a in arts] == ["https://www.anthropic.com/news/opus"]
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_sources.py -v`
Expected: 신규 4개 FAIL(`ImportError: cannot import name '_is_offsite'` 등), 수정한 `test_extract_article_drops_stub` 는 `ValueError: too many values to unpack` 로 FAIL

- [ ] **Step 3: 구현**

`_extract_body` 를 통째로 교체:

```python
def _extract_body(html_text: str) -> tuple[str, str, str, str]:
    """trafilatura 로 임의 HTML → (title, 본문(부트플레이트 제거 + 상한), date, canonical). 실패 시 빈값 4개.

    canonical = `<link rel=canonical>`/`og:url`(trafilatura doc.url) — 없으면 "". RSS 전문·HTML 공용.
    """
    import trafilatura
    doc = trafilatura.bare_extraction(html_text, with_metadata=True)
    if doc is None:
        return ("", "", "", "")
    title = (getattr(doc, "title", "") or "").strip()
    body = _excerpt(_strip_boilerplate((getattr(doc, "text", "") or "").strip()))
    date = (getattr(doc, "date", "") or "").strip()
    canonical = (getattr(doc, "url", "") or "").strip()
    return (title, body, date, canonical)
```

`_fetch_feed` 안의 호출부 교체:

```python
                _t, body, _d, _c = _extract_body(page)
```

`_extract_article` 바로 위에 헬퍼 2개 추가:

```python
def _host(u: str) -> str:
    """URL 호스트(소문자·`www.` 제거). 상대경로·빈값이면 ""."""
    h = (urlparse(u).hostname or "").lower()
    return h[4:] if h.startswith("www.") else h


def _is_offsite(canonical: str, listing_url: str) -> bool:
    """canonical 이 리스팅과 *다른 사이트*면 True — 블로그 리스팅에 남은 링크가 문서 등으로 옮겨간 경우.

    ★ fail-open: canonical 없음·상대경로(판단 불가)와 서브도메인 관계(blog.x.com ↔ x.com)는 False(통과).
    실측(2026-10-10): html 소스 4곳 링크 77개 중 True 는 best-practices(→ code.claude.com) 1건뿐.
    """
    c, home = _host(canonical), _host(listing_url)
    if not (c and home):
        return False
    return not (c == home or c.endswith("." + home) or home.endswith("." + c))
```

`_extract_article` 를 통째로 교체:

```python
def _extract_article(html_text: str, url: str, source_key: str, listing_url: str = "") -> FetchedArticle | None:
    """HTML 기사 → FetchedArticle. title·본문 둘 다 있고 본문이 기사 길이여야 채택(`_is_stub`).

    listing_url 을 주면(html 리스팅 경로) canonical 이 다른 사이트인 페이지를 버린다 — 문서 페이지는
    최종 수정일을 날짜로 내서 수정될 때마다 "새 글"로 보이기 때문(2026-10 감사: Best practices 14회 재발송).
    """
    title, text, published, canonical = _extract_body(html_text)
    if not (title and text):
        return None
    if listing_url and _is_offsite(canonical, listing_url):  # non-silent — 무엇을 왜 버렸나
        _debug.warn("fetch offsite", f"{source_key}: canonical 이 다른 호스트 — 글이 아니라 건너뜀: {url} → {canonical}")
        return None
    if _is_stub(text):  # 리스팅/쿠키월/스켈레톤에서 부스러기만 추출된 경우 — non-silent
        _debug.warn("fetch stub", f"{source_key}: 본문 미확보({len(text)}자 < {MIN_SOURCE_CHARS}) — {title[:40]}")
        return None
    return FetchedArticle(source_key, url, title, text, published)
```

`fetch_generic_html` 의 호출부 교체:

```python
        art = _extract_article(page, url, source.key, source.url)
```

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest tests/test_sources.py tests/test_curation.py -v && uv run pytest -q && uv run ruff check src tests`
Expected: 전부 PASS, 전체 스위트 실패 0, ruff `All checks passed!`

- [ ] **Step 5: 라이브 확인(읽기 전용, 네트워크)**

Run:

```bash
uv run python - <<'EOF'
from briefing.core.retrieval import sources as s
src = next(x for x in s.CATALOG if x.key == "anthropic-eng")
arts = s.fetch_generic_html(src, window_hours=0, max_items=30)
print(len(arts), any("best-practices" in a.url for a in arts))
EOF
```

Expected: stderr 에 `[WARN fetch offsite] anthropic-eng: canonical 이 다른 호스트 … claude-code-best-practices → https://code.claude.com/docs/en/best-practices` 1줄, stdout 마지막 값 `False`(best-practices 제외), 기사 수 > 0(정상 글 유지).

- [ ] **Step 6: 커밋**

```bash
git add src/briefing/core/retrieval/sources.py tests/test_sources.py
git commit -m "$(cat <<'EOF'
feat(retrieval): canonical 호스트 검사 — 리스팅의 문서 페이지를 새 글로 오인하지 않기

anthropic.com/engineering 의 best-practices 링크는 code.claude.com 문서로 옮겨가
최종 수정일이 날짜로 잡혀 수정될 때마다 재발송됐다(14회). canonical 이 다른 사이트면
버리고 warn. canonical 없음·상대경로·서브도메인은 통과(fail-open).

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: 재생 게이트 — 프로덕션 이력으로 새 dedup 검증

**Files:**
- Create: `scripts/dedup_audit/replay.py`

**Interfaces:**
- Consumes:
  - Task 1: `identity_keys`, `match_kind`, `url_key`
  - Task 2: `SourceMeta`
  - Task 3: `DEFAULT_DEDUP_LOOKBACK_DAYS`
  - Task 4: `published_keys`
  - 기존: `LocalLedger`
- Produces: CLI — `replay --until D [--expect-blocked N] [--expect-articles N]`(머지 게이트), `audit --since D`(배포 후 관측). 종료코드 0=PASS, 1=FAIL.

- [ ] **Step 1: 스크립트 작성**

`scripts/dedup_audit/replay.py`:

```python
#!/usr/bin/env python3
"""dedup 감사 — 프로덕션 이력(읽기 전용)으로 기사 신원 dedup 을 검증한다.

두 모드:
- replay: 과거 실발송 카드를 *새 dedup 코드*(article_identity.published_keys)에 날짜순으로 통과시켜
          무엇이 막혔을지 센다 — 머지 게이트(spec §10).
    uv run python scripts/dedup_audit/replay.py replay --until 2026-10-15 --expect-blocked 45 --expect-articles 8
- audit : 실제로 발송된 카드 중 lookback 안의 이전 발송과 같은 기사인 것을 센다 — 배포 후 관측(기대 0).
    uv run python scripts/dedup_audit/replay.py audit --since <배포 다음날>

두 모드 모두 AI Times(쿼리가 기사 ID) 막힘이 0 이어야 PASS. 설계: docs/superpowers/specs/2026-10-16-article-identity-dedup-design.md
"""
from __future__ import annotations

import argparse
import sys
import tempfile
from collections import Counter, defaultdict

import boto3

from briefing.core.article_identity import identity_keys, match_kind, published_keys, url_key
from briefing.core.config import DEFAULT_DEDUP_LOOKBACK_DAYS
from briefing.core.stores.ledger import LocalLedger
from briefing.core.stores.source_store import SourceMeta

REGION = "us-east-1"


def _scan(ddb, name: str, **kw) -> list[dict]:
    t = ddb.Table(name)
    resp = t.scan(**kw)
    out = list(resp["Items"])
    while "LastEvaluatedKey" in resp:
        resp = t.scan(ExclusiveStartKey=resp["LastEvaluatedKey"], **kw)
        out += resp["Items"]
    return out


class _MetaStore:
    """source-store 덤프를 get_meta 로 내주는 읽기 전용 어댑터(published_keys 가 쓰는 인터페이스)."""

    def __init__(self, meta: dict[str, SourceMeta]) -> None:
        self.meta = meta

    def get_meta(self, source_ids):
        return {i: self.meta[i] for i in source_ids if i in self.meta}


def _load(ddb) -> tuple[dict[str, SourceMeta], list[dict]]:
    """(source_id → 메타, 실제로 발송된 브리핑의 PUBLISH 행들)."""
    meta = {i["source_id"]: SourceMeta(url=i.get("url", ""), title=i.get("title", ""), media=i.get("media", ""))
            for i in _scan(ddb, "briefing-source-store", ProjectionExpression="source_id, #u, title, media",
                           ExpressionAttributeNames={"#u": "url"})}
    sent = {(s["user_id"], s["run_date"]) for s in _scan(ddb, "briefing-sent-log") if s.get("status") == "sent"}
    rows = [r for r in _scan(ddb, "briefing-ledger")
            if r.get("decision") == "PUBLISH" and (r["user_id"], r["run_date"]) in sent]
    return meta, rows


def _keys(sid: str, meta: dict[str, SourceMeta]) -> frozenset[str]:
    m = meta.get(sid)
    if m is None:
        return frozenset({f"sid:{sid}"})
    return identity_keys(source_id=sid, url=m.url, title=m.title, media=m.media)


def replay(meta, rows, until: str, lookback: int) -> list[tuple[str, str, str, str]]:
    """막히지 않은 카드만 시뮬레이션 원장에 PUBLISH 로 쌓으며 날짜순 재생(실제 dedup 과 같은 순서·같은 코드)."""
    by_day: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in rows:
        if r["run_date"] <= until:
            by_day[(r["run_date"], r["user_id"])].append(r)
    store, memo, blocked = _MetaStore(meta), {}, []
    with tempfile.TemporaryDirectory() as d:
        sim = LocalLedger(d)
        for rd, uid in sorted(by_day):
            seen = published_keys(sim, store, uid, rd, lookback, memo)
            for r in by_day[(rd, uid)]:
                if kind := match_kind(_keys(r["source_id"], meta), seen):
                    blocked.append((rd, uid, r["source_id"], kind))
                else:
                    sim.append(rd, uid, r["source_id"], r.get("card_key", ""), "PUBLISH", r.get("headline", ""))
    return blocked


def audit(meta, rows, since: str, lookback: int) -> list[tuple[str, str, str, str]]:
    """실제 발송 이력 그대로 — since 이후 카드 중 이전 발송과 같은 기사인 것(=dedup 이 놓친 것)."""
    store, memo, dups = _MetaStore(meta), {}, []
    seen_cache: dict[tuple[str, str], frozenset[str]] = {}
    with tempfile.TemporaryDirectory() as d:
        real = LocalLedger(d)
        for r in rows:
            real.append(r["run_date"], r["user_id"], r["source_id"], r.get("card_key", ""), "PUBLISH", r.get("headline", ""))
        for r in sorted(rows, key=lambda r: (r["run_date"], r["user_id"])):
            if r["run_date"] < since:
                continue
            ck = (r["user_id"], r["run_date"])
            if ck not in seen_cache:
                seen_cache[ck] = published_keys(real, store, r["user_id"], r["run_date"], lookback, memo)
            if kind := match_kind(_keys(r["source_id"], meta), seen_cache[ck]):
                dups.append((r["run_date"], r["user_id"], r["source_id"], kind))
    return dups


def _report(hits, meta, label: str) -> tuple[int, int]:
    """요약 출력 → (AI Times 막힘 수, 서로 다른 기사 수)."""
    print(f"{label}: {len(hits)}장 | 종류별 {dict(Counter(k for *_, k in hits))}")
    aitimes = sum(1 for _, _, sid, _ in hits if sid in meta and meta[sid].media == "AI Times")
    arts = Counter(url_key(meta[sid].url) if sid in meta else sid for _, _, sid, _ in hits)
    print(f"  AI Times: {aitimes} | 서로 다른 기사: {len(arts)}")
    for a, n in arts.most_common():
        print(f"  {n:3}  {a}")
    return aitimes, len(arts)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="기사 신원 dedup 재생·감사(프로덕션 읽기 전용)")
    sub = ap.add_subparsers(dest="mode", required=True)
    rp = sub.add_parser("replay")
    rp.add_argument("--until", required=True)
    rp.add_argument("--expect-blocked", type=int)
    rp.add_argument("--expect-articles", type=int)
    au = sub.add_parser("audit")
    au.add_argument("--since", required=True)
    for p in (rp, au):
        p.add_argument("--lookback", type=int, default=DEFAULT_DEDUP_LOOKBACK_DAYS)
    a = ap.parse_args(argv)

    meta, rows = _load(boto3.resource("dynamodb", region_name=REGION))
    if a.mode == "replay":
        hits = replay(meta, rows, a.until, a.lookback)
        aitimes, n_arts = _report(hits, meta, f"replay(≤{a.until}, lookback {a.lookback}일) 막힘")
        ok = aitimes == 0
        if a.expect_blocked is not None:
            ok = ok and len(hits) == a.expect_blocked
        if a.expect_articles is not None:
            ok = ok and n_arts == a.expect_articles
    else:
        hits = audit(meta, rows, a.since, a.lookback)
        _report(hits, meta, f"audit(≥{a.since}) 실제 중복 발송")
        ok = not hits
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: 머지 게이트 실행(프로덕션 읽기 전용)**

Run: `uv run python scripts/dedup_audit/replay.py replay --until 2026-10-15 --expect-blocked 45 --expect-articles 8`
Expected(2026-10-16 프로토타입 실측과 같아야 함):

```
replay(≤2026-10-15, lookback 90일) 막힘: 45장 | 종류별 {…}   ← url 43 · sid 1 · title 1 (순서 무관)
  AI Times: 0 | 서로 다른 기사: 8
   28  anthropic.com/engineering/claude-code-best-practices
    6  developers.googleblog.com/ml-drift-next-gen-gpu-aiml-inference-at-the-edge
    6  anthropic.com/news/2026-us-midterms
    …(1장짜리 5건: cognizant · claude-blog 2건 · aws-kr narae · aws-ml scaling)
PASS
```

FAIL 이면 머지하지 않는다 — 어느 기사가 늘었/줄었는지 출력으로 원인을 찾는다(새 오탐 = 키 규칙 문제, 누락 = join·lookback 문제).

- [ ] **Step 3: 커밋**

```bash
git add scripts/dedup_audit/replay.py
git commit -m "$(cat <<'EOF'
feat(scripts): dedup 재생·감사 스크립트 — 프로덕션 이력으로 새 dedup 검증

replay = 머지 게이트(≤10-15 에서 45장·8기사·AI Times 0 실측 일치),
audit = 배포 후 실제 중복 발송 관측(기대 0). 프로덕션 DDB 읽기 전용.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: 출하 — 머지·배포·사후 관측·문서 승격

> ⚠️ **Step 2 부터는 비가역·외부 영향**(main push, 프로덕션 런타임 교체). 각 단계 전에 **사용자에게 명시적으로 확인**받는다.

**Files:**
- Create: `docs/deliveries/<배포일>-article-identity-dedup-delivery.md`
- Modify: `docs/README.md` (색인 상태 DRAFT → SHIPPED·LIVE)
- Modify: `design/architecture/system-map.md` (§3 의 dedup 줄 — truth flows up)

**Interfaces:**
- Consumes: Task 1–6 전부
- Produces: 프로덕션 런타임(다음 05:00 KST run 부터 새 dedup)

- [ ] **Step 1: 최종 검증**

Run: `uv run pytest -q && uv run ruff check src tests && uv run python scripts/dedup_audit/replay.py replay --until 2026-10-15 --expect-blocked 45 --expect-articles 8`
Expected: 실패 0 · `All checks passed!` · `PASS`

- [ ] **Step 2: main 머지 + push (사용자 확인 후)**

```bash
git switch main && git pull --ff-only && git merge --ff-only feat/article-identity-dedup && git push origin main
```

- [ ] **Step 3: 런타임 배포 (사용자 확인 후)**

Run: `uv run python -m briefing.runtime.deploy_runtime`
Expected: READY · 런타임 ARN 불변(`.env` 의 `BRIEFING_RUNTIME_ARN` 과 같음). 대기 중이던 main `22a358c`(미상 출처 키 warn)도 함께 실린다.
확인: `aws bedrock-agentcore-control get-agent-runtime --agent-runtime-id "$(grep ^BRIEFING_RUNTIME_ID= .env | cut -d= -f2)" --region us-east-1 --output json | grep DEDUP_LOOKBACK_DAYS` → `"90"` 이 보여야 한다(응답에 환경변수가 안 실리는 API 라면 이 확인은 건너뛰고 Step 4 audit 으로 판단).
(⚠️ `deploy_scheduler` 는 돌리지 않는다 — 재실행 시 `BRIEFING_DRY_RUN=1` 로 리셋되는 풋건.)

- [ ] **Step 4: 다음 아침 사후 관측 (배포 다음날 05:00 KST run 이후)**

Run: `uv run python scripts/dedup_audit/replay.py audit --since <배포 다음날 YYYY-MM-DD>`
Expected: `실제 중복 발송: 0장` · `PASS`
CloudWatch(런타임 로그)에서 `pipeline dedup` · `fetch offsite` warn 라인 확인 — `fetch offsite` 에 best-practices 가, `원본 없는 이전 발행 N건` 은 N 이 날마다 줄어 2026-10-23 run 부터 0 이어야 한다(07-24 이전 행이 90일 창 밖으로).
2주간 같은 audit 을 주 1회 반복해 0 유지 확인.

- [ ] **Step 5: 문서 승격 + 커밋 (사용자 확인 후 push)**

- `docs/deliveries/<배포일>-article-identity-dedup-delivery.md`: 배포 커밋·ECR 태그·replay/audit 출력·관측 결과·잔여(90일 넘는 재등장은 1회 재발송 가능, `claude-blog` 무음 정지 별건).
- `docs/README.md`: article-identity-dedup 행 상태 `DRAFT` → `SHIPPED·LIVE` + delivery 행 추가.
- `design/architecture/system-map.md` §3: `ledger 조회 → prior_published (이전 run 에서 PUBLISH 한 source_id 제외)` 줄을 `ledger(90일) + source-store join → 신원 키(해시·URL·매체+제목) 일치 시 제외` 로 갱신.

```bash
git add docs/deliveries/ docs/README.md design/architecture/system-map.md
git commit -m "$(cat <<'EOF'
docs(delivery): 기사 신원 dedup 출하 기록 + 시스템 지도 갱신

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
)"
```
