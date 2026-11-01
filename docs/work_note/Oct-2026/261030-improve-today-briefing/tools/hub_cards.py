"""#7 새 항목(a) — Anthropic News 허브 페이지(/news/announcements·/news/partnerships)가 카드로 발행된 사례의 원자료(읽기 전용 DDB):
URL·동결 본문 길이·날짜·결정·헤드라인·요약·claims 수. 덤으로 Anthropic Engineering 카드 6장의 URL(목록이 /engineering/ 링크를 준 적이 있는지).
usage: BACKEND=dynamo uv run python hub_cards.py
"""
from __future__ import annotations

from briefing.core.authoring.author import PROMPT_VERSION
from briefing.core.config import load_settings
from briefing.core.stores.backends import make_stores
from briefing.core.stores.cache import fact_card_key

USER = "445814b8-5001-70a6-84a6-6c010ac347ba"
HUB_TAILS = {"announcements", "partnerships", "product", "security", "features", "policy", "safeguards"}
ENG_DAYS = ["2026-09-11", "2026-09-25", "2026-09-26", "2026-10-02", "2026-10-06", "2026-10-13"]
HUB_DAYS = ["2026-10-21", "2026-10-28"]
KNOWN_MODELS = ("global.anthropic.claude-sonnet-5-5", "global.anthropic.claude-sonnet-5")
KNOWN_VERSIONS = ("represent-v3.4.2", "represent-v3.4.1", "represent-v3.4", "represent-v3.3")


def load_card(cache, sid, card_key):
    g = cache.get(card_key)
    if g is not None:
        return g
    for m in KNOWN_MODELS:
        for v in dict.fromkeys((PROMPT_VERSION, *KNOWN_VERSIONS)):
            g = cache.get(fact_card_key(sid, m, v))
            if g is not None:
                return g
    return None


def main() -> int:
    settings = load_settings()
    store, cache, ledger = make_stores(settings)
    print("== Anthropic News 허브 카드 ==")
    for rd in HUB_DAYS:
        rows = [r for r in ledger.query(USER, rd) if r.get("run_date") == rd]
        metas = store.get_meta([r["source_id"] for r in rows])
        for r in rows:
            m = metas.get(r["source_id"])
            if not m or m.media != "Anthropic News":
                continue
            tail = m.url.rstrip("/").split("/")[-1]
            if tail not in HUB_TAILS:
                continue
            doc = store.get_source(r["source_id"])
            g = load_card(cache, r["source_id"], r["card_key"])
            print(f"\n[{rd}] {m.url}\n  본문 {len(doc.text)}자 · 결정 {r.get('decision')}")  # SourceMeta 엔 날짜 필드 없음(url·title·media)
            print(f"  headline: {r.get('headline', '')}")
            if g is not None:
                card = g.get("card", g) if isinstance(g, dict) else g
                summary = card.get("summary", "") if isinstance(card, dict) else getattr(card, "summary", "")
                claims = card.get("claims", []) if isinstance(card, dict) else getattr(card, "claims", [])
                print(f"  summary: {str(summary)[:400]}")
                print(f"  claims: {len(claims)}")
            else:
                print("  (card-cache 에서 카드 못 찾음)")
            print(f"  본문 앞 300자: {' '.join(doc.text[:300].split())}")
    print("\n== Anthropic Engineering 카드 URL ==")
    for rd in ENG_DAYS:
        rows = [r for r in ledger.query(USER, rd) if r.get("run_date") == rd]
        metas = store.get_meta([r["source_id"] for r in rows])
        for r in rows:
            m = metas.get(r["source_id"])
            if m and m.media == "Anthropic Engineering":
                print(f"  {rd} {r.get('decision'):8s} {m.url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
