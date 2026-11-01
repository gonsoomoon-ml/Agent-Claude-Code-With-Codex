"""+b — /engineering 페이지(JS 셸)가 링크하는 /research/ 글 43개의 발행일을 받아, 10-13 이후 글이 몇 개이고 그중 /research 목록 페이지(22링크)에
보이는 것이 몇 개인지(= anthropic-research 소스가 받을 수 있는지) 센다(네트워크 읽기만)."""
import re
import urllib.request

from briefing.core.retrieval import sources as src

UA = "Mozilla/5.0 (compatible; briefing-check)"


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310
        return r.read().decode("utf-8", "replace")


eng_html = get("https://www.anthropic.com/engineering")   # JS 모음 페이지지만 정적 HTML 에 /research/ 링크가 있다
eng = sorted(set(re.findall(r'href="(/research/[a-zA-Z0-9-]+)"', eng_html)))
listing = src._http_get("https://www.anthropic.com/research")
shown = {u.replace("https://www.anthropic.com", "").rstrip("/") for u in src._article_links(listing, "https://www.anthropic.com/research")}
print(f"/engineering 페이지의 /research/ 링크 {len(eng)}개 · /research 목록 페이지 링크 {len(shown)}개 · 겹침 {len(set(eng) & shown)}개")
rows = []
for path in eng:
    html = get("https://www.anthropic.com" + path)
    pub = re.search(r'article:published_time"\s+content="([^"]+)"', html)
    title = re.search(r"<title>(.*?)</title>", html, re.S)
    rows.append((pub.group(1)[:10] if pub else "-", path, path in shown, (title.group(1) if title else "").split("\\")[0].strip()[:55]))
rows.sort(reverse=True)
print("\n발행일순(상위 15):")
for p, path, in_listing, t in rows[:15]:
    print(f"  {p}  {'목록O' if in_listing else '목록X'}  {path[10:50]:40s} {t}")
since = [r for r in rows if r[0] >= "2026-10-13"]
print(f"\n10-13 이후 발행된 엔지니어링 글 {len(since)}개 · 그중 /research 목록 페이지에 보임 {sum(1 for r in since if r[2])}개 · 안 보임 {sum(1 for r in since if not r[2])}개")
for p, path, in_listing, t in since:
    print(f"  {p}  {'목록O' if in_listing else '목록X'}  {path}")
