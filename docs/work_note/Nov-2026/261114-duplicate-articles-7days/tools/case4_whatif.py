#!/usr/bin/env python3
"""사례 4 — 원 발표 글이 왜 수집되지 않았나 · 수집됐다면 두 글이 재보도로 빠졌을까(읽기 전용).

    uv run python docs/work_note/Nov-2026/261114-duplicate-articles-7days/tools/case4_whatif.py [반복 수=3]

★ 1) 은 **수정 전 동작**을 본다 — `extra_article_prefixes` 를 넘기지 않고 `_article_links` 를 부른다(수정 뒤 동작은
`case4_live_fetch.py`). 수정 전 결과 = "운영이 고르나: False"(2026-11-15 실행, README 에 기록).

1) Anthropic News 목록(`/news`)이 원 발표 글을 링크하는지, 수정 전 링크 추출(`_article_links`)이 그 글을 잡는지.
2) 원 발표 글이 기사로 추출되는지(선언된 페이지 종류 · 본문 길이 · 날짜).
3) 운영 판정자에 세 쌍을 묻는다: (원문, The Decoder) · (원문, PyTorch Korea) · (The Decoder, PyTorch Korea).
"""
from __future__ import annotations

import re
import sys
from urllib.parse import urljoin, urlparse

from briefing.core.config import load_settings
from briefing.core.retrieval import relevance_bedrock as rb
from briefing.core.retrieval.rereport import MAX_JUDGE_CHARS, REREPORT_SYSTEM, _first_json_object
from briefing.core.retrieval.sources import (_article_links, _declared_page_type, _extract_article, _extract_body,
                                             _http_get, _load_catalog)
from briefing.core.stores.dynamo import source_store_from_settings

REPS = int(sys.argv[1]) if len(sys.argv) > 1 else 3
ORIG = "https://www.anthropic.com/claude-fable-and-mythos-5-2"
DECODER = "83b0ce2ba9123db817a05948478dac89b71840c08e396ffac3a6e89048e6da76"
PTK = "dd2635aa37e535eb4eaa437b74a50f74e40e437bd8022a707448ca5a5680ff92"

src = next(s for s in _load_catalog() if s.key == "anthropic")
listing = _http_get(src.url)
picked = _article_links(listing, src.url, src.article_path, src.exclude_paths)
paths = set()
for href in re.findall(r"""href=["']([^"']+)["']""", listing):
    u = urlparse(urljoin("https://www.anthropic.com", href.split("#")[0].split("?")[0]))
    if u.netloc.endswith("anthropic.com"):
        paths.add(u.path.rstrip("/"))
root = sorted(p for p in paths if p.count("/") == 1 and p)
print(f"== 1) 목록 {src.url}: 수정 전 규칙(`/news/<slug>` 만)이 고르는 글 링크 {len(picked)}개")
print(f"   원 발표 글을 수정 전 규칙이 고르나: {ORIG in picked}")
print(f"   목록 HTML 에 원 발표 글 링크가 있나: {'/claude-fable-and-mythos-5-2' in paths}")
print(f"   목록에 있는 최상위(한 단계) 경로 {len(root)}개: {root}")

html = _http_get(ORIG)
title, text, published, canonical = _extract_body(html)
art = _extract_article(html, ORIG, "anthropic", src.url)
print(f"\n== 2) 원 발표 글: 선언된 종류={_declared_page_type(html)!r} · 제목={title!r} · 본문 {len(text)}자 · 날짜={published} · canonical={canonical}")
print(f"   기사로 추출되나: {art is not None}")

s = load_settings()
store = source_store_from_settings(s)
client = rb._client(s.region)
dec, ptk = store.get_source(DECODER), store.get_source(PTK)
pairs = [("원문", text, "The Decoder", dec.text), ("원문", text, "PyTorch Korea", ptk.text),
         ("The Decoder", dec.text, "PyTorch Korea", ptk.text)]
print(f"\n== 3) 판정({REPS}회씩)")
for an, at, bn, bt in pairs:
    user = f"<A>\n{at[:MAX_JUDGE_CHARS]}\n</A>\n\n<B>\n{bt[:MAX_JUDGE_CHARS]}\n</B>"
    res = []
    for _ in range(REPS):
        resp = client.converse(modelId=s.relevance_model_id, system=[{"text": REREPORT_SYSTEM}],
                               messages=[{"role": "user", "content": [{"text": user}]}],
                               inferenceConfig={"maxTokens": rb.REREPORT_MAX_TOKENS})
        out = next((x["text"] for x in resp["output"]["message"]["content"] if "text" in x), "")
        obj = _first_json_object(out)
        res.append((obj.get("same") if obj else None, (obj or {}).get("reason", out)[:230]))
    print(f"A={an} ← B={bn}: {[r[0] for r in res]}")
    for same, reason in res:
        print(f"     {same}: {reason}")
