#!/usr/bin/env python3
"""사례 4 — Anthropic News 목록이 링크하는 최상위 경로 페이지들: 제목 · 날짜 · 선언된 종류 · 수집된 횟수(읽기 전용).

    uv run python docs/work_note/Nov-2026/261114-duplicate-articles-7days/tools/case4_root_pages.py

모델 출시 글 4건이 한 번도 수집되지 않았음을 본다 — 결과 `case4-root-pages.txt`.
"""
from __future__ import annotations

import boto3
from boto3.dynamodb.conditions import Attr

from briefing.core.retrieval.sources import _declared_page_type, _extract_body, _http_get

PATHS = ["/claude-fable-and-mythos-5-2", "/claude-opus-5-5", "/claude-sonnet-5-5", "/claude-haiku-5-5", "/science", "/press-kit"]
t = boto3.resource("dynamodb", region_name="us-east-1").Table("briefing-source-store")
for p in PATHS:
    url = "https://www.anthropic.com" + p
    html = _http_get(url)
    title, text, published, _ = _extract_body(html) if html else ("", "", "", "")
    kw = dict(FilterExpression=Attr("url").contains("anthropic.com" + p), ProjectionExpression="source_id, fetched_at")
    r = t.scan(**kw)
    items = list(r["Items"])
    while "LastEvaluatedKey" in r:
        r = t.scan(ExclusiveStartKey=r["LastEvaluatedKey"], **kw)
        items += r["Items"]
    print(f"{p}: 종류={_declared_page_type(html)!r} · 날짜={published or '-'} · 본문 {len(text)}자 · 수집된 적 {len(items)}회 · {title[:70]!r}")
