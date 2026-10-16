#!/usr/bin/env python3
"""dedup 감사 — 프로덕션 이력(읽기 전용)으로 기사 신원 dedup 을 검증한다.

두 모드:
- replay: 과거 실발송 카드를 *새 dedup 코드*(article_identity.published_keys)에 날짜순으로 통과시켜
          무엇이 막혔을지 센다 — 머지 게이트(spec §10).
    uv run python scripts/dedup_audit/replay.py replay --until 2026-10-15 --expect-blocked 45 --expect-articles 8
- audit : 실제로 발송된 카드 중 lookback 안의 이전 발송과 같은 기사인 것을 센다 — 배포 후 관측(기대 0).
    uv run python scripts/dedup_audit/replay.py audit --since <배포 다음날>

두 모드 모두 AI Times(쿼리가 기사 ID) 막힘이 0 이어야 PASS. 설계: docs/superpowers/specs/2026-10-16-article-identity-dedup-design.md
"""
from __future__ import annotations

import argparse
import sys
import tempfile
from collections import Counter, defaultdict

import boto3

from briefing.core.article_identity import identity_keys, match_kind, published_keys, url_key
from briefing.core.config import DEFAULT_DEDUP_LOOKBACK_DAYS
from briefing.core.stores.ledger import LocalLedger
from briefing.core.stores.source_store import SourceMeta

REGION = "us-east-1"


def _scan(ddb, name: str, **kw) -> list[dict]:
    t = ddb.Table(name)
    resp = t.scan(**kw)
    out = list(resp["Items"])
    while "LastEvaluatedKey" in resp:
        resp = t.scan(ExclusiveStartKey=resp["LastEvaluatedKey"], **kw)
        out += resp["Items"]
    return out


class _MetaStore:
    """source-store 덤프를 get_meta 로 내주는 읽기 전용 어댑터(published_keys 가 쓰는 인터페이스)."""

    def __init__(self, meta: dict[str, SourceMeta]) -> None:
        self.meta = meta

    def get_meta(self, source_ids):
        return {i: self.meta[i] for i in source_ids if i in self.meta}


def _load(ddb) -> tuple[dict[str, SourceMeta], list[dict]]:
    """(source_id → 메타, 실제로 발송된 브리핑의 PUBLISH 행들)."""
    meta = {i["source_id"]: SourceMeta(url=i.get("url", ""), title=i.get("title", ""), media=i.get("media", ""))
            for i in _scan(ddb, "briefing-source-store", ProjectionExpression="source_id, #u, title, media",
                           ExpressionAttributeNames={"#u": "url"})}
    sent = {(s["user_id"], s["run_date"]) for s in _scan(ddb, "briefing-sent-log") if s.get("status") == "sent"}
    rows = [r for r in _scan(ddb, "briefing-ledger")
            if r.get("decision") == "PUBLISH" and (r["user_id"], r["run_date"]) in sent]
    return meta, rows


def _keys(sid: str, meta: dict[str, SourceMeta]) -> frozenset[str]:
    m = meta.get(sid)
    if m is None:
        return frozenset({f"sid:{sid}"})
    return identity_keys(source_id=sid, url=m.url, title=m.title, media=m.media)


def replay(meta, rows, until: str, lookback: int) -> list[tuple[str, str, str, str]]:
    """막히지 않은 카드만 시뮬레이션 원장에 PUBLISH 로 쌓으며 날짜순 재생(실제 dedup 과 같은 순서·같은 코드)."""
    by_day: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in rows:
        if r["run_date"] <= until:
            by_day[(r["run_date"], r["user_id"])].append(r)
    store, memo, blocked = _MetaStore(meta), {}, []
    with tempfile.TemporaryDirectory() as d:
        sim = LocalLedger(d)
        for rd, uid in sorted(by_day):
            seen = published_keys(sim, store, uid, rd, lookback, memo)
            for r in by_day[(rd, uid)]:
                if kind := match_kind(_keys(r["source_id"], meta), seen):
                    blocked.append((rd, uid, r["source_id"], kind))
                else:
                    sim.append(rd, uid, r["source_id"], r.get("card_key", ""), "PUBLISH", r.get("headline", ""))
    return blocked


def audit(meta, rows, since: str, lookback: int) -> list[tuple[str, str, str, str]]:
    """실제 발송 이력 그대로 — since 이후 카드 중 이전 발송과 같은 기사인 것(=dedup 이 놓친 것)."""
    store, memo, dups = _MetaStore(meta), {}, []
    seen_cache: dict[tuple[str, str], frozenset[str]] = {}
    with tempfile.TemporaryDirectory() as d:
        real = LocalLedger(d)
        for r in rows:
            real.append(r["run_date"], r["user_id"], r["source_id"], r.get("card_key", ""), "PUBLISH", r.get("headline", ""))
        for r in sorted(rows, key=lambda r: (r["run_date"], r["user_id"])):
            if r["run_date"] < since:
                continue
            ck = (r["user_id"], r["run_date"])
            if ck not in seen_cache:
                seen_cache[ck] = published_keys(real, store, r["user_id"], r["run_date"], lookback, memo)
            if kind := match_kind(_keys(r["source_id"], meta), seen_cache[ck]):
                dups.append((r["run_date"], r["user_id"], r["source_id"], kind))
    return dups


def _report(hits, meta, label: str) -> tuple[int, int]:
    """요약 출력 → (AI Times 막힘 수, 서로 다른 기사 수)."""
    print(f"{label}: {len(hits)}장 | 종류별 {dict(Counter(k for *_, k in hits))}")
    aitimes = sum(1 for _, _, sid, _ in hits if sid in meta and meta[sid].media == "AI Times")
    arts = Counter(url_key(meta[sid].url) if sid in meta else sid for _, _, sid, _ in hits)
    print(f"  AI Times: {aitimes} | 서로 다른 기사: {len(arts)}")
    for a, n in arts.most_common():
        print(f"  {n:3}  {a}")
    return aitimes, len(arts)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="기사 신원 dedup 재생·감사(프로덕션 읽기 전용)")
    sub = ap.add_subparsers(dest="mode", required=True)
    rp = sub.add_parser("replay")
    rp.add_argument("--until", required=True)
    rp.add_argument("--expect-blocked", type=int)
    rp.add_argument("--expect-articles", type=int)
    au = sub.add_parser("audit")
    au.add_argument("--since", required=True)
    for p in (rp, au):
        p.add_argument("--lookback", type=int, default=DEFAULT_DEDUP_LOOKBACK_DAYS)
    a = ap.parse_args(argv)

    meta, rows = _load(boto3.resource("dynamodb", region_name=REGION))
    if a.mode == "replay":
        hits = replay(meta, rows, a.until, a.lookback)
        aitimes, n_arts = _report(hits, meta, f"replay(≤{a.until}, lookback {a.lookback}일) 막힘")
        ok = aitimes == 0
        if a.expect_blocked is not None:
            ok = ok and len(hits) == a.expect_blocked
        if a.expect_articles is not None:
            ok = ok and n_arts == a.expect_articles
    else:
        hits = audit(meta, rows, a.since, a.lookback)
        _report(hits, meta, f"audit(≥{a.since}) 실제 중복 발송")
        ok = not hits
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
