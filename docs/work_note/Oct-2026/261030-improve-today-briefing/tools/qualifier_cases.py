"""#5 수식어 탈락(qualifier_dropped) 사례 복원 — 그림자 검사 WARN 의 카드 14장을 ledger·card-cache·source-store 에서 찾아
요약 문장 · 그 숫자를 담은 claim · 원문 문장을 나란히 보여 준다(읽기 전용). 어디서 한정어가 빠졌는지(요약만 / claim 도) 보기 위함.

usage: BACKEND=dynamo uv run python qualifier_cases.py --since 2026-10-21 --until 2026-10-30
"""
from __future__ import annotations

import argparse
import re
from datetime import date, timedelta

from briefing.core import quality_checks as qc
from briefing.core.authoring.author import PROMPT_VERSION
from briefing.core.config import load_settings
from briefing.core.stores.backends import make_stores
from briefing.core.stores.cache import fact_card_key
from briefing.core.verification import numeric

USER = "445814b8-5001-70a6-84a6-6c010ac347ba"
KNOWN_PROMPT_VERSIONS = ("represent-v3.3", "represent-v3.4", "represent-v3.4.1", "represent-v3.4.2")
KNOWN_MODELS = ("global.anthropic.claude-sonnet-5-5", "global.anthropic.claude-sonnet-5",
                "global.anthropic.claude-opus-5-5", "global.anthropic.claude-sonnet-4-6")

# CloudWatch `[WARN quality shadow] <sid[:12]> qualifier_dropped: <값>(<원문 한정어>)` 최근 10일(2026-10-21~30)
CASES: dict[str, list[float]] = {
    "017f49924e18": [1e8], "37f741efcbd9": [1e7], "3852ae9ca8a4": [2.5e8], "4e1c193a3c8b": [5], "4e3ec60a3cb7": [20],
    "514a9809df4c": [1e5], "537e4434b934": [5e10], "624b77d71767": [8e5], "8a9b4d480ea5": [2.3e5], "94d9cdc408e5": [2.5e5],
    "9a8c6b7979b3": [5.719], "9d831b4a8381": [86900], "e6d93240877a": [4e5], "eeb275d02b83": [25000, 1e7],
}

_SENT = re.compile(r"(?<=[.!?。])\s+|(?<=다\.)\s+|\n+")


def sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENT.split(text or "") if s.strip()]


def has_value(text: str, v: float) -> bool:
    n = numeric.scan(text)
    return numeric.contains(v, set(n.values) | set(n.percents))


def load_card(cache, sid: str, card_key: str, author_model: str):
    g = cache.get(card_key)
    if g is not None:
        return g
    for m in dict.fromkeys((author_model, *KNOWN_MODELS)):
        for v in dict.fromkeys((PROMPT_VERSION, *KNOWN_PROMPT_VERSIONS)):
            g = cache.get(fact_card_key(sid, m, v))
            if g is not None:
                return g
    return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", required=True)
    ap.add_argument("--until", required=True)
    a = ap.parse_args(argv)
    settings = load_settings()
    store, cache, ledger = make_stores(settings)
    d0, d1 = date.fromisoformat(a.since), date.fromisoformat(a.until)
    days = [(d0 + timedelta(days=i)).isoformat() for i in range((d1 - d0).days + 1)]

    found: dict[str, tuple[str, dict]] = {}
    for rd in days:
        for r in ledger.query(USER, rd):
            if r.get("run_date") != rd:
                continue
            p = r["source_id"][:12]
            if p in CASES and p not in found:
                found[p] = (rd, r)
    missing = [p for p in CASES if p not in found]
    print(f"찾음 {len(found)}/{len(CASES)} · 못 찾음(관리자 ledger 밖) = {missing}\n")

    for p, (rd, r) in found.items():
        sid = r["source_id"]
        g = load_card(cache, sid, r["card_key"], settings.author_model_id)
        fs = store.get_source(sid)
        src_text = getattr(fs, "raw_text", None) or getattr(fs, "text", "") or ""
        print("=" * 100)
        print(f"[{rd}] {p} · {r.get('decision')} · {r.get('headline', '')[:70]}")
        if g is None:
            print("  (card-cache 에 카드 없음)")
            continue
        card = g.card
        for v in CASES[p]:
            print(f"  ── 값 {v:g}")
            for s in sentences(card.summary):
                if has_value(s, v):
                    print(f"  요약 : {s}")
            cl = [c for c in card.claims if has_value(c.text, v)]
            if not cl:
                print("  claim: (이 값을 담은 claim 없음)")
            for c in cl:
                vd = next((x for x in getattr(g, "verdicts", []) if getattr(x, "claim_id", None) == c.id), None)
                st = f"{getattr(vd, 'status', '?')}/{getattr(vd, 'method', '?')}" if vd else "?"
                print(f"  claim: [{c.claim_type}·{st}] {c.text}")
            hits = [s for s in sentences(src_text) if has_value(s, v)]
            for s in hits[:3]:
                print(f"  원문 : {s[:260]}")
            if not hits:
                # 문장 분리가 안 된 긴 본문 — 숫자 주변 160자
                for m in re.finditer(r"\d[\d,\.]*", src_text):
                    if has_value(src_text[max(0, m.start() - 30):m.end() + 12], v):
                        print(f"  원문~: …{src_text[max(0, m.start() - 120):m.end() + 60]}…")
                        break
            # 그림자 검사 재현(현 코드) — 운영 로그와 같은 결과인지
        print(f"  shadow(now): {[f'{f.check}: {f.detail}' for f in qc.shadow_checks(card, src_text) if f.check == 'qualifier_dropped']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
