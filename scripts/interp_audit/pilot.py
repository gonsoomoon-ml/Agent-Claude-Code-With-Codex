# -*- coding: utf-8 -*-
"""해석층 계약 후보 파일럿 — 소규모 스크리닝(게이트 아님).

목적: 명백히 깨지는 후보를 **싸게 탈락**시키고, 눈에 띄게 다른 산출이 나오는지 본다.
n=6 은 통계적 판정에 못 쓴다(McNemar: n=20 도 15pt 검출 불가) — 여기서 하는 일은
① 후보가 계약을 지키는가 ② 날조·폼레터 같은 즉시 탈락 사유가 있는가 ③ 문장이 실제로 달라지는가.

usage: uv run python scripts/interp_audit/pilot.py [N] [arm,arm] [lens,lens]
       기본: 12기사 × (base,struct+sil,counterfact,conditional) × (engineer,business)
       PILOT_OUT=… 로 산출 경로 지정(기본 $INTERP_AUDIT_DIR/pilot2_rows.json)
"""
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor


import briefing.core.authoring.author as A
from briefing.core.authoring.author import (
    _parse_interp, _run_author, build_interp_system_prompt, build_interp_user_prompt,
)
from briefing.core.config import load_settings
from briefing.core.lenses import resolve_lens
from briefing.core.stores.source_store import FrozenSource

# 중간 산출물(JSON) 보관 위치 — 코드만 저장소에 살고 데이터(수 MB·재생성 가능)는 밖에 둔다.
DATA = os.environ.get("INTERP_AUDIT_DIR", "/tmp/interp-audit")
os.makedirs(DATA, exist_ok=True)

A._AUTHOR_TIMEOUT_S = 300

# ── 후보 계약 조각 ────────────────────────────────────────────────────────────
# 현행(base) 계약의 "## lens 가 정하는 것" 절 **앞**에 삽입된다. 전부 **금지문·허가문·형식 지시**로,
# 입력 크기에 비례하는 포함 명령은 없다(2026-07-27 지연 참사 형태 회피).

STRUCT = """
## 산출 구조 (반드시 이 세 가지를 이 순서로 한 단락에 녹여 쓴다)
1) **무엇이 달라졌나** — 제공된 claim 중 **하나만** 지목해 그 변화를 쓴다.
2) **독자의 무엇에 닿나** — 독자가 실제로 다루는 대상(코드·설정·비용·의사결정)을 지목한다.
   "업계는", "기업들은" 같은 무주체 주어 금지.
3) **그래서 무엇을** — 독자가 확인하거나 정할 수 있는 것을 **동사로 끝맺는다**.
라벨·번호·소제목을 노출하지 마라 — 읽으면 한 단락이어야 한다.
"""

SILENCE = """
## 침묵 허가 (중요)
위 세 가지를 원문 근거로 채울 수 없으면 **why_it_matters 를 빈 문자열로 두어라.**
억지로 채운 한 단락은 빈칸보다 나쁘다 — 독자는 검증 배지가 붙은 카드에서 그것을 읽는다.
"""

COUNTERFACT = """
## 반사실 검사 (스스로 적용하라)
쓴 문단을 **다른 기사에 붙였을 때도 말이 된다면 그것은 이 기사의 해석이 아니다.**
다른 기사에 붙이면 틀린 말이 되도록, 이 기사에 고유한 조건·수치·메커니즘·제약을 문장 안에 넣어라.
"""

CONDITIONAL = """
## 조건부 함의 (외삽을 숨기지 말고 드러내라)
독자 상황을 가정해야 한다면 그 가정을 **문장 안에 명시**하라 — 「당신의 X가 Y라면, …」 형태.
★ 조건은 **독자의 절반쯤은 "아니오"라고 답할 만한 것**이어야 한다. 이 lens 를 고른 독자라면
누구나 참인 조건("당신이 엔지니어라면", "AI 도구를 쓴다면")은 정보가 0이므로 쓰지 마라 —
구체적인 기술·규모·제약·현재 상태를 조건으로 걸어라.
가정할 것이 없으면 조건절 없이 쓴다(억지 조건 금지).
"""

TRUNC = ("\n※ 아래 동결 원문은 길이 상한에서 **잘렸을 수 있다**. 문장이 중간에서 끝나면 그 뒤를 "
         "추정하지 말고, 완전히 진술된 부분만 근거로 삼아라.\n")


RELATION = """
## 무엇에 대해 쓰는가 (이 절이 다른 지시보다 우선한다)
**독자에 대해 쓰지 마라 — 너는 독자를 모른다.** 대신 **검증된 claims 사이의 관계**를 써라.
요약은 사실을 하나씩 나열한다. 여러 사실을 **함께 놓았을 때만 보이는 것**이 있고, 그것이 이 문단의 몫이다.

관계의 예(이 목록에 없는 관계도 좋다):
- 귀속 — 어떤 수치가 누구의 자체 측정인가, 독립 검증이 있는가
- 범위 — 어떤 조건에서 얻은 결과가 어디까지 일반화됐는가
- 부재 — 있어야 할 비교 기준·조건·시점이 claims 에 없다
- 의존 — 이 이점이 성립하려면 무엇이 이미 참이어야 하는가
- 시점 — 발표 시점과 실제 가용 시점이 다른가

**두 개 이상의 claim 을 엮어라.** 하나만으로 되는 말은 요약이 이미 했다.
lens 는 *어떤 관계를 고를지*만 정한다 — 문장이 독자를 호명하지 않는다("당신이 ~라면" 금지).
엮을 관계가 없으면 why_it_matters 를 **빈 문자열**로 두어라. 없는 관계를 만들어내지 마라.
"""


# ── ① 재료를 바꾼다 — 인터프리터에게 **요약을 보여준다** ────────────────────────
# 지금 인터프리터는 자기가 무엇을 반복하는지 모른다(요약 문자열을 못 받는다).
# 실측: 산출의 90%가 "요약만 읽고도 말할 수 있는 것"(derive 감사 n=48).
NOREPEAT = """
## 이미 발행된 요약 (독자가 방금 읽은 것)
user 메시지의 [이미 발행된 요약]은 이 카드에서 독자가 **바로 위에서 읽은 문단**이다.
**그것이 말한 것을 다시 말하지 마라.** 표현만 바꾼 재진술은 지면 낭비다.
같은 사실을 쓰더라도, 요약이 **연결하지 않은 관계**로만 써라.
"""

BEYOND2 = """
## 요약이 고른 것과 버린 것
user 메시지의 [이미 발행된 요약]은 원문에서 **일부만 고른 결과**다. 동결 원문에는 요약이 버린 것이 있다.
**요약이 담지 않은 것 중 독자가 알아야 할 것**을 동결 원문에서 찾아 써라.
- 요약이 이미 말한 것을 반복하지 마라.
- 원문에 **적혀 있는 것만** 써라(추측·외삽 금지는 그대로다).
- 요약이 버린 것 중 알릴 가치가 있는 것이 없으면 why_it_matters 를 빈 문자열로 두어라.
★ **요약을 언급하지 마라.** "요약에는 없지만", "요약이 빠뜨린", "요약은 ~만 다루고" 같은 도입부 금지.
  독자는 요약을 방금 읽었다 — 무엇이 빠졌는지 설명하지 말고 **그 내용을 그냥 말하라.**
"""

BEYOND = """
## 요약이 고른 것과 버린 것
user 메시지의 [이미 발행된 요약]은 원문에서 **일부만 고른 결과**다. 동결 원문에는 요약이 버린 것이 있다.
**요약이 담지 않은 것 중 독자가 알아야 할 것**을 동결 원문에서 찾아 써라.
- 요약이 이미 말한 것을 반복하지 마라.
- 원문에 **적혀 있는 것만** 써라(추측·외삽 금지는 그대로다).
- 요약이 버린 것 중 알릴 가치가 있는 것이 없으면 why_it_matters 를 빈 문자열로 두어라.
"""

ARMS = {
    "base":       {"sys_extra": "", "user_extra": ""},
    "struct+sil": {"sys_extra": STRUCT + SILENCE, "user_extra": ""},
    "counterfact": {"sys_extra": COUNTERFACT, "user_extra": ""},
    "conditional": {"sys_extra": CONDITIONAL, "user_extra": ""},
    "s+s+trunc":  {"sys_extra": STRUCT + SILENCE, "user_extra": TRUNC},
    "relation":   {"sys_extra": RELATION, "user_extra": ""},
    "norepeat":   {"sys_extra": NOREPEAT, "user_extra": "", "show_summary": True},
    "beyond":     {"sys_extra": BEYOND,   "user_extra": "", "show_summary": True},
    "beyond2":    {"sys_extra": BEYOND2,  "user_extra": "", "show_summary": True},
}

_ANCHOR = "\n\n## lens 가 정하는 것"


def system_for(arm: str, lens_guidance: str) -> str:
    base = build_interp_system_prompt(lens_guidance=lens_guidance)
    extra = ARMS[arm]["sys_extra"]
    if not extra:
        return base
    i = base.find(_ANCHOR)
    assert i > 0, "삽입 앵커('## lens 가 정하는 것')를 못 찾음 — 계약 구조가 바뀌었다"
    return base[:i] + "\n" + extra + base[i:]


# ── 표본 ─────────────────────────────────────────────────────────────────────
def load_sample(n=12):
    """공허성이 **실제로 나타나는 모집단**을 섞는다 — 1차 파일럿은 장문 기술문서만 뽑혀
    base 의 공허끝이 0/6 이었다(전수 44%인데). 개선을 측정하려면 문제가 있는 표본이어야 한다."""
    d = json.load(open(f"{DATA}/dataset.json"))
    cards, srcs = d["cards"], d["sources"]
    pool = [c for c in cards
            if c["source_id"] in srcs
            and len([x for x in c["claims"] if x["verdict"] == "VERIFIED"]) >= 3]
    seen, uniq = set(), []
    for c in sorted(pool, key=lambda c: c["cache_key"]):
        if c["source_id"] in seen:
            continue
        seen.add(c["source_id"])
        uniq.append(c)
    vac = [c for c in uniq if _VACUOUS.search(c["why"].strip())]
    rest = [c for c in uniq if c not in vac]
    short = [c for c in rest if len(srcs[c["source_id"]]["text"]) < 2500]
    long_ = [c for c in rest if len(srcs[c["source_id"]]["text"]) >= 6000]
    k = max(1, n // 3)
    picked = vac[:k] + short[::max(1, len(short)//k)][:k] + long_[::max(1, len(long_)//k)][:k]
    out = []
    for c in picked:
        s = srcs[c["source_id"]]
        out.append({
            "headline": c["headline"], "orig_why": c["why"], "summary": c["summary"],
            "bucket": ("공허끝" if c in vac else "짧은원문" if len(s["text"]) < 2500 else "장문"),
            "src": FrozenSource(c["source_id"], s.get("url", ""), s.get("title", ""), s["text"], ""),
            "claims": tuple(A.Claim(x["id"], x["text"], x["type"], "core")
                            for x in c["claims"] if x["verdict"] == "VERIFIED"),
        })
    return out


_VACUOUS = re.compile(r"(신호가 된다|참고할 만하다|참고할 신호|시사한다|주목할 필요|주목된다|"
                      r"고려할 필요|판단할 수 있다는 점|가늠할|영향을 줄 수 있다|중요해진다)[.\s]*$")


def run_one(job):
    arm, it, settings, lens = job
    lensg = resolve_lens(lens).guidance
    t0 = time.monotonic()
    try:
        sysmsg = system_for(arm, lensg)
        user = build_interp_user_prompt(it["src"], it["claims"], today="2026-07-28")
        if ARMS[arm].get("show_summary"):
            user = f"[이미 발행된 요약]\n{it['summary']}\n\n" + user
        user += ARMS[arm]["user_extra"]
        interp = _parse_interp(_run_author(sysmsg, user, settings))
        why = interp.why_it_matters
        return {"arm": arm, "lens": lens, "bucket": it["bucket"],
                "based_on": list(interp.based_on), "n_cited": len(interp.based_on),
                "headline": it["headline"][:44], "why": why,
                "len": len(why), "empty": not why.strip(),
                "vacuous_end": bool(_VACUOUS.search(why.strip())),
                "secs": round(time.monotonic() - t0)}
    except Exception as e:  # noqa: BLE001 — 실패도 데이터
        return {"arm": arm, "lens": lens, "bucket": it["bucket"],
                "headline": it["headline"][:44], "error": type(e).__name__,
                "secs": round(time.monotonic() - t0)}


OUT = f"{DATA}/pilot2_rows.json"


def main():
    global OUT
    OUT = os.environ.get("PILOT_OUT", OUT)
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 12
    arms = sys.argv[2].split(",") if len(sys.argv) > 2 else ["base", "struct+sil", "counterfact", "conditional"]
    lenses = sys.argv[3].split(",") if len(sys.argv) > 3 else ["engineer", "business"]
    settings = load_settings()
    sample = load_sample(n)
    total = len(sample) * len(arms) * len(lenses)
    print(f"표본 {len(sample)}건 × 팔 {len(arms)} × lens {len(lenses)} = {total}회 · author={settings.author_model_id}")
    from collections import Counter
    print("  버킷:", dict(Counter(it["bucket"] for it in sample)))
    for a in arms:
        print(f"  {a:<12} system {len(system_for(a, resolve_lens('engineer').guidance))}자")
    print()
    jobs = [(a, it, settings, ln) for it in sample for a in arms for ln in lenses]
    rows = []
    with ThreadPoolExecutor(max_workers=4) as ex:
        for k, r in enumerate(ex.map(run_one, jobs), 1):
            rows.append(r)
            tag = r.get("error") or ("빈값" if r["empty"] else f"{r['len']}자{' 공허끝' if r['vacuous_end'] else ''}")
            print(f"  [{k:>3}/{total}] {r['arm']:<12} {r['lens']:<9} {r['bucket']:<6} {tag:<16} {r['secs']}s", flush=True)
            json.dump(rows, open(OUT, "w"), ensure_ascii=False, indent=1)

    import statistics as st
    print("\n" + "=" * 88)
    print(f"{'팔':<12} {'lens':<9} {'성공':<7} {'빈값':<5} {'공허끝':<8} {'길이':<7} {'지연'}")
    for a in arms:
        for ln in lenses:
            ok = [r for r in rows if r["arm"] == a and r["lens"] == ln and "error" not in r]
            if not ok:
                print(f"{a:<12} {ln:<9} 전부 실패")
                continue
            print(f"{a:<12} {ln:<9} {len(ok)}/{len(sample):<5} {sum(r['empty'] for r in ok):<5} "
                  f"{sum(r['vacuous_end'] for r in ok)}/{len(ok):<6} "
                  f"{st.median([r['len'] for r in ok]):<7.0f} {st.median([r['secs'] for r in ok])}s")
    print("\n버킷별 공허끝(팔 x 버킷, lens 합산):")
    for a in arms:
        cells = []
        for b in ("공허끝", "짧은원문", "장문"):
            ok = [r for r in rows if r["arm"] == a and r["bucket"] == b and "error" not in r]
            cells.append(f"{b} {sum(r['vacuous_end'] for r in ok)}/{len(ok)}" if ok else f"{b} -")
        print(f"  {a:<12} " + " · ".join(cells))
    print(f"\n전문: {OUT}")


if __name__ == "__main__":
    main()
