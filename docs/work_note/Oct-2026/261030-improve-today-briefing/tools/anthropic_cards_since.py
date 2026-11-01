"""+b — 관리자 ledger 의 Anthropic Research/Engineering 카드 URL(10-13~10-31) — 어떤 글이 실제로 카드가 됐나(읽기 전용 DDB)."""
from datetime import date, timedelta

from briefing.core.config import load_settings
from briefing.core.stores.backends import make_stores

USER = "445814b8-5001-70a6-84a6-6c010ac347ba"
store, cache, ledger = make_stores(load_settings())
d0 = date(2026, 10, 13)
for i in range(19):
    rd = (d0 + timedelta(days=i)).isoformat()
    rows = [r for r in ledger.query(USER, rd) if r.get("run_date") == rd]
    metas = store.get_meta([r["source_id"] for r in rows])
    for r in rows:
        m = metas.get(r["source_id"])
        if m and m.media in ("Anthropic Research", "Anthropic Engineering"):
            print(f"{rd} {m.media:22s} {r.get('decision', ''):10s} {m.url.replace('https://www.anthropic.com', '')}")
