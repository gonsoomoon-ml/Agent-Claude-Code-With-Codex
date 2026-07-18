#!/usr/bin/env python
"""measure_latency — 순차(동시성 1) author 지연 실측 = 프로덕션 조건.

A/B 하네스의 지연은 동시 8 실행이라 부풀려진다(pipeline 은 카드를 순차 처리). 배포 전 타임아웃
위험을 판단하려면 **순차** 실측이 필요하다. 프로덕션 미접촉(source-store 읽기만, author 만 호출).
"""
from __future__ import annotations

import statistics
import sys
import time

import boto3

from briefing.core.authoring.author import (
    _parse_card_json,
    _run_author,
    build_system_prompt,
    build_user_prompt,
)
from briefing.core.config import load_settings
from briefing.core.lenses import resolve_lens
from briefing.core.pipeline import _FACT_USER
from briefing.core.stores.source_store import FrozenSource

ADMIN = "445814b8-5001-70a6-84a6-6c010ac347ba"


def _p(*a: object) -> None:
    print(*a, flush=True)


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    settings = load_settings()
    sysp = build_system_prompt(
        lens_guidance=resolve_lens(_FACT_USER.lens).guidance, skill_md=_FACT_USER.skill_md)
    _p(f"프롬프트 v3.1 · author={settings.author_model_id} · system {len(sysp)}자 · 동시성 1(순차)\n")

    ddb = boto3.client("dynamodb", region_name="us-east-1")
    items, kw = [], {}
    while True:
        r = ddb.query(TableName="briefing-ledger", KeyConditionExpression="user_id = :u",
                      ExpressionAttributeValues={":u": {"S": ADMIN}}, **kw)
        items += [{k: list(v.values())[0] for k, v in it.items()} for it in r["Items"]]
        if "LastEvaluatedKey" not in r:
            break
        kw = {"ExclusiveStartKey": r["LastEvaluatedKey"]}

    seen, srcs = set(), []
    for it in items:
        if it["source_id"] in seen:
            continue
        s = ddb.get_item(TableName="briefing-source-store",
                         Key={"source_id": {"S": it["source_id"]}}).get("Item")
        if not s or "text" not in s:
            continue
        seen.add(it["source_id"])
        srcs.append(s["text"]["S"])
    srcs.sort(key=len)
    # 길이 스펙트럼 균등 표본
    pick = [srcs[i * (len(srcs) - 1) // (n - 1)] for i in range(n)] if len(srcs) >= n else srcs

    secs = []
    for i, src in enumerate(pick):
        fs = FrozenSource(f"m{i}", "u", "t", src, "")
        t0 = time.monotonic()
        try:
            card = _parse_card_json(_run_author(sysp, build_user_prompt(fs, today="2026-07-18"), settings))
            el = time.monotonic() - t0
            secs.append(el)
            _p(f"  [{i+1}/{len(pick)}] 원문 {len(src):>5}자 → {el:>5.0f}s · "
               f"요약 {len(card.get('summary','')):>4}자 · claims {len(card.get('claims', []))}")
        except Exception as e:  # noqa: BLE001
            el = time.monotonic() - t0
            _p(f"  [{i+1}/{len(pick)}] 원문 {len(src):>5}자 → {el:>5.0f}s · 실패 {type(e).__name__}: {e}")
    if secs:
        _p(f"\n순차 지연: min {min(secs):.0f}s · median {statistics.median(secs):.0f}s · "
           f"max {max(secs):.0f}s · 평균 {statistics.mean(secs):.0f}s  (프로덕션 한도 240s)")
        _p(f"240s 초과: {sum(1 for s in secs if s > 240)}/{len(secs)}")


if __name__ == "__main__":
    main()
