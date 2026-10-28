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
from datetime import date, timedelta
from typing import Any
from urllib.parse import urlparse

from .stores.source_store import SourceMeta

MIN_TITLE_KEY_CHARS = 15  # 정규화 후 이보다 짧은 제목은 키 없음 — "Release notes" 류 일반 제목 오탐 방지
TITLE_KEY_WINDOW_DAYS = 14  # 제목 키는 이 기간 안의 이전 발행에만 — 같은 제목 연재(월간 호 등)의 새 호를 막지 않게.
#                            실측 제목 일치는 slug 수정 1일 간격뿐(2026-10 감사). 해시·URL 키는 lookback 전체(90일).

_NON_WORD = re.compile(r"\W+")
# 첫 경로 조각이 언어 코드인 번역판 URL(`/de/`·`/ko/`·`/zh-cn/`·`/es-419/`) — 같은 글의 다른 언어판을 한 키로.
# 언어 목록을 닫아 둔다: `/ai/`·`/ml/` 같은 일반 두 글자 경로까지 지우면 다른 글끼리 키가 겹친다.
_LOCALE = re.compile(
    r"(?:ar|cs|da|de|el|en|es|fi|fr|he|hi|hu|id|it|ja|ko|nl|no|nb|pl|pt|ro|ru|sv|th|tr|uk|vi|zh)"
    r"(?:-(?:[a-zA-Z]{2}|[a-zA-Z]{4}|\d{3}))?")


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


def cite_key(url: str) -> str:
    """URL → 인용 키(재보도 dedup 용). `url_key` 에서 첫 경로 조각이 언어 코드면 지운다.

    ★ 비교 양쪽(본문 인용 링크·보낸 기사 URL·오늘 후보 URL)에 같은 함수를 써야 한다 — The Decoder 는
      `claude.com/de/…` 를, AWS KR 은 저장 URL 자체가 `aws.amazon.com/ko/…` 다. 키 없으면 "".
    """
    k = url_key(url)
    host, slash, rest = k.partition("/")
    if not slash:
        return k
    first, sep, tail = rest.partition("/")
    seg, q, query = first.partition("?")
    if not _LOCALE.fullmatch(seg):
        return k
    return f"{host}/{tail}" if sep else f"{host}{q}{query}"


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


def published_keys(ledger: Any, store: Any, user_id: str, run_date: str, lookback_days: int,
                   memo: dict[str, SourceMeta | None],
                   url_index: dict[str, str] | None = None) -> frozenset[str]:
    """user 가 run_date 이전 lookback_days 안에 메일로 받은 기사들(PUBLISH·QUARANTINE)의 신원 키 합집합.

    의미론(선행 설계 2026-07-11): strictly-earlier(run_date 미만 — 같은 날 재실행 = 강제 재발송 런북 보존).
    경계: 정확히 lookback_days 일 전은 포함(sk >= since).
    ★ 2026-10-18 변경(N5): 예전엔 'PUBLISH 만(QUARANTINE 은 재도전)'이었다 — 격리 카드를 보내지 않던 때의 전제.
      이제 격리 카드도 ⚠ 표시로 메일에 실리므로(사용자 결정) 받은 기사로 센다. 안 그러면 48h 창 소스의 같은
      기사가 다음 날 다시 나간다(캐시된 같은 QUARANTINE 카드라 재도전으로 달라지는 것도 없다).
    memo = run 동안 사용자 간 공유하는 {source_id: SourceMeta | None} — 같은 기사를 받은 두 번째 사용자부터는
    source-store 를 다시 읽지 않는다. None = 원본 없음(2026-08-01 이전 TTL 만료분) → 해시 키만(fail-open).
    ledger: `query(user_id, since_date)` · store: `get_meta(ids)` 를 가진 객체(Local·Dynamo 공통).
    url_index(선택) = 재보도 dedup 의 역참조 — 메타가 있는 받은 기사마다 `{cite_key(url): source_id}` 를 채운다
    (같은 키면 더 최근에 받은 쪽). 오늘 기사가 인용한 링크에서 원문(A) 본문을 찾아 읽는 데 쓴다.
    """
    try:
        since = (date.fromisoformat(run_date) - timedelta(days=lookback_days)).isoformat()
        title_since = (date.fromisoformat(run_date) - timedelta(days=TITLE_KEY_WINDOW_DAYS)).isoformat()
    except ValueError:
        since = title_since = ""  # 형식 밖 run_date — 전체 조회(기존 동작 유지)
    latest: dict[str, str] = {}  # source_id → 가장 최근에 받은 run_date (제목 키 창 판단용)
    for r in ledger.query(user_id, since_date=since):
        if r.get("decision") in ("PUBLISH", "QUARANTINE") and r.get("run_date", "") < run_date:
            latest[r["source_id"]] = max(latest.get(r["source_id"], ""), r["run_date"])
    missing = [i for i in latest if i not in memo]
    if missing:
        found = store.get_meta(missing)
        for i in missing:
            memo[i] = found.get(i)
    keys: set[str] = set()
    index_on: dict[str, str] = {}  # cite_key → 그 키를 채운 기사의 run_date (최근 쪽이 이긴다)
    for i, sent_on in latest.items():
        m = memo[i]
        if m is None:
            keys.add(f"sid:{i}")
            continue
        if url_index is not None and (c := cite_key(m.url)) and sent_on >= index_on.get(c, ""):
            url_index[c], index_on[c] = i, sent_on
        k = identity_keys(source_id=i, url=m.url, title=m.title, media=m.media)
        if sent_on < title_since:  # 제목 키 창(14일) 밖 — 해시·URL 키만 남긴다
            k = frozenset(x for x in k if not x.startswith("title:"))
        keys |= k
    return frozenset(keys)
