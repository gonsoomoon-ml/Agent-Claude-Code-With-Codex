#!/usr/bin/env python3
"""재보도 dedup 재생 게이트 — 프로덕션 이력(읽기 전용) + 실제 판정자(Haiku)로 drop_rereports 를 다시 돌린다.

run_date 마다: 그 사용자가 실제로 받은 기사(PUBLISH·QUARANTINE)를 생존자로 두고, 기사 페이지를 다시 받아
본문 인용 키(_cited_keys)를 뽑고, 그 run 이전 발송 기록으로 published_keys(url_index=) 를 만든 뒤
drop_rereports(파이프라인과 같은 코드)를 돌려 판정한 쌍·제외 목록을 출력한다. 기대값과 다르면 종료코드 1.

    uv run python scripts/dedup_audit/rereport_replay.py --user-prefix 445814b8 \\
        --since 2026-10-21 --until 2026-10-27 --expect-dropped 10 \\
        --expect-kept-title gitai --expect-kept-title "AAIF에 Agent Skills"

판정자는 temperature 를 고정할 수 없다(Haiku 5.5 거부) — 1건 차이는 1회 재실행, 같은 쌍이 또 갈리면 프롬프트를 의심.
설계: docs/superpowers/specs/2026-10-28-cited-rereport-dedup-design.md §7
"""
from __future__ import annotations

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

import boto3

from briefing.core.article_identity import published_keys
from briefing.core.config import DEFAULT_DEDUP_LOOKBACK_DAYS, load_settings
from briefing.core.rereport_dedup import drop_rereports
from briefing.core.retrieval.relevance_bedrock import make_bedrock_rereport
from briefing.core.retrieval.sources import CATALOG, _cited_keys, _http_get
from briefing.core.stores.dynamo import ledger_from_settings, source_store_from_settings


def _user_id(settings, prefix: str) -> str:
    t = boto3.resource("dynamodb", region_name=settings.region).Table("briefing-users")
    resp = t.scan(ProjectionExpression="user_id")
    ids = [i["user_id"] for i in resp["Items"]]
    while "LastEvaluatedKey" in resp:
        resp = t.scan(ProjectionExpression="user_id", ExclusiveStartKey=resp["LastEvaluatedKey"])
        ids += [i["user_id"] for i in resp["Items"]]
    hits = [i for i in ids if i.startswith(prefix)]
    if len(hits) != 1:
        sys.exit(f"--user-prefix {prefix!r} 가 사용자 {len(hits)}명과 일치 — 정확히 1명이어야 한다")
    return hits[0]


def _days(since: str, until: str) -> list[str]:
    d, end = date.fromisoformat(since), date.fromisoformat(until)
    out = []
    while d <= end:
        out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def _cited(fs) -> tuple[str, ...]:
    html = _http_get(fs.url)
    return _cited_keys(html, fs.url) if html else ()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--user-prefix", required=True)
    ap.add_argument("--since", required=True)
    ap.add_argument("--until", required=True)
    ap.add_argument("--expect-dropped", type=int)
    ap.add_argument("--expect-kept-title", action="append", default=[],
                    help="판정은 받았지만 남아야 하는 B 제목의 부분 문자열(여러 번 가능)")
    args = ap.parse_args()

    settings = load_settings()
    uid = _user_id(settings, args.user_prefix)
    ledger, store = ledger_from_settings(settings), source_store_from_settings(settings)
    judge = make_bedrock_rereport(settings)
    category = {s.name: s.category for s in CATALOG}
    rows = ledger.query(uid)
    print(f"user={uid[:8]}… model={settings.relevance_model_id} rows={len(rows)}")

    meta_memo: dict = {}
    judged: list[tuple[str, object, object, object]] = []   # (run_date, A, B, 판정)
    dropped: set[tuple[str, str]] = set()                    # (run_date, B source_id)
    for d in _days(args.since, args.until):
        sids = sorted({r["source_id"] for r in rows
                       if r.get("run_date") == d and r.get("decision") in ("PUBLISH", "QUARANTINE")})
        survivors = []
        for sid in sids:
            try:
                fs = store.get_source(sid)
            except KeyError:
                continue
            survivors.append((fs, category.get(fs.media, "")))
        if not survivors:
            continue
        with ThreadPoolExecutor(8) as ex:
            cited = {fs.source_id: c for (fs, _), c in zip(survivors, ex.map(lambda x: _cited(x[0]), survivors)) if c}
        sent_index: dict[str, str] = {}
        published_keys(ledger, store, uid, d, DEFAULT_DEDUP_LOOKBACK_DAYS, meta_memo, url_index=sent_index)
        memo: dict = {}   # run 단위 메모(프로덕션과 같음)
        drops = drop_rereports(survivors, cited=cited, sent_index=sent_index, get_source=store.get_source,
                               judge=judge, memo=memo)
        by_sid = {fs.source_id: fs for fs, _ in survivors}
        for (a_sid, b_sid), v in memo.items():
            a = by_sid.get(a_sid) or store.get_source(a_sid)   # 같은 날 A 는 생존자, 과거 A 는 source-store
            judged.append((d, a, by_sid[b_sid], v))
        dropped |= {(d, b) for b in drops}
        print(f"{d}: 생존자 {len(survivors)} · 인용 키 있는 기사 {len(cited)} · 판정 {len(memo)} · 제외 {len(drops)}")

    print()
    for d, a, b, v in judged:
        tag = "DROP" if (d, b.source_id) in dropped else ("FAIL" if v.same is None else "KEEP")
        print(f"{d} {tag:4} {b.media[:16]:16} {b.title[:60]!r}\n{'':16}← {a.media[:16]} {a.title[:56]!r}\n"
              f"{'':16}  {v.reason[:140]}")

    ok = True
    print(f"\n판정한 쌍 {len(judged)} · 제외 {len(dropped)}")
    if args.expect_dropped is not None and len(dropped) != args.expect_dropped:
        print(f"FAIL: 제외 {len(dropped)} ≠ 기대 {args.expect_dropped}")
        ok = False
    for sub in args.expect_kept_title:
        hits = [(d, b) for d, _a, b, _v in judged if sub in b.title]
        if not hits:
            print(f"FAIL: '{sub}' 를 포함한 B 가 판정 쌍에 없다(유지 확인 불가)")
            ok = False
        elif any((d, b.source_id) in dropped for d, b in hits):
            print(f"FAIL: '{sub}' 가 제외됐다(유지돼야 함)")
            ok = False
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
