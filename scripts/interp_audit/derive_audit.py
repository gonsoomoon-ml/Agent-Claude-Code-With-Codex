# -*- coding: utf-8 -*-
"""도출 가능성 감사 — "이 문단을 **요약만 읽은 사람**이 스스로 말할 수 있는가?"

왜 이 지표인가: 목표가 "요약만 읽어서는 도달하지 못할 것"이므로 **정의를 그대로 잰다**.
(b)/(c) 분류는 대리 지표였고 바닥 효과로 실패했다(95건 중 (c) 1건). 이 지표는
대조어 주입으로 게임할 수 없고, 행동 가능성을 안 물으므로 지어내기 압박도 없다.

★ 판정자는 **요약만** 본다 — 원문도 claims 도 주지 않는다. 그래야 "요약 독자"를 흉내낸다.
★ 도출 가능하다고 답하려면 **요약의 해당 부분을 축어 인용**해야 한다(인용 못 하면 도출 불가로 본다).
   오늘 얻은 교훈: 근거 인용 강제가 배경지식 추론을 막는다.

LEAP 감사(relation_audit.json)와 교차해 2x2 를 만든다:
  도출가능 → 무의미 / 도출불가+근거있음 → **통찰** / 도출불가+LEAP → 오추론
"""
import json
import os
from collections import Counter
from concurrent.futures import ThreadPoolExecutor


from briefing.core.config import load_settings
from briefing.core.retrieval.relevance_bedrock import _client

# 중간 산출물(JSON) 보관 위치 — 코드만 저장소에 살고 데이터(수 MB·재생성 가능)는 밖에 둔다.
DATA = os.environ.get("INTERP_AUDIT_DIR", "/tmp/interp-audit")
os.makedirs(DATA, exist_ok=True)

SYSTEM = """너는 뉴스 카드의 두 부분을 비교한다: [요약]과 그 아래 [문단].
질문은 하나다 — **[요약]만 읽은 사람이 [문단]의 내용을 스스로 말할 수 있는가?**

규칙:
- [요약]에 없는 원문 지식으로 판단하지 마라. 너는 [요약]만 가진 독자다.
- "말할 수 있다"고 답하려면 [요약]에서 그 근거가 되는 부분을 **그대로 인용**해야 한다.
  인용하지 못하면 "말할 수 없다"이다.
- 표현만 바꾼 재진술은 "말할 수 있다"이다.
- 여러 사실을 **엮어야만** 나오는 관계, 요약이 언급만 하고 연결하지 않은 것,
  요약에 없는 조건·시점·인과는 "말할 수 없다"이다.
- 애매하면 "말할 수 있다"로 답하라(문단에 후하게 점수 주지 않기 위해).

다음 JSON 하나만 출력하라(다른 텍스트 금지):
{"derivable": true | false,
 "quote": "derivable=true 면 [요약]에서 그대로 복사한 근거 구간(10자 이상), 아니면 \\"\\"",
 "added": "derivable=false 면 문단이 더한 것을 한 구절로"}"""

USER = """[요약]
{summary}

[문단]
{why}"""


def main():
    s = load_settings()
    cl = _client(s.region)

    d = json.load(open(f"{DATA}/dataset.json"))
    summ_by = {}
    for c in d["cards"]:
        summ_by.setdefault(c["headline"][:44], c["summary"])

    rows = json.load(open(f"{DATA}/relation_audit.json"))   # LEAP 판정이 이미 붙어 있다
    rows = [r for r in rows if r["why"].strip() and summ_by.get(r["headline"])]
    print(f"채점 대상 {len(rows)}건 (relation {sum(1 for r in rows if r['arm']=='relation')} · "
          f"base {sum(1 for r in rows if r['arm']=='base')})")

    # ── 자 검증: 요약 자체를 문단으로 넣으면 반드시 derivable=true 여야 한다 ──
    probe_h = rows[0]["headline"]
    probe = {"summary": summ_by[probe_h], "why": summ_by[probe_h]}

    def ask(summary, why):
        try:
            resp = cl.converse(modelId=s.relevance_model_id, system=[{"text": SYSTEM}],
                               messages=[{"role": "user", "content": [
                                   {"text": USER.format(summary=summary, why=why)}]}],
                               inferenceConfig={"maxTokens": 400, "temperature": 0})
            t = resp["output"]["message"]["content"][0]["text"]
            i, j = t.find("{"), t.rfind("}")
            return json.loads(t[i:j + 1]) if i >= 0 else {"derivable": None}
        except Exception as e:  # noqa: BLE001
            return {"derivable": None, "err": f"{type(e).__name__}"}

    sanity = ask(probe["summary"], probe["why"])
    print(f"자 검증 — 요약 자체를 문단으로 넣음 → derivable={sanity.get('derivable')} "
          f"{'OK' if sanity.get('derivable') is True else '★FAIL: 자가 재진술도 못 잡는다'}")
    if sanity.get("derivable") is not True:
        raise SystemExit("자 검증 실패 — 채점 중단")

    with ThreadPoolExecutor(max_workers=8) as ex:
        res = list(ex.map(lambda r: ask(summ_by[r["headline"]], r["why"]), rows))
    for r, v in zip(rows, res):
        r["derive"] = v

    json.dump(rows, open(f"{DATA}/derive_audit.json", "w"), ensure_ascii=False, indent=1)

    print("\n" + "=" * 74)
    print(f"{'팔':<10} {'n':<5} {'도출가능(무의미)':<18} {'도출불가(추가 있음)'}")
    for arm in ("base", "relation"):
        sub = [r for r in rows if r["arm"] == arm]
        dv = sum(1 for r in sub if r["derive"].get("derivable") is True)
        nd = sum(1 for r in sub if r["derive"].get("derivable") is False)
        print(f"{arm:<10} {len(sub):<5} {dv}/{len(sub)} ({dv/len(sub)*100:.0f}%){'':<7} "
              f"{nd}/{len(sub)} ({nd/len(sub)*100:.0f}%)")

    print("\n2x2 — 도출가능성 × 근거(LEAP 감사):")
    print(f"{'팔':<10} {'무의미(도출가능)':<18} {'통찰(불가+근거)':<18} {'오추론(불가+LEAP)':<18} {'기타'}")
    for arm in ("base", "relation"):
        sub = [r for r in rows if r["arm"] == arm]
        cells = Counter()
        for r in sub:
            dv, vd = r["derive"].get("derivable"), r["audit"].get("verdict")
            if dv is True:
                cells["무의미"] += 1
            elif dv is False and vd == "SUPPORTED":
                cells["통찰"] += 1
            elif dv is False and vd == "LEAP":
                cells["오추론"] += 1
            else:
                cells["기타"] += 1
        n = len(sub)
        print(f"{arm:<10} {cells['무의미']}/{n} ({cells['무의미']/n*100:.0f}%){'':<8} "
              f"{cells['통찰']}/{n} ({cells['통찰']/n*100:.0f}%){'':<8} "
              f"{cells['오추론']}/{n} ({cells['오추론']/n*100:.0f}%){'':<8} {cells['기타']}")

    print("\n── 통찰 판정 사례(도출불가 + 근거있음) ──")
    shown = 0
    for r in rows:
        if r["derive"].get("derivable") is False and r["audit"].get("verdict") == "SUPPORTED" and shown < 4:
            shown += 1
            print(f"\n[{r['arm']}·{r['lens']}] {r['headline'][:42]}")
            print(f"  더한 것: {r['derive'].get('added','')[:150]}")

    print(f"\n전문: {DATA}/derive_audit.json")


if __name__ == "__main__":
    main()
