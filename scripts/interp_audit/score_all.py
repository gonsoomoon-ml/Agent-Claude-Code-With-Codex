# -*- coding: utf-8 -*-
"""네 팔(base·relation·norepeat·beyond) 통합 채점 — 도출가능성 × 근거.

지표 2종:
  ① 도출가능성 — 판정자에게 **요약만** 주고 "이 문단을 요약 독자가 스스로 말할 수 있나". 목표의 정의 그 자체.
  ② 근거 — 문단의 주장이 뒷받침되는가. **팔에 따라 대조 기준이 다르다**:
       base·relation·norepeat = 검증된 claims (그 팔들은 claims 범위 안에서 쓴다)
       beyond                 = **동결 원문** (요약이 버린 것을 쓰는 게 그 팔의 목적이므로 claims 로 재면 부당)

2x2: 도출가능 → 무의미 · 도출불가+근거 → **통찰** · 도출불가+미근거 → 오추론
"""
import json
import os
from collections import Counter
from concurrent.futures import ThreadPoolExecutor


from briefing.core.config import load_settings
from briefing.core.retrieval.relevance_bedrock import _client
from derive_audit import SYSTEM as DERIVE_SYS
from derive_audit import USER as DERIVE_USER

# 중간 산출물(JSON) 보관 위치 — 코드만 저장소에 살고 데이터(수 MB·재생성 가능)는 밖에 둔다.
DATA = os.environ.get("INTERP_AUDIT_DIR", "/tmp/interp-audit")
os.makedirs(DATA, exist_ok=True)

GROUND_SYS = """너는 뉴스 카드의 해석 문단이 **주어진 근거 자료로 뒷받침되는지**만 판정한다.

규칙:
- **적힌 것만 근거다.** 세상 지식으로 그럴듯한지 판단하지 마라.
- 뒷받침된다면 근거 자료에서 해당 부분을 **그대로 인용**하라. 인용 못 하면 뒷받침되지 않는 것이다.
- 표현을 바꾼 것은 문제가 아니다. 애매하면 SUPPORTED 로 답하라.

다음 JSON 하나만 출력하라:
{"verdict": "SUPPORTED" | "LEAP", "quote": "근거 축어 인용 또는 \\"\\"", "leap_step": "LEAP 일 때 어느 지점이 근거를 넘는가"}"""

GROUND_USER = """[근거 자료]
{ground}

[해석 문단]
{why}"""


def main():
    s = load_settings()
    cl = _client(s.region)
    d = json.load(open(f"{DATA}/dataset.json"))
    summ_by, src_by = {}, {}
    for c in d["cards"]:
        summ_by.setdefault(c["headline"][:44], c["summary"])
        if c["source_id"] in d["sources"]:
            src_by.setdefault(c["headline"][:44], d["sources"][c["source_id"]]["text"])
    claims_by = {}
    for c in d["cards"]:
        v = [x["text"] for x in c["claims"] if x["verdict"] == "VERIFIED"]
        if v:
            claims_by.setdefault(c["headline"][:44], v)

    rows = []
    for path in (f"{DATA}/pilot2_rows.json", f"{DATA}/pilot3_rows.json",
                 f"{DATA}/pilot4_rows.json",
                 f"{DATA}/pilot5_rows.json",
                 f"{DATA}/pilot6_rows.json"):
        for r in json.load(open(path)):
            if "error" in r or r["arm"] not in ("base", "relation", "norepeat", "beyond", "beyond2"):
                continue
            if not r["why"].strip() or r["headline"] not in summ_by:
                continue
            rows.append(r)
    print(f"채점 대상 {len(rows)}건 · " + str(dict(Counter(r['arm'] for r in rows))))

    def ask(sysmsg, user, maxtok=400):
        try:
            resp = cl.converse(modelId=s.relevance_model_id, system=[{"text": sysmsg}],
                               messages=[{"role": "user", "content": [{"text": user}]}],
                               inferenceConfig={"maxTokens": maxtok, "temperature": 0})
            t = resp["output"]["message"]["content"][0]["text"]
            i, j = t.find("{"), t.rfind("}")
            return json.loads(t[i:j + 1]) if i >= 0 else {}
        except Exception as e:  # noqa: BLE001
            return {"err": type(e).__name__}

    def score(r):
        dv = ask(DERIVE_SYS, DERIVE_USER.format(summary=summ_by[r["headline"]], why=r["why"]))
        ground = (src_by.get(r["headline"], "")[:7000] if r["arm"] in ("beyond", "beyond2")
                  else "\n".join(f"- {c}" for c in claims_by.get(r["headline"], [])))
        gd = ask(GROUND_SYS, GROUND_USER.format(ground=ground, why=r["why"]), maxtok=500)
        return {**r, "derive": dv, "ground": gd}

    with ThreadPoolExecutor(max_workers=8) as ex:
        out = list(ex.map(score, rows))
    json.dump(out, open(f"{DATA}/score_all.json", "w"), ensure_ascii=False, indent=1)

    print("\n" + "=" * 84)
    print(f"{'팔':<11} {'n':<5} {'무의미(도출가능)':<18} {'통찰(불가+근거)':<18} {'오추론(불가+미근거)':<20}")
    for arm in ("base", "relation", "norepeat", "beyond", "beyond2"):
        sub = [r for r in out if r["arm"] == arm]
        if not sub:
            continue
        cells = Counter()
        for r in sub:
            dv, vd = r["derive"].get("derivable"), r["ground"].get("verdict")
            if dv is True:
                cells["무의미"] += 1
            elif dv is False and vd == "SUPPORTED":
                cells["통찰"] += 1
            elif dv is False and vd == "LEAP":
                cells["오추론"] += 1
            else:
                cells["기타"] += 1
        n = len(sub)
        print(f"{arm:<11} {n:<5} {cells['무의미']}/{n} ({cells['무의미']/n*100:>3.0f}%){'':<8} "
              f"{cells['통찰']}/{n} ({cells['통찰']/n*100:>3.0f}%){'':<8} "
              f"{cells['오추론']}/{n} ({cells['오추론']/n*100:>3.0f}%){'':<8} 기타 {cells['기타']}")

    # ── n=60 대응표본: lens 별 + McNemar ──
    from math import comb
    p6 = {(r["headline"], r["arm"], r["lens"]) for r in json.load(open(f"{DATA}/pilot6_rows.json")) if "error" not in r}
    big = [r for r in out if (r["headline"], r["arm"], r["lens"]) in p6]
    def lab(r):
        dv, vd = r["derive"].get("derivable"), r["ground"].get("verdict")
        return "통찰" if (dv is False and vd == "SUPPORTED") else ("무의미" if dv is True else "오추론" if dv is False else "기타")
    print("\n" + "=" * 84)
    print("── ③ n=60 대응표본 (pilot6) · lens 분리 ──")
    for ln in ("engineer", "business", "전체"):
        sel = [r for r in big if ln == "전체" or r["lens"] == ln]
        by = {}
        for r in sel:
            by.setdefault((r["headline"], r["lens"]), {})[r["arm"]] = lab(r)
        pairs = [v for v in by.values() if "base" in v and "beyond" in v]
        x = sum(1 for v in pairs if v["base"] != "통찰" and v["beyond"] == "통찰")
        y = sum(1 for v in pairs if v["base"] == "통찰" and v["beyond"] != "통찰")
        pv = sum(comb(x + y, k) for k in range(x, x + y + 1)) / 2 ** (x + y) if x + y else 1.0
        for arm in ("base", "beyond"):
            c = Counter(v[arm] for v in pairs)
            n = len(pairs)
            print(f"  {ln:<9} {arm:<8} n={n:<4} 통찰 {c['통찰']}/{n} ({c['통찰']/n*100:>3.0f}%) · "
                  f"무의미 {c['무의미']/n*100:>3.0f}% · 오추론 {c['오추론']/n*100:>3.0f}%")
        print(f"  {'':<9} → McNemar: base→beyond 전이 {x} · 역전 {y} · 단측 p={pv:.4f} "
              f"{'✅ 유의' if pv < 0.05 else '❌ 불충분'}\n")

    print("\n── 통찰 사례(도출불가 + 근거있음) ──")
    shown = 0
    for r in out:
        if (r["derive"].get("derivable") is False and r["ground"].get("verdict") == "SUPPORTED"
                and r["arm"] == "beyond2" and shown < 4):
            shown += 1
            print(f"\n[{r['arm']}·{r['lens']}] {r['headline'][:40]}")
            print(f"  더한 것: {r['derive'].get('added','')[:130]}")
            print(f"  본문: {r['why'][:150]}")
    print(f"\n전문: {DATA}/score_all.json")


if __name__ == "__main__":
    main()
