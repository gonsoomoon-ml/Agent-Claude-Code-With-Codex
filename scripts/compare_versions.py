#!/usr/bin/env python
"""compare_versions — 같은 기사를 layered-v2(배포 직전 프로덕션) vs represent-v3.3(현행)로 대조.

trial 이 만든 v3.3 카드(card-cache)를 하나 골라, 그 동결 원문을 layered-v2 프롬프트로 다시 돌려
before/after 를 나란히 보인다. 프로덕션 미접촉(읽기 + author 1회 호출).
"""
from __future__ import annotations

import json
import re
import subprocess
import time

import boto3

from briefing.core.authoring.author import _parse_card_json, _run_author
from briefing.core.config import load_settings

REGION = "us-east-1"
_V2_COMMIT = "f08b741~1"  # represent-v3 직전 = layered-v2(배포 직전 프로덕션)
_MD = "src/briefing/core/prompts/author_system.md"
_TOK = re.compile(r"[A-Z][A-Za-z0-9.\-]{2,}|\d[\d,.]*")

_V2_LENS = '균형 잡힌 일반 독자 관점. 핵심 사실과 "왜 중요한가"를 간결히.'
_V2_CONTRACT = (
    "## 출력 형식 (JSON only)\n"
    "다음 JSON object *하나*만 출력하라(코드펜스·여는 설명 금지):\n"
    '{"summary": "...", "why_it_matters": "...", '
    '"claims": [{"id": "C1", "text": "...", "claim_type": "arithmetic|entailment", '
    '"importance": "core|supporting"}]}\n'
    "제목(headline)은 만들지 마라 — 카드 제목은 기사 원제목을 그대로 쓴다(사실층 앵커, 재프레이밍 금지).\n"
    "claims 는 원자적(독립 검증 단위). 숫자/날짜/% 포함이면 claim_type=arithmetic, 그 외 entailment. 애매하면 arithmetic.\n"
    "importance: summary 또는 why_it_matters 를 직접 뒷받침하면 core, 그 외 supporting."
)


def _v2_system() -> str:
    md = subprocess.run(["git", "show", f"{_V2_COMMIT}:{_MD}"], capture_output=True, text=True,
                        check=True).stdout.strip()
    return "\n\n".join([md, "## 요약 관점(lens)\n" + _V2_LENS, _V2_CONTRACT])


def _v2_user(src: str, today: str) -> str:
    return (f"오늘 날짜: {today} (상대 날짜는 이 기준; 원문에 없는 날짜 생성 금지).\n\n"
            f"다음 동결 원문을 요약하고 원자적 claims 를 추출하라:\n\n{src}")


def _depth(src: str, text: str) -> float | None:
    pos = [src.find(a) / max(1, len(src)) for a in {m.group() for m in _TOK.finditer(text)} if src.find(a) >= 0]
    return max(pos) if pos else None


def _sents(t: str) -> int:
    return len([s for s in re.split(r"(?<=[.?!다])\s+", t.strip()) if len(s) > 5])


def main() -> None:
    settings = load_settings()
    ddb = boto3.client("dynamodb", region_name=REGION)
    # 가장 최근(ttl 최대) v3.3 카드 중, 원문이 source-store 에 있고 밀집(≥3000자)인 것 하나
    items, kw = [], {}
    while True:
        r = ddb.scan(TableName="briefing-card-cache", **kw)
        items += r["Items"]
        if "LastEvaluatedKey" not in r:
            break
        kw = {"ExclusiveStartKey": r["LastEvaluatedKey"]}
    items.sort(key=lambda it: int(it.get("ttl", {}).get("N", "0")), reverse=True)

    for it in items[:60]:
        p = json.loads(it["card_json"]["S"])
        c = p["card"]
        sid = c.get("source_id", "")
        s = ddb.get_item(TableName="briefing-source-store", Key={"source_id": {"S": sid}}).get("Item")
        if not s or "text" not in s:
            continue
        src = s["text"]["S"]
        if len(src) < 3000:
            continue
        # 이 카드로 대조
        print(f"{'=' * 90}\n■ 기사: {c.get('headline', '')}\n원문 {len(src)}자\n{'=' * 90}\n")

        v33_sum, v33_cl = c.get("summary", ""), c.get("claims", [])
        print("▼ [layered-v2] 배포 직전 프로덕션 — 실행 중…", flush=True)
        t0 = time.monotonic()
        v2 = _parse_card_json(_run_author(_v2_system(), _v2_user(src, "2026-07-18"), settings))
        v2s = time.monotonic() - t0
        v2_sum, v2_cl = v2.get("summary", ""), v2.get("claims", [])

        for name, summ, cl, secs in [("layered-v2 (구 프로덕션)", v2_sum, v2_cl, v2s),
                                     ("represent-v3.3 (배포됨)", v33_sum, v33_cl, None)]:
            d = _depth(src, summ)
            print(f"\n── {name} ──")
            print(f"   요약 {len(summ)}자 · {_sents(summ)}문장 · claims {len(cl)} · "
                  f"앵커 최심 {d if d is None else round(d, 2)}" + (f" · {secs:.0f}s" if secs else ""))
            print(f"   요약: {summ}")
        return
    print("적합한 밀집 v3.3 카드를 못 찾음")


if __name__ == "__main__":
    main()
