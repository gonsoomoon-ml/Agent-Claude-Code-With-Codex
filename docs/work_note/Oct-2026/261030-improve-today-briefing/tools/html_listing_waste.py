"""#7 — 날짜 없는 목록(html 리스팅) 소스가 run 마다 어떤 페이지를 열고 버리는지 재현(읽기 전용 네트워크, 저장소 무변경).

운영 `fetch_generic_html` 과 같은 순서·중단 규칙(풀 수 확보 또는 예산 초과)으로 링크를 열되, 페이지마다 결과를 기록한다:
kept(창 안) · stale(창 밖 날짜) · stub(본문 <500자) · nobody(제목/본문 없음) · http(응답 없음) · undated(날짜 없음 → fail-open 통과) ·
non-article(page_type 관문이 거른 선언 유형, 2026-11-01). exclude_paths 는 목록 단계에서 빠져 '목록 링크' 수에 안 들어간다.
usage: uv run python html_listing_waste.py [--sources anthropic,meta-research,...] [--budget 180]
"""
from __future__ import annotations

import argparse
import time
from collections import Counter

from briefing.core.retrieval import sources as src
from briefing.core.retrieval.curation import _DEFAULT_MAX_ITEMS, _SELECT_POOL
from briefing.core.retrieval.sources import CATALOG

HTML_KEYS = ("anthropic", "anthropic-eng", "claude-blog", "anthropic-research", "google-dev", "meta-research", "pytorch-kr-news")


def walk(source, budget_s: float):
    win = source.window_hours or 24
    pool = _SELECT_POOL if source.select == "llm" else (source.max_items or _DEFAULT_MAX_ITEMS)
    t0 = time.monotonic()
    listing = src._http_get(source.url)
    if not listing:
        return {"key": source.key, "error": "listing fetch 실패"}
    links = src._article_links(listing, source.url, source.article_path, source.exclude_paths)  # 2026-11-01 +a 관문(제외 경로)
    rows = []
    kept = 0
    for url in links:
        if kept >= pool or time.monotonic() - t0 >= budget_s:
            break
        t1 = time.monotonic()
        page = src._http_get(url)
        dt = time.monotonic() - t1
        if not page:
            rows.append((url, "http", "", "", dt))
            continue
        if source.page_type == "article":  # 2026-11-01 +a 관문(선언된 페이지 유형)
            declared = src._declared_page_type(page)
            if declared and declared != "article":
                rows.append((url, "non-article", declared, "", dt))
                continue
        title, text, published, canonical = src._extract_body(page)
        if not (title and text):
            rows.append((url, "nobody", "", title[:40], dt))
            continue
        offsite = bool(src._is_offsite(canonical, source.url))
        if src._is_stub(text):
            rows.append((url, "stub", published, title[:40], dt))
            continue
        if src._is_stale(published, win):
            rows.append((url, "stale" + ("+offsite" if offsite else ""), published, title[:40], dt))
            continue
        kept += 1
        rows.append((url, "undated" if not published else "kept", published, title[:40], dt))
    return {"key": source.key, "pool": pool, "window": win, "links": len(links), "rows": rows,
            "elapsed": time.monotonic() - t0}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sources", default=",".join(HTML_KEYS))
    ap.add_argument("--budget", type=float, default=180.0)
    a = ap.parse_args(argv)
    by_key = {s.key: s for s in CATALOG}
    total = Counter()
    for k in a.sources.split(","):
        r = walk(by_key[k], a.budget)
        if "error" in r:
            print(f"### {k}: {r['error']}")
            continue
        c = Counter(row[1].split("+")[0] for row in r["rows"])
        total.update(c)
        print(f"### {k}: 목록 링크 {r['links']} · 연 페이지 {len(r['rows'])} · 풀 {r['pool']} · 창 {r['window']}h · "
              f"{r['elapsed']:.0f}s → {dict(c)}")
        for url, kind, pub, title, dt in r["rows"]:
            if kind != "kept":
                print(f"   {kind:14s} {pub or '-':10s} {dt:4.1f}s {url.split('/')[-1][:60]:60s} {title}")
    print("\n합계(연 페이지 중):", dict(total))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
