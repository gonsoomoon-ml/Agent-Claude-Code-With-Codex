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
