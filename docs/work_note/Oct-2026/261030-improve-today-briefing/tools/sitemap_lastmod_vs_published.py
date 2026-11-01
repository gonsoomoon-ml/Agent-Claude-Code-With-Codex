"""anthropic sitemap 의 lastmod(수정일) 가 발행일과 얼마나 다른가 — 최근 lastmod 항목의 페이지 article:published_time 과 대조(네트워크 읽기만)."""
import re
import urllib.request
UA = "Mozilla/5.0 (compatible; briefing-check)"
def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")
xml = get("https://www.anthropic.com/sitemap.xml")
es = []
for block in re.findall(r"<url>(.*?)</url>", xml, re.S):
    loc = re.search(r"<loc>\s*(.*?)\s*</loc>", block, re.S)
    mod = re.search(r"<lastmod>\s*(.*?)\s*</lastmod>", block, re.S)
    es.append((loc.group(1).strip() if loc else "", mod.group(1).strip() if mod else ""))
recent = sorted([(loc, m) for loc, m in es if m[:10] >= "2026-10-22" and ("/news/" in loc or "/research/" in loc)], key=lambda e: e[1], reverse=True)
print(f"lastmod ≥ 10-22 인 /news/·/research/ 항목 {len(recent)}개")
false_fresh = 0
for loc, mod in recent:
    try:
        html = get(loc)
    except Exception as e:  # noqa: BLE001
        print(f"  {mod[:10]} {loc.split('.com',1)[-1][:60]:60s} (fetch 실패 {type(e).__name__})")
        continue
    pub = re.search(r'article:published_time"\s+content="([^"]+)"', html) or re.search(r'content="([^"]+)"\s+property="article:published_time"', html)
    og = re.search(r'property="og:type"\s+content="([^"]+)"', html)
    p = pub.group(1)[:10] if pub else "-"
    ff = " ★수정일≠발행일" if p != "-" and p < mod[:10] and (int(mod[8:10]) - int(p[8:10]) > 2 or mod[:7] != p[:7]) else ""
    false_fresh += bool(ff)
    print(f"  lastmod {mod[:10]} published {p} og {og.group(1) if og else '-':8s} {loc.split('.com',1)[-1][:60]}{ff}")
print(f"\n수정일이 발행일보다 3일+ 뒤(= 사이트맵 기준이면 옛 글이 새 글로 보임): {false_fresh}/{len(recent)}")
# google-dev RSS 날짜 태그
feed = get("https://developers.googleblog.com/rss")
print("\ngoogle-dev rss 날짜 태그:", sorted(set(re.findall(r"<(pubDate|atom:updated|dc:date|updated|published)>", feed))), "· 첫 item:", re.search(r"<item>(.*?)</item>", feed, re.S).group(1)[:300].replace("\n", " "))
