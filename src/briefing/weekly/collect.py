"""한 주 카드 수집 — 원장(관리자) → 카드 캐시 → 원문 메타. 읽기 전용, 데일리 stores 재사용.

발행일 D(토)의 한 주 = run_date D-7 ~ D-1(토~금). 토 05:00 KST 데일리 run 의 run_date 는 UTC 금요일이다.
② 의 사실은 PUBLISH 카드의 VERIFIED claims 안에서만 쓰므로(README §2), 그 집합을 여기서 함께 넘긴다.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from ..core.authoring.author import Claim


@dataclass(frozen=True)
class WeekCard:
    n: int                        # 1부터 — 프롬프트 · run 로그에서 '#36' 처럼 부르는 번호
    run_date: str
    source_id: str
    card_key: str
    headline: str
    summary: str                  # 캐시 miss 면 빈 값(원장엔 headline 만 남는다)
    why: str
    claims: tuple[Claim, ...]     # 카드의 claims 전부
    verified_ids: tuple[str, ...]  # 그중 certifier 가 VERIFIED 로 판정한 id — ② 인용 가능 집합
    url: str
    title: str
    media: str
    cached: bool                  # 카드 캐시 hit 여부(miss = 제목만 검토 가능)


def week_range(issue_date: str) -> tuple[str, str]:
    """발행일(토) → run_date 범위(직전 토 ~ 금). 예: 2026-11-07 → (2026-10-31, 2026-11-06)."""
    d = date.fromisoformat(issue_date)
    return (d - timedelta(days=7)).isoformat(), (d - timedelta(days=1)).isoformat()


def friday_ready(ledger, user_id: str, issue_date: str) -> bool:
    """재료 마감 확인 — 금요일 run_date(토 05:00 KST run) 원장 행이 있으면 True."""
    fri = week_range(issue_date)[1]
    return any(r["run_date"] == fri for r in ledger.query(user_id, since_date=fri))


def collect(ledger, card_cache, source_store, user_id: str, issue_date: str) -> list[WeekCard]:
    """관리자 원장의 한 주 PUBLISH 행 → WeekCard 목록(run_date · source_id 순, 같은 원문은 첫 날만)."""
    lo, hi = week_range(issue_date)
    rows, seen = [], set()
    for r in sorted(ledger.query(user_id, since_date=lo), key=lambda r: (r["run_date"], r["source_id"])):
        if not (lo <= r["run_date"] <= hi) or r["decision"] != "PUBLISH" or r["source_id"] in seen:
            continue
        seen.add(r["source_id"])
        rows.append(r)
    meta = source_store.get_meta([r["source_id"] for r in rows])
    out = []
    for n, r in enumerate(rows, 1):
        gc = card_cache.get(r["card_key"]) if r["card_key"] else None
        m = meta.get(r["source_id"])
        card = gc.card if gc else None
        out.append(WeekCard(
            n=n, run_date=r["run_date"], source_id=r["source_id"], card_key=r["card_key"],
            headline=card.headline if card else r["headline"],
            summary=card.summary if card else "",
            why=card.why_it_matters if card else "",
            claims=card.claims if card else (),
            verified_ids=tuple(v.claim_id for v in gc.verdicts if v.verdict == "VERIFIED") if gc else (),
            url=m.url if m else "", title=m.title if m else "", media=m.media if m else "",
            cached=gc is not None,
        ))
    return out
