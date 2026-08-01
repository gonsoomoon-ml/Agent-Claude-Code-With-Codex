# -*- coding: utf-8 -*-
"""dataset.json 생성 — 프로덕션 DDB(card-cache · source-store)에서 감사용 코퍼스를 뽑는다.

**읽기 전용**: Scan 만 한다. 캐시·원장·발송 어디에도 쓰지 않는다.

왜 필요한가: 해석층 실험은 *실제로 발행된* 카드와 그 동결 원문을 재료로 써야 한다(합성 입력으로는
lead bias·요약 커버리지 같은 진짜 실패 유형이 재현되지 않는다).

⚠️ 2026-08-01 변경: source-store 의 7일 TTL 이 폐지되어 **원문은 이제 영구 보존된다** → 소급 감사가 가능하다.
   단 **card-cache 는 여전히 30일 TTL** 이므로 카드(요약·해석·claims·verdict)는 30일이 지나면 사라진다.
   즉 조인의 병목이 원문에서 카드로 옮겨갔다 — 여전히 그때그때 떠 두는 게 안전하다.
   (2026-08-01 이전 7일 창에서 만료된 원문은 복구 불가 — 그 기간 카드는 `원문 조인 가능` 수가 낮게 나온다.)

산출 형태:
  {"cards":   [{cache_key, source_id, headline, summary, why, decision, claims[], variants_for_source}],
   "sources": {source_id: {url, title, text, media, fetched_at}}}

claims[] = Claim 필드 + certifier verdict 를 조인한 것(`verdict`: VERIFIED|DEMOTED|BLOCKED…).
variants_for_source = 같은 source_id 를 가진 캐시 항목 수 — 2 이상이면 사실층 + 해석층 변형이 함께 있다는 뜻
(`interp_card_key` 는 lens 별로 갈리므로 lens 수만큼 늘어난다).

usage: uv run python scripts/interp_audit/build_dataset.py
       INTERP_AUDIT_DIR=/some/dir uv run python scripts/interp_audit/build_dataset.py
"""
import json
import os
from collections import Counter

import boto3

from briefing.core.config import load_settings
from briefing.core.stores.cache import _deserialize

# 중간 산출물(JSON) 보관 위치 — 코드만 저장소에 살고 데이터(수 MB·재생성 가능)는 밖에 둔다.
DATA = os.environ.get("INTERP_AUDIT_DIR", "/tmp/interp-audit")
os.makedirs(DATA, exist_ok=True)


def _scan(table):
    """전체 Scan(페이지네이션 포함). 테이블이 작아서(수백~수천 항목) Scan 이 적절하다."""
    items, kw = [], {}
    while True:
        page = table.scan(**kw)
        items += page.get("Items", [])
        if not page.get("LastEvaluatedKey"):
            return items
        kw["ExclusiveStartKey"] = page["LastEvaluatedKey"]


def main():
    s = load_settings()
    ddb = boto3.resource("dynamodb", region_name=s.region) if s.region else boto3.resource("dynamodb")

    sources = {}
    for it in _scan(ddb.Table(s.source_table)):
        sources[it["source_id"]] = {k: it.get(k, "") for k in
                                    ("url", "title", "text", "media", "fetched_at")}
    print(f"sources {len(sources)}  (source-store TTL 7일 — 이 시점 스냅샷)")

    cards, skipped = [], 0
    for it in _scan(ddb.Table(s.cache_table)):
        try:
            g = _deserialize(json.loads(it["card_json"]))
        except Exception:       # noqa: BLE001 — 구 스키마 캐시 항목은 건너뛴다(캐시는 disposable)
            skipped += 1
            continue
        verdict_of = {v.claim_id: v.verdict for v in g.verdicts}
        cards.append({
            "cache_key": it["cache_key"],
            "source_id": g.card.source_id,
            "headline": g.card.headline,
            "summary": g.card.summary,
            "why": g.card.why_it_matters,
            "based_on": list(g.card.based_on),
            "decision": g.decision,
            # 키 이름 `type`(≠ 필드명 `claim_type`)은 소비자(pilot.load_sample)와 맞춘 계약이다.
            "claims": [{"id": c.id, "text": c.text, "type": c.claim_type,
                        "importance": c.importance,
                        "verdict": str(verdict_of.get(c.id, ""))} for c in g.card.claims],
        })

    per_source = Counter(c["source_id"] for c in cards)
    for c in cards:
        c["variants_for_source"] = per_source[c["source_id"]]

    out = f"{DATA}/dataset.json"
    json.dump({"cards": cards, "sources": sources}, open(out, "w"),
              ensure_ascii=False, indent=1)
    joinable = sum(1 for c in cards if c["source_id"] in sources)
    print(f"cards {len(cards)} (구스키마 건너뜀 {skipped}) · 원문 조인 가능 {joinable}")
    print(f"decision {dict(Counter(c['decision'] for c in cards))}")
    print(f"→ {out}")


if __name__ == "__main__":
    main()
