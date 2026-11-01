"""#7 — 최근 N일 관리자 ledger 의 카드 중 html 리스팅 소스 글의 URL 꼬리·제목을 나열(읽기 전용 DDB).
목록·허브 페이지(Announcements·Partnerships 류)가 카드가 된 사례 식별용 — 꼬리가 짧고 하이픈 없는 **단어**면 "허브 의심" 표시
(Discourse 의 숫자 id 꼬리는 제외).
usage: BACKEND=dynamo uv run python undated_published.py --since 2026-10-21 --until 2026-10-30
"""
from __future__ import annotations

import argparse
from datetime import date, timedelta

from briefing.core.config import load_settings
from briefing.core.retrieval.sources import CATALOG
from briefing.core.stores.backends import make_stores

USER = "445814b8-5001-70a6-84a6-6c010ac347ba"
HTML_MEDIA = {s.name for s in CATALOG if s.kind == "html"}


def looks_like_hub(tail: str) -> bool:
    """짧은 한 단어 슬러그(announcements·partnerships…) = 허브 의심. 숫자 id(Discourse 글 번호)는 글이다."""
    return len(tail) < 16 and "-" not in tail and not tail.isdigit()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", required=True)
    ap.add_argument("--until", required=True)
    a = ap.parse_args(argv)
    settings = load_settings()
    store, cache, ledger = make_stores(settings)
    d0, d1 = date.fromisoformat(a.since), date.fromisoformat(a.until)
    days = [(d0 + timedelta(days=i)).isoformat() for i in range((d1 - d0).days + 1)]
    n = 0
    for rd in days:
        rows = [r for r in ledger.query(USER, rd) if r.get("run_date") == rd]
        metas = store.get_meta([r["source_id"] for r in rows])
        for r in rows:
            m = metas.get(r["source_id"])
            if not m or m.media not in HTML_MEDIA:
                continue
            n += 1
            tail = m.url.rstrip("/").split("/")[-1]
            flag = " ★목록/허브 의심" if looks_like_hub(tail) else ""
            print(f"{rd} {m.media:22s} {r.get('decision', ''):10s} {tail[:50]:50s} {r.get('headline', '')[:50]}{flag}")
    print(f"\nhtml 소스 카드 {n}장")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
