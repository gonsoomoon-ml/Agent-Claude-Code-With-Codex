#!/usr/bin/env python
"""verify_timeout — 재보정한 420s 가 밀집 기사의 *실제 최악* 지연을 덮는지 관측 검증.

240s 에 죽던 것들(밀집=claims 많음)을 다시 돌려 (a) 완료되는지 (b) 420s 안인지 확인.
프로덕션 미접촉. 가장 긴 원문 위주로 표본(= 타임아웃 위험 최상위).
"""
from __future__ import annotations

import json
import time

import boto3

from briefing.core.authoring import author as A
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
    settings = load_settings()
    _p(f"현재 _AUTHOR_TIMEOUT_S = {A._AUTHOR_TIMEOUT_S}s (재보정값)")
    sysp = build_system_prompt(
        lens_guidance=resolve_lens(_FACT_USER.lens).guidance, skill_md=_FACT_USER.skill_md)

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
    # 가장 긴 4개 = 타임아웃 위험 최상위 + 앞서 240s 에 죽은 2478자대
    srcs.sort(key=len, reverse=True)
    dense = srcs[:4] + [s for s in srcs if 2300 <= len(s) <= 2700][:1]

    _p(f"\n밀집 원문 {len(dense)}개 순차 검증 (v3.3 claims 축소 효과 + 안전망 스팟체크):\n")
    worst, dump = 0.0, []
    for i, src in enumerate(dense):
        fs = FrozenSource(f"v{i}", "u", "t", src, "")
        t0 = time.monotonic()
        try:
            card = _parse_card_json(_run_author(sysp, build_user_prompt(fs, today="2026-07-18"), settings))
            el = time.monotonic() - t0
            worst = max(worst, el)
            flag = "✅" if el < A._AUTHOR_TIMEOUT_S else "⚠️"
            _p(f"  {flag} 원문 {len(src):>5}자 → {el:>5.0f}s · claims {len(card.get('claims', []))} · "
               f"요약 {len(card.get('summary', ''))}자")
            dump.append({"src_len": len(src), "secs": round(el), "summary": card.get("summary", ""),
                         "claims": [c.get("text", "") for c in card.get("claims", [])]})
        except Exception as e:  # noqa: BLE001
            el = time.monotonic() - t0
            _p(f"  ❌ 원문 {len(src):>5}자 → {el:>5.0f}s · 실패 {type(e).__name__}")
    _p(f"\n관측 최악 지연 {worst:.0f}s / 한도 {A._AUTHOR_TIMEOUT_S}s")
    out = "/tmp/claude-1000/-home-ubuntu-Agent-Claude-Code-With-Codex/9b743048-a1f7-4874-a47f-b09806167dfd/scratchpad/v33_cards.json"
    import os
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(dump, f, ensure_ascii=False, indent=1)
    _p(f"카드 전문(안전망 대조용): {out}")


if __name__ == "__main__":
    main()
