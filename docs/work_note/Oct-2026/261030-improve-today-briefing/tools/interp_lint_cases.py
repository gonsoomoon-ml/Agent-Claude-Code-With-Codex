"""#6 해석층 lint 폴백(미검증 수치 밀수) 사례 분류 — WARN 의 '밀수 토큰'이 정말 원문·검증 claim 에 없는 수치인지(읽기 전용).

분류: 토큰마다 (a) gate._num_tokens(원문 ∪ VERIFIED claims) 에 없음(= lint 기준, 당연히 True) ·
(b) 값 기준(numeric.scan — '96.2 percent'·'163 million'·'ten' 같은 다른 표기)으로는 원문/claim 에 있음 → 표기 불일치(오탐 후보)
(c) 둘 다 없음 → 해석이 새로 만든(또는 계산한) 수치 = 진짜 밀수.
usage: BACKEND=dynamo uv run python interp_lint_cases.py --since 2026-10-21 --until 2026-10-30
"""
from __future__ import annotations

import argparse
import re
from datetime import date, timedelta

from briefing.core import gate
from briefing.core.authoring.author import PROMPT_VERSION
from briefing.core.config import load_settings
from briefing.core.stores.backends import make_stores
from briefing.core.stores.cache import fact_card_key
from briefing.core.verification import numeric

USER = "445814b8-5001-70a6-84a6-6c010ac347ba"
KNOWN_PROMPT_VERSIONS = ("represent-v3.3", "represent-v3.4", "represent-v3.4.1", "represent-v3.4.2")
KNOWN_MODELS = ("global.anthropic.claude-sonnet-5-5", "global.anthropic.claude-sonnet-5",
                "global.anthropic.claude-opus-5-5", "global.anthropic.claude-sonnet-4-6")

# CloudWatch `[WARN gate interp] <sid[:12]>: lint 실패(미검증 수치 밀수 [...])` 2026-10-21~30 (시험 발송 포함, 카드당 1회)
CASES: dict[str, list[str]] = {
    "3852ae9ca8a4": ["1"], "2e14da66e724": ["10.22%", "11.79%", "13.53%", "28.48%", "30.50%", "6.48%"],
    "f1863f9354f6": ["49"], "ee71b9406d7c": ["6"], "3276ddf83745": ["55%", "85%"], "017f49924e18": ["70"],
    "116bfc4b1582": ["8"], "4e1c193a3c8b": ["10%", "163"], "73cf71306cc7": ["10"], "c91d595b3576": ["20", "9"],
    "6f0a0c2bc1e9": ["1", "3", "4"], "840443b20a3f": ["3", "96.2%", "98.8%"], "f15d256314dc": ["90%"],
    "13bd5dc70d68": ["1", "4"], "942db1453b32": ["4"], "31c69a33ebf8": ["23.8%", "30.8%"], "89864af537b0": ["64%"],
    "514a9809df4c": ["1"], "eae1e69b90b6": ["11", "8"], "d2102f7278dc": ["10%", "20%"],
}


def tok_value(tok: str) -> tuple[float, bool]:
    pct = tok.endswith("%")
    return float(tok.rstrip("%").replace(",", "")), pct


def value_in(text: str, tok: str) -> str:
    """값 기준으로 원문/claim 에 있나 — 있으면 어떤 표기로 있는지 한 조각."""
    v, pct = tok_value(tok)
    n = numeric.scan(text)
    pool = set(n.percents) if pct else set(n.values)
    if not numeric.contains(v, pool) and not numeric.contains(v, set(n.values) | set(n.percents)):
        return ""
    base = tok.rstrip("%")
    for pat in (re.escape(base) + r"\s*(?:%|percent|퍼센트|프로)", re.escape(base) + r"[^\d]", r"\b" + re.escape(base) + r"\b"):
        m = re.search(pat, text)
        if m:
            s = max(0, m.start() - 40)
            return "…" + " ".join(text[s:m.end() + 40].split()) + "…"
    return "(값은 있으나 표기 미상 — 말로 쓴 수?)"


def load_card(cache, sid, card_key, author_model):
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
    found = {}
    for rd in days:
        for r in ledger.query(USER, rd):
            if r.get("run_date") != rd:
                continue
            p = r["source_id"][:12]
            if p in CASES and p not in found:
                found[p] = (rd, r)
    print(f"찾음 {len(found)}/{len(CASES)} · 못 찾음 = {[p for p in CASES if p not in found]}\n")
    tally = {"표기 불일치(값은 원문/claim 에 있음)": 0, "진짜 새 수치": 0}
    for p, (rd, r) in found.items():
        sid = r["source_id"]
        g = load_card(cache, sid, r["card_key"], settings.author_model_id)
        src = store.get_source(sid).text
        claims_txt = " ".join(c.text for c in gate.verified_claims(g)) if g else ""
        print("=" * 100)
        print(f"[{rd}] {p} · {r.get('decision')} · {r.get('headline', '')[:70]} · VERIFIED claims {len(gate.verified_claims(g)) if g else '?'}")
        for tok in CASES[p]:
            in_lint = tok in (gate._num_tokens(src) | gate._num_tokens(claims_txt))
            where = value_in(src, tok) or (("[claim] " + value_in(claims_txt, tok)) if value_in(claims_txt, tok) else "")
            kind = "표기 불일치(값은 원문/claim 에 있음)" if where else "진짜 새 수치"
            tally[kind] += 1
            print(f"  {tok:8s} lint토큰에 있음={in_lint!s:5s} → {kind}: {where[:150]}")
    print("\n집계:", tally)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
