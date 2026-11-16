#!/usr/bin/env python3
"""사례 4 — 두 글(The Decoder 11-10 · PyTorch Korea 11-11)이 본문에서 인용한 링크와 그 교집합(읽기 전용).

    uv run python docs/work_note/Nov-2026/261114-duplicate-articles-7days/tools/case4_cites.py

페이지를 다시 받아 운영과 같은 함수(`_cited_keys`)로 인용 키를 뽑는다 — 결과 `case4-cites.txt`.
"""
from __future__ import annotations

from briefing.core.article_identity import cite_host
from briefing.core.retrieval.sources import _cited_keys, _http_get

URLS = {
    "decoder": "https://the-decoder.com/claude-fable-5-2-and-mythos-5-2-cement-anthropics-ai-lead-just-before-its-ipo/",
    "pytorchkr": "https://discuss.pytorch.kr/t/anthropic-claude-fable-5-2-mythos-5-2-30-feat-opus-5-5/12478",
}
keys = {}
for name, url in URLS.items():
    html = _http_get(url)
    ks = _cited_keys(html, url)
    keys[name] = set(ks)
    print(f"== {name}: 인용 키 {len(ks)}개")
    for k in sorted(ks):
        print("   ", k)
both = keys["decoder"] & keys["pytorchkr"]
print(f"\n== 두 글이 함께 인용한 페이지 {len(both)}개")
for k in sorted(both):
    print("   ", k)
hosts = {cite_host(k) for k in keys["decoder"]} & {cite_host(k) for k in keys["pytorchkr"]}
print(f"\n== 두 글이 함께 인용한 사이트 {len(hosts)}개: {sorted(hosts)}")
