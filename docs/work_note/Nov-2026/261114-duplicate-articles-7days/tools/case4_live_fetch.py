#!/usr/bin/env python3
"""사례 4 — 고친 수집 코드로 실제 Anthropic News 를 받아 본다(읽기 전용, 저장 없음).

    uv run python docs/work_note/Nov-2026/261114-duplicate-articles-7days/tools/case4_live_fetch.py

창을 넓힌 실행(11-09 출시 글이 들어오는지)과 운영 창 48h 실행(옛 출시 글·허브가 안 들어오는지)을 나란히 본다 —
결과 `case4-live-fetch-20261115.txt`. ★ 240h 창은 2026-11-19 이후에는 11-09 글을 덮지 못한다(다시 볼 때 창을 늘린다).
"""
from __future__ import annotations

import contextlib
import io

from briefing.core.article_identity import cite_key
from briefing.core.retrieval.sources import CATALOG, _article_links, _http_get, fetch_generic_html

src = next(s for s in CATALOG if s.key == "anthropic")
print(f"extra_article_prefixes = {src.extra_article_prefixes} · window_hours = {src.window_hours} · max_items = {src.max_items or '기본'}")
links = _article_links(_http_get(src.url), src.url, src.article_path, src.exclude_paths, src.extra_article_prefixes)
extra = [u for u in links if "/news/" not in u]
print(f"목록에서 고른 링크 {len(links)}개 · 그중 `/news/` 밖 {len(extra)}개: {[u.rsplit('/', 1)[-1] for u in extra]}")

for label, window in (("창 240h(11-09 글 포함)", 240), (f"운영 창 {src.window_hours}h", src.window_hours)):
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        arts = fetch_generic_html(src, window_hours=window, max_items=30)
    print(f"\n== {label}: {len(arts)}건")
    for a in arts:
        mark = "★" if "/news/" not in a.url else " "
        print(f" {mark} {a.published_at[:10]} {a.title[:70]} · {len(a.raw_text)}자 · cite_key={cite_key(a.url)}")
    warns = [ln for ln in err.getvalue().splitlines() if ln.strip()]
    print(f"   경고 {len(warns)}줄")
    for ln in warns:
        print("    ", ln[:200])
