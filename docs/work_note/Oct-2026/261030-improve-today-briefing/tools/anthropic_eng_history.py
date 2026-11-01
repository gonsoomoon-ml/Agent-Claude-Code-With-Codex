"""#7 새 항목(b) — anthropic-eng(Anthropic Engineering) 소스가 언제부터 0건인지: 관리자 ledger 를 날짜별로 훑어 media 별 카드 수를
센다(읽기 전용 DDB). 비교용으로 다른 html 소스(anthropic·claude-blog·anthropic-research)도 같이 센다.
usage: BACKEND=dynamo uv run python anthropic_eng_history.py --since 2026-09-01 --until 2026-10-30
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import date, timedelta

from briefing.core.config import load_settings
from briefing.core.retrieval.sources import CATALOG
from briefing.core.stores.backends import make_stores

USER = "445814b8-5001-70a6-84a6-6c010ac347ba"
WATCH = {s.name for s in CATALOG if s.kind == "html"}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", required=True)
    ap.add_argument("--until", required=True)
    a = ap.parse_args(argv)
    settings = load_settings()
    store, cache, ledger = make_stores(settings)
    d0, d1 = date.fromisoformat(a.since), date.fromisoformat(a.until)
    days = [(d0 + timedelta(days=i)).isoformat() for i in range((d1 - d0).days + 1)]
    per_day: dict[str, Counter] = defaultdict(Counter)
    last_seen: dict[str, str] = {}
    eng_cards: list[tuple[str, str, str]] = []
    for rd in days:
        rows = [r for r in ledger.query(USER, rd) if r.get("run_date") == rd]
        if not rows:
            continue
        metas = store.get_meta([r["source_id"] for r in rows])
        for r in rows:
            m = metas.get(r["source_id"])
            if not m or m.media not in WATCH:
                continue
            per_day[rd][m.media] += 1
            last_seen[m.media] = rd
            if m.media == "Anthropic Engineering":
                eng_cards.append((rd, r.get("decision", ""), r.get("headline", "")[:70]))
    medias = sorted(WATCH)
    print("run_date   " + " ".join(f"{m[:14]:>14s}" for m in medias))
    for rd in days:
        if rd in per_day:
            print(f"{rd} " + " ".join(f"{per_day[rd].get(m, 0):>14d}" for m in medias))
    print("\n마지막으로 카드가 나온 날:", {m: last_seen.get(m, "없음") for m in medias})
    print(f"\nAnthropic Engineering 카드 {len(eng_cards)}장:")
    for rd, dec, h in eng_cards:
        print(f"  {rd} {dec:10s} {h}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
