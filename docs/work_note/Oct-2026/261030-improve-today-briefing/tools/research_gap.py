"""+b — 사이트맵의 /research/ 글(발행일 10-13 이후) 중 /research 목록 페이지(운영 _article_links)에 없는 글 = 두 소스 모두 못 보는 글.
각 글의 article:published_time·og:type·페이지의 분류 라벨(Engineering 등)을 찍는다(네트워크 읽기만)."""
import re
import urllib.request

from briefing.core.retrieval import sources as src

UA = "Mozilla/5.0 (compatible; briefing-check)"


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310
        return r.read().decode("utf-8", "replace")


xml = get("https://www.anthropic.com/sitemap.xml")
sm = {}
for block in re.findall(r"<url>(.*?)</url>", xml, re.S):
    loc = re.search(r"<loc>\s*(.*?)\s*</loc>", block, re.S)
    mod = re.search(r"<lastmod>\s*(.*?)\s*</lastmod>", block, re.S)
    if loc and "/research/" in loc.group(1):
        sm[loc.group(1).strip().rstrip("/")] = (mod.group(1).strip()[:10] if mod else "")
listing = src._http_get("https://www.anthropic.com/research")
shown = set(u.rstrip("/") for u in src._article_links(listing, "https://www.anthropic.com/research"))
print(f"사이트맵 /research/ {len(sm)}개 · 목록 페이지 링크 {len(shown)}개 · 목록에 없는 글 {len(set(sm) - shown)}개")
recent = sorted([u for u in sm if sm[u] >= "2026-10-13"], key=lambda u: sm[u], reverse=True)
print(f"lastmod ≥ 10-13 인 /research/ 글 {len(recent)}개 중 목록에 없는 글의 발행일 확인(발행 ≥ 10-13 만 표시):")
missed = []
for u in recent:
    if u in shown:
        continue
    html = get(u)
    pub = re.search(r'article:published_time"\s+content="([^"]+)"', html)
    p = pub.group(1)[:10] if pub else "-"
    if p == "-" or p < "2026-10-13":
        continue
    og = re.search(r'property="og:type"\s+content="([^"]+)"', html)
    labels = sorted(set(re.findall(r'>(Engineering|Research|Product|Policy|Alignment|Interpretability|Societal impacts|Economic research)<', html)))
    title = re.search(r"<title>(.*?)</title>", html, re.S)
    missed.append((p, u.split(".com", 1)[-1], og.group(1) if og else "-", labels, (title.group(1) if title else "")[:60]))
for m in sorted(missed, reverse=True):
    print("  ", *m)
print(f"\n목록에 없고 발행 ≥ 10-13 인 글: {len(missed)}개")
