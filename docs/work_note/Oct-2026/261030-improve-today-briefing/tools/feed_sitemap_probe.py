"""+a dive-in — html 목록 소스의 기계용 목록(사이트맵·RSS) 내용 점검(네트워크 읽기만).
anthropic.com/sitemap.xml: 경로별 URL 수 · 허브 URL 포함 여부와 lastmod · /engineering/ 포함 여부 · news: 태그 유무 · 최근 /news/ 항목.
claude.com/sitemap.xml · research.meta.ai/sitemap.xml: 항목 수·lastmod 유무. developers.googleblog.com/rss: 항목 수·날짜·링크·본문 길이.
"""
from __future__ import annotations

import re
import urllib.request
from collections import Counter

UA = "Mozilla/5.0 (compatible; briefing-check)"
HUBS = {"announcements", "partnerships", "product", "security", "features", "policy", "safeguards"}


def get(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310
        return r.read().decode("utf-8", "replace")


def entries(xml: str) -> list[tuple[str, str]]:
    out = []
    for block in re.findall(r"<url>(.*?)</url>", xml, re.S):
        loc = re.search(r"<loc>\s*(.*?)\s*</loc>", block, re.S)
        mod = re.search(r"<lastmod>\s*(.*?)\s*</lastmod>", block, re.S)
        out.append((loc.group(1).strip() if loc else "", mod.group(1).strip() if mod else ""))
    return out


def sitemap(name: str, url: str, prefixes: tuple[str, ...]):
    xml = get(url)
    es = entries(xml)
    print(f"\n### {name} {url}: url {len(es)}개 · lastmod 있음 {sum(1 for _, m in es if m)} · news: 태그 {'있음' if '<news:' in xml else '없음'} · sitemapindex {'<sitemapindex' in xml}")
    c = Counter()
    for loc, _ in es:
        path = loc.split("://", 1)[-1].split("/", 1)[-1] if "://" in loc else loc
        top = "/" + path.split("/")[0] if path else "/"
        c[top] += 1
    print("  최상위 경로별:", dict(c.most_common(12)))
    for p in prefixes:
        sub = [(loc, m) for loc, m in es if f"/{p}/" in loc]
        sub.sort(key=lambda e: e[1], reverse=True)
        print(f"  /{p}/ {len(sub)}개 · 최신 lastmod 5: {[(loc.rsplit('/', 1)[-1][:40], m[:10]) for loc, m in sub[:5]]}")
    hubs = [(loc, m) for loc, m in es if loc.rstrip("/").rsplit("/", 1)[-1] in HUBS]
    if hubs:
        print("  허브 URL 포함:", [(loc.split('.com', 1)[-1], m[:10]) for loc, m in hubs])


def rss(name: str, url: str):
    xml = get(url)
    items = re.findall(r"<item>(.*?)</item>", xml, re.S)
    print(f"\n### {name} {url}: item {len(items)}개")
    for it in items[:6]:
        link = re.search(r"<link>\s*(.*?)\s*</link>", it, re.S)
        date = re.search(r"<pubDate>\s*(.*?)\s*</pubDate>", it, re.S)
        desc = re.search(r"<description>(.*?)</description>", it, re.S)
        cont = re.search(r"<content:encoded>(.*?)</content:encoded>", it, re.S)
        print(f"  {date.group(1)[:25] if date else '-':25s} desc {len(desc.group(1)) if desc else 0:6d}자 content {len(cont.group(1)) if cont else 0:6d}자  {link.group(1) if link else '-'}")


sitemap("anthropic", "https://www.anthropic.com/sitemap.xml", ("news", "engineering", "research"))
sitemap("claude.com", "https://claude.com/sitemap.xml", ("resources/articles",))
sitemap("meta-research", "https://research.meta.ai/sitemap.xml", ("blog",))
rss("google-dev", "https://developers.googleblog.com/rss")
