"""+d dive-in — 팀 페이지 5개의 글 중 메인 /research 목록에 없는 글의 발행일 분포(최근 60일) → 어느 팀이 얼마나 새는지(네트워크 읽기만)."""
import re
import urllib.request

from briefing.core.retrieval import sources as src

UA = "Mozilla/5.0 (compatible; briefing-check)"
TEAMS = ["alignment", "economics", "frontier-red-team", "interpretability", "societal-impacts"]


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310
        return r.read().decode("utf-8", "replace")


main_posts = {u for u in src._article_links(get("https://www.anthropic.com/research"), "https://www.anthropic.com/research")}
cache = {}
for t in TEAMS:
    posts = [u for u in src._article_links(get(f"https://www.anthropic.com/research/team/{t}"), "https://www.anthropic.com/research")]
    not_main = [u for u in posts if u not in main_posts]
    dated = []
    for u in not_main:
        if u not in cache:
            html = get(u)
            pub = re.search(r'article:published_time"\s+content="([^"]+)"', html)
            cache[u] = pub.group(1)[:10] if pub else "-"
        dated.append((cache[u], u.rsplit("/", 1)[-1]))
    recent = sorted([d for d in dated if d[0] >= "2026-09-01"], reverse=True)
    print(f"{t:18s} 글 {len(posts):2d} · 메인에 없음 {len(not_main):2d} · 그중 09-01 이후 발행 {len(recent):2d}: {[f'{d} {s[:28]}' for d, s in recent[:6]]}")
