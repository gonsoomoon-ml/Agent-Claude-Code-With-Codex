#!/usr/bin/env python3
"""게이트 10-25 쌍이 왜 안 걸리나(읽기 전용): 그날 관리자 발송 기사의 인용 키 vs 보낸 기사 색인."""
from __future__ import annotations

from briefing.core.article_identity import published_keys
from briefing.core.config import DEFAULT_DEDUP_LOOKBACK_DAYS, load_settings
from briefing.core.retrieval.sources import _body_links, _cited_keys, _http_get
from briefing.core.stores.dynamo import ledger_from_settings, source_store_from_settings

ADMIN = "445814b8-5001-70a6-84a6-6c010ac347ba"
s = load_settings()
ledger, store = ledger_from_settings(s), source_store_from_settings(s)
rows = ledger.query(ADMIN)
sent_index: dict[str, str] = {}
published_keys(ledger, store, ADMIN, "2026-10-25", DEFAULT_DEDUP_LOOKBACK_DAYS, {}, url_index=sent_index)
print(f"10-25 이전 보낸 기사 색인 {len(sent_index)}")
for k, sid in sent_index.items():
    if "subagent" in k or "fold" in k:
        fs = store.get_source(sid)
        print(f"  색인: {k}  ← [{fs.media}] {fs.title[:60]}")
for sid in sorted({r["source_id"] for r in rows if r.get("run_date") == "2026-10-25"}):
    fs = store.get_source(sid)
    if "Decoder" not in fs.media:
        continue
    html = _http_get(fs.url)
    cited = _cited_keys(html, fs.url) if html else ()
    print(f"\n[{fs.media}] {fs.title[:70]}\n  {fs.url}\n  html={'없음' if not html else len(html)} · 인용 키 {len(cited)} · 색인 일치 {[k for k in cited if k in sent_index]}")
    for k in cited:
        if "claude" in k or "anthropic" in k:
            print(f"    · {k}")
    if html and "subagent" in fs.url:
        links = [u for u in _body_links(html) if "claude" in u or "anthropic" in u]
        print("  본문 링크(원형):", links[:6])
