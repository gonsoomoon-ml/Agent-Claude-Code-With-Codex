"""+a dive-in — 허브(목록) 페이지와 기사 페이지를 코드가 구별할 수 있는 제너릭 신호 측정(네트워크 읽기만, 저장소·DDB 무변경).

소스별 목록의 링크를 운영과 같은 `_article_links` 로 뽑아 페이지마다:
  og:type · JSON-LD @type · trafilatura pagetype · 본문 길이 · 추출 날짜 · 본문 속 날짜 문자열 수 ·
  페이지 안의 '형제 글 링크' 수(소스 목록 경로 한 단계 아래 링크, 자기 제외) 를 찍는다.
usage: uv run python hub_signals.py [--sources anthropic,google-dev,...] [--limit 40]
"""
from __future__ import annotations

import argparse
import json
import re

from briefing.core.retrieval import sources as src
from briefing.core.retrieval.sources import CATALOG

HTML_KEYS = ("anthropic", "claude-blog", "anthropic-research", "google-dev", "meta-research", "pytorch-kr-news")
_OG = re.compile(r'<meta[^>]+property=["\']og:type["\'][^>]+content=["\']([^"\']+)["\']', re.I)
_OG2 = re.compile(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:type["\']', re.I)
_LD = re.compile(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', re.S | re.I)
_DATE_TXT = re.compile(r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.? \d{1,2}, \d{4}\b|\b\d{4}[-.]\d{2}[-.]\d{2}\b|\d{4}년 \d{1,2}월 \d{1,2}일")


def ld_types(html: str) -> str:
    out = []
    for blob in _LD.findall(html):
        try:
            data = json.loads(blob.strip())
        except Exception:  # noqa: BLE001
            continue
        items = data if isinstance(data, list) else [data]
        for it in items:
            if isinstance(it, dict):
                t = it.get("@type")
                if isinstance(t, list):
                    out.extend(str(x) for x in t)
                elif t:
                    out.append(str(t))
                for g in it.get("@graph", []) if isinstance(it.get("@graph"), list) else []:
                    if isinstance(g, dict) and g.get("@type"):
                        out.append(str(g.get("@type")))
    return ",".join(dict.fromkeys(out))[:40]


def pagetype(html: str) -> str:
    import trafilatura
    doc = trafilatura.bare_extraction(html, with_metadata=True)
    return (getattr(doc, "pagetype", "") or "") if doc is not None else ""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sources", default=",".join(HTML_KEYS))
    ap.add_argument("--limit", type=int, default=40)
    a = ap.parse_args(argv)
    by_key = {s.key: s for s in CATALOG}
    for k in a.sources.split(","):
        s = by_key[k]
        listing = src._http_get(s.url)
        links = src._article_links(listing, s.url, s.article_path)[: a.limit]
        print(f"\n### {k} ({s.url}) 링크 {len(links)}")
        print(f"{'slug':48s} {'og:type':10s} {'ld@type':22s} {'pagetype':10s} {'chars':>5s} {'date':10s} {'ndate':>5s} {'sibl':>4s}")
        for url in links:
            page = src._http_get(url)
            if not page:
                print(f"{url.split('/')[-1][:48]:48s} (http 실패)")
                continue
            title, text, published, _canon = src._extract_body(page)
            og = (_OG.search(page) or _OG2.search(page))
            siblings = [u for u in src._article_links(page, s.url, s.article_path) if u.rstrip('/') != url.rstrip('/')]
            print(f"{url.split('/')[-1][:48]:48s} {(og.group(1) if og else '-')[:10]:10s} {(ld_types(page) or '-'):22s} "
                  f"{(pagetype(page) or '-')[:10]:10s} {len(text):5d} {published or '-':10s} {len(_DATE_TXT.findall(text)):5d} {len(siblings):4d}"
                  f"  {title[:30]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
