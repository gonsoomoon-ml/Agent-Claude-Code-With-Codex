"""핵심 3 라벨 재생(10-30 문제 #2 측정) — 최근 run 의 실제 카드로 (현 프롬프트 vs 후보 프롬프트) × (1티어 importance 하한 없음/3/4).

읽기 전용(DDB ledger·card-cache·source-store) + Bedrock 라벨 호출(LABEL_MODEL_ID). 운영 경로 `make_bedrock_labels` 그대로.
usage: BACKEND=dynamo uv run python toppicks_replay.py --since 2026-10-20 --until 2026-10-29 [--dry] [--golden] [--out DIR]
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from collections import Counter
from pathlib import Path

from briefing.core import top_picks as tp
from briefing.core.config import load_settings
from briefing.core.retrieval.sources import CATALOG
from briefing.core.stores.backends import make_stores
from briefing.core.authoring.author import PROMPT_VERSION
from briefing.core.stores.cache import fact_card_key

# 해석층 폴백 카드는 interp 키로 캐시되지 않는데 ledger 는 그 키를 적는다(pipeline.py 242~249) → 사실층 키로 재탐색.
KNOWN_PROMPT_VERSIONS = ("represent-v3.3", "represent-v3.4", "represent-v3.4.1", "represent-v3.4.2")
KNOWN_MODELS = ("global.anthropic.claude-sonnet-5", "global.anthropic.claude-sonnet-5-5",
                "global.anthropic.claude-opus-5-5", "global.anthropic.claude-sonnet-4-6")

USER = "445814b8-5001-70a6-84a6-6c010ac347ba"
FLOORS = (0, 3, 4)

# ── 후보 프롬프트: 분류 정의만 손본다(정책은 코드). 원문에서 문장 치환으로 만들어 나머지(분야 정의)는 그대로.
_OLD_LAUNCH = ('type "launch" = the org announces its own new model, product, platform, general availability or major '
               'feature. ')
_NEW_LAUNCH = ('type "launch" = the org announces its own NEW model, NEW product or service, or general availability of a '
               'platform - something an AI practitioner would call headline news. Incremental features, integrations, '
               'SDK/skill/tool additions, regional expansions, tutorials, how-tos and engineering write-ups are NOT launch - '
               'use "applied" (or "other"). ')
_OLD_OTHER = ('Criticism, lawsuits, court rulings, controversies, leaks, rumors, opinion and analyst '
              'rankings or awards are never launch or policy - use "other" (or "applied" if it fits). ')
_NEW_OTHER = ('Research findings, studies, papers, benchmarks, criticism, lawsuits, court rulings, controversies, leaks, '
              'rumors, opinion and analyst rankings or awards are never launch or policy - use "other" (or "applied" if it '
              'fits). ')
_OLD_IMP = '"importance": <1-5 for an AI practitioner>'
_NEW_IMP = ('"importance": <1-5 for an AI practitioner: 5 = frontier model or flagship product launch by a major lab; '
            '4 = major product, service, GA or major policy decision; 3 = notable feature, partnership or expansion; '
            '2 = incremental feature, integration, tutorial or case study; 1 = minor>')


def candidate_prompt(base: str) -> str:
    for old, new in ((_OLD_LAUNCH, _NEW_LAUNCH), (_OLD_OTHER, _NEW_OTHER), (_OLD_IMP, _NEW_IMP)):
        assert base.count(old) == 1, f"prompt fragment not found once: {old[:40]!r}"
        base = base.replace(old, new)
    return base


def refined_prompt(base: str) -> str:
    """2차 후보: launch 문장 하나만 좁힌다(연구→other·앵커 없음) — 1차 재생에서 효과 있던 레버만."""
    assert base.count(_OLD_LAUNCH) == 1
    return base.replace(_OLD_LAUNCH, _NEW_LAUNCH)


def assign_with_floor(labels: list[dict], secs: list[str], floor: int) -> list[int]:
    """1티어(5대 기업 launch/policy)인데 importance < floor 면 '그 밖'으로 강등한 뒤 현행 assign_top."""
    lbs = copy.deepcopy(labels)
    for lb in lbs:
        if floor and tp.tier(lb) == 1 and tp._importance(lb) < floor:
            lb["type"] = "other"
    return tp.assign_top(lbs, secs, tp.TOP_K)


def load_day_cards(ledger, cache, store, run_date: str, author_model: str = ""):
    rows = [r for r in ledger.query(USER, run_date) if r["run_date"] == run_date]
    metas = store.get_meta([r["source_id"] for r in rows])
    cat_of = {s.name: s.category for s in CATALOG}
    order_of = {s.name: i for i, s in enumerate(CATALOG)}
    items = []
    for r in rows:
        g = cache.get(r["card_key"])
        if g is None and author_model:   # 폴백 카드 → 사실층 키 후보(라벨은 제목·요약만 보므로 동일 입력)
            for m in dict.fromkeys((author_model, *KNOWN_MODELS)):          # 10-25 v62 전 요약 모델 = Sonnet 5
                for v in dict.fromkeys((PROMPT_VERSION, *KNOWN_PROMPT_VERSIONS)):
                    g = cache.get(fact_card_key(r["source_id"], m, v))
                    if g is not None:
                        break
                if g is not None:
                    break
        if g is None:
            items.append({"missing": r["headline"][:60]})
            continue
        m = metas.get(r["source_id"])
        media = getattr(m, "media", "") if m else ""
        items.append({"g": g, "decision": r["decision"], "media": media, "cat": cat_of.get(media, ""),
                      "ord": order_of.get(media, 999)})
    missing = [i["missing"] for i in items if "missing" in i]
    items = [i for i in items if "g" in i]
    items.sort(key=lambda i: (i["ord"], i["g"].card.headline))   # 파이프라인(카탈로그 순)에 가깝게
    return items, missing


def label_day(label_fn, items):
    cards = [i["g"] for i in items]
    secs = [i["cat"] for i in items]
    labels = list(label_fn(cards, secs))
    return cards, secs, sorted(labels, key=lambda lb: lb["n"])


def picks_table(cards, secs, labels):
    pub = [lb for lb in labels if cards[lb["n"]].decision == "PUBLISH"]
    out = {}
    for f in FLOORS:
        idx = assign_with_floor(pub, secs, f)
        by_n = {lb["n"]: lb for lb in labels}
        out[f] = [f"p{tp.tier(by_n[i])}/{tp._importance(by_n[i])} {tp.big_org(by_n[i].get('org', '')) or by_n[i].get('type', '')}: "
                  f"{cards[i].card.headline[:48]}" for i in idx] if len(idx) >= tp.TOP_K else ["(핵심 칸 생략)"]
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", required=True)
    ap.add_argument("--until", required=True)
    ap.add_argument("--dry", action="store_true", help="데이터 로드만(Bedrock 호출 없음)")
    ap.add_argument("--golden", action="store_true", help="후보 프롬프트로 분야 골든 게이트(passes=1)도 돌린다")
    ap.add_argument("--out", default=str(Path(__file__).with_name("toppicks_replay_out")))
    ap.add_argument("--variants", default="current,candidate", help="current,candidate,refined 중 콤마 목록")
    a = ap.parse_args(argv)
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)

    settings = load_settings()
    store, cache, ledger = make_stores(settings)
    from datetime import date, timedelta
    d0, d1 = date.fromisoformat(a.since), date.fromisoformat(a.until)
    days = [(d0 + timedelta(days=i)).isoformat() for i in range((d1 - d0).days + 1)]

    data = {}
    for rd in days:
        items, missing = load_day_cards(ledger, cache, store, rd, settings.author_model_id)
        data[rd] = (items, missing)
        pubs = sum(1 for i in items if i["decision"] == "PUBLISH")
        print(f"{rd}: cards={len(items)} (PUBLISH {pubs}) missing={missing} "
              f"media={dict(Counter(i['media'] for i in items))}")
    if a.dry:
        print("region=", settings.region, "| label model=", __import__('os').environ.get("LABEL_MODEL_ID"))
        return 0

    from briefing.core.retrieval.relevance_bedrock import _label_model, make_bedrock_labels
    label_fn = make_bedrock_labels(settings)
    base_prompt = tp._LABEL_SYSTEM
    prompts = {"current": base_prompt, "candidate": candidate_prompt(base_prompt), "refined": refined_prompt(base_prompt)}
    variants = [v.strip() for v in a.variants.split(",") if v.strip()]
    for v in variants:
        (out / f"{v}_prompt.txt").write_text(prompts[v], encoding="utf-8")
    gate_variant = next((v for v in variants if v != "current"), None)
    print("label model=", _label_model(settings))

    report = {"model": _label_model(settings), "days": {}}
    md = [f"# 핵심 3 재생 — {a.since}~{a.until} · model {_label_model(settings)}", ""]
    for rd in days:
        items, missing = data[rd]
        if len(items) < tp.TOP_MIN_CARDS:
            md.append(f"## {rd} — 카드 {len(items)}장 < {tp.TOP_MIN_CARDS}, 건너뜀"); continue
        day = {"missing": missing, "prompts": {}}
        md.append(f"## {rd} — 카드 {len(items)}장" + (f" (캐시 미스 {len(missing)})" if missing else ""))
        for name, prompt in ((v, prompts[v]) for v in variants):
            tp._LABEL_SYSTEM = prompt
            try:
                cards, secs, labels = label_day(label_fn, items)
            except Exception as err:  # noqa: BLE001
                day["prompts"][name] = {"error": f"{type(err).__name__}: {err}"}
                md.append(f"- **{name}**: 라벨 실패 {type(err).__name__}: {err}"); continue
            rows = [{"n": lb["n"], "media": items[lb['n']]["media"], "decision": cards[lb["n"]].decision,
                     "headline": cards[lb["n"]].card.headline, "org": lb.get("org", ""), "type": lb.get("type", ""),
                     "importance": tp._importance(lb), "event": lb.get("event", ""), "area": lb.get("area", ""),
                     "tier": tp.tier(lb)} for lb in labels]
            pk = picks_table(cards, secs, labels)
            day["prompts"][name] = {"labels": rows, "picks": {str(k): v for k, v in pk.items()}}
            t1 = [r for r in rows if r["tier"] == 1 and r["decision"] == "PUBLISH"]
            md.append(f"### {name} — 1티어 후보 {len(t1)}장")
            for r in sorted(t1, key=lambda r: -r["importance"]):
                md.append(f"- imp {r['importance']} · {tp.big_org(r['org'])} · {r['type']} · [{r['media']}] {r['headline'][:70]}")
            for f in FLOORS:
                md.append(f"- **하한 {f or '없음'}** → " + " | ".join(pk[f]))
            md.append("")
        report["days"][rd] = day
    tp._LABEL_SYSTEM = base_prompt

    if a.golden and gate_variant:
        sys.path.insert(0, str(Path.cwd() / "scripts"))
        from area_eval.run_golden import evaluate, load_golden
        tp._LABEL_SYSTEM = prompts[gate_variant]
        try:
            res = evaluate(load_golden(), label_fn, passes=1)
            report["golden_variant"] = gate_variant
            report["golden_candidate"] = {k: res[k] for k in ("scored", "correct", "accuracy", "gate", "gate_pass",
                                                               "mismatch_boundary", "mismatch_nonboundary", "failures")}
            report["golden_candidate"]["mismatches"] = res["mismatches"]
            md.append(f"## 분야 골든 게이트({gate_variant} 프롬프트, passes=1): {res['correct']}/{res['scored']} = "
                      f"{res['accuracy']:.1%} (게이트 {res['gate']:.0%}) → {'PASS' if res['gate_pass'] else 'FAIL'}; "
                      f"경계 {res['mismatch_boundary']} · 비경계 {res['mismatch_nonboundary']} · 실패 {len(res['failures'])}")
        finally:
            tp._LABEL_SYSTEM = base_prompt

    (out / "replay.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "replay.md").write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
