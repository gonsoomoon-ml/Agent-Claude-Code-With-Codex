"""+d — /research 목록 페이지의 구조: href 분포, 팀 페이지(/research/team/*)가 어떤 글을 링크하는지, 누락 4편이 어디에 있는지(네트워크 읽기만)."""
import re
import urllib.request
from collections import Counter

from briefing.core.retrieval import sources as src

UA = "Mozilla/5.0 (compatible; briefing-check)"
MISSED = ["ecdsa-curve-origins", "attack-surface-reduction", "formal-verification", "discovering-vulnerabilities-with-claude"]


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310
        return r.read().decode("utf-8", "replace")


main = get("https://www.anthropic.com/research")
hrefs = re.findall(r'href="(/[^"#?]*)"', main)
pref = Counter("/".join(h.split("/")[:3]) if h.startswith("/research/team/") else "/".join(h.split("/")[:2]) for h in hrefs)
print(f"/research 페이지 {len(main)//1024}KB · href {len(hrefs)}개 · 접두 분포 {dict(pref.most_common(8))}")
teams = sorted({h for h in hrefs if h.startswith("/research/team/")})
print("팀 페이지 링크:", teams)
main_posts = {u.replace("https://www.anthropic.com", "") for u in src._article_links(main, "https://www.anthropic.com/research")}
print(f"메인 목록의 글 링크 {len(main_posts)}개 · 누락 4편 포함? {[m for m in MISSED if '/research/' + m in main_posts]}")
# 메인 페이지 안의 '더 보기/페이지' 단서
for kw in ("Load more", "load-more", "page=", "?subject", "subject=", "Show more", "See all", "View all"):
    if kw in main:
        print("  메인 페이지 단서:", kw)
allteam = set()
for t in teams:
    html = get("https://www.anthropic.com" + t)
    posts = {u.replace("https://www.anthropic.com", "") for u in src._article_links(html, "https://www.anthropic.com/research")}
    allteam |= posts
    hit = [m for m in MISSED if "/research/" + m in posts]
    print(f"  {t:40s} 글 링크 {len(posts):3d}개 · 메인과 겹침 {len(posts & main_posts):3d} · 누락 4편 중 {len(hit)}: {hit}")
print(f"\n팀 페이지 합집합 {len(allteam)}개 · 메인 ∪ 팀 = {len(allteam | main_posts)}개 (사이트맵 /research/ 는 211개)")
