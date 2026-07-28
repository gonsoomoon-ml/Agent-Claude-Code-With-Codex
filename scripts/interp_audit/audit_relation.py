# -*- coding: utf-8 -*-
"""관계 진위 감사 — 해석층 문단이 주장하는 관계가 **검증된 claims 로부터 실제로 성립하는가**.

이 접근(relation 팔)의 실패 모드는 공허함이 아니라 **그럴듯한 오추론**이다. 공허한 문장은
틀릴 수 없지만 관계를 주장하는 문장은 틀릴 수 있다 — 그게 정보량의 대가다.
certifier 는 해석층을 보지 않으므로 이 감사가 유일한 확인 경로다.

★ 판정자 설계 원칙(오늘 얻은 교훈 반영):
  · 근거 claim 을 **축어 인용**하게 한다 — 인용 못 하면 미근거(배경지식 추론 차단).
  · "세상 지식으로 그럴듯한가"가 아니라 "**적힌 claims 로 성립하는가**"만 묻는다.
  · 애매하면 성립 쪽으로 — 위양성(멀쩡한 문장을 오추론으로 모는 것)을 피한다.
"""
import json
import os
from collections import Counter
from concurrent.futures import ThreadPoolExecutor


from briefing.core.config import load_settings
from briefing.core.retrieval.relevance_bedrock import _client
from pilot import load_sample

# 중간 산출물(JSON) 보관 위치 — 코드만 저장소에 살고 데이터(수 MB·재생성 가능)는 밖에 둔다.
DATA = os.environ.get("INTERP_AUDIT_DIR", "/tmp/interp-audit")
os.makedirs(DATA, exist_ok=True)

SYSTEM = """너는 뉴스 카드의 해석 문단을 감사한다. 그 문단이 주장하는 **관계**가
아래 [검증된 사실] 목록으로부터 실제로 성립하는지만 판정한다.

규칙:
- **적힌 사실만 근거다.** 세상 지식으로 그럴듯한지 판단하지 마라. 네가 아는 배경으로 빈틈을 메우지 마라.
- 근거가 있다면 그 사실의 문장을 **그대로 인용**하라. 인용하지 못하면 근거가 없는 것이다.
- 표현을 바꾼 것은 오추론이 아니다. 애매하면 SUPPORTED 로 답하라(멀쩡한 문장을 잘못 잡지 않기 위해).
- 관계를 전혀 주장하지 않고 사실을 나열하기만 하면 verdict=NO_RELATION.

다음 JSON 하나만 출력하라(다른 텍스트 금지):
{"relation": "문단이 주장하는 관계를 한 문장으로",
 "verdict": "SUPPORTED" | "LEAP" | "NO_RELATION",
 "evidence": "SUPPORTED 면 근거 사실 축어 인용, LEAP 면 근거 없는 추론 단계를 지적",
 "leap_step": "LEAP 일 때만: 어느 지점이 사실을 넘는가"}"""

USER = """[기사 제목]
{headline}

[검증된 사실]
{claims}

[해석 문단]
{why}"""


def build(it):
    return USER.format(headline=it["headline"],
                       claims="\n".join(f"- {c}" for c in it["claims"]),
                       why=it["why"])


def main():
    s = load_settings()
    cl = _client(s.region)
    claims_by = {it["headline"][:44]: [c.text for c in it["claims"]] for it in load_sample(12)}

    rows = []
    for path, arm in ((f"{DATA}/pilot3_rows.json", "relation"),
                      (f"{DATA}/pilot2_rows.json", "base")):
        for r in json.load(open(path)):
            if "error" in r or r.get("arm") != arm or not r["why"].strip():
                continue
            rows.append({**r, "claims": claims_by.get(r["headline"], [])})

    print(f"감사 대상 {len(rows)}건 (relation {sum(1 for r in rows if r['arm']=='relation')} · "
          f"base {sum(1 for r in rows if r['arm']=='base')})")

    def call(r):
        try:
            resp = cl.converse(modelId=s.relevance_model_id, system=[{"text": SYSTEM}],
                               messages=[{"role": "user", "content": [{"text": build(r)}]}],
                               inferenceConfig={"maxTokens": 500, "temperature": 0})
            txt = resp["output"]["message"]["content"][0]["text"]
            i, j = txt.find("{"), txt.rfind("}")
            return json.loads(txt[i:j + 1]) if i >= 0 else {"verdict": "PARSE_FAIL"}
        except Exception as e:  # noqa: BLE001
            return {"verdict": "ERROR", "evidence": f"{type(e).__name__}: {e}"}

    with ThreadPoolExecutor(max_workers=8) as ex:
        verdicts = list(ex.map(call, rows))
    for r, v in zip(rows, verdicts):
        r["audit"] = v

    json.dump(rows, open(f"{DATA}/relation_audit.json", "w"), ensure_ascii=False, indent=1)

    print("\n" + "=" * 76)
    for arm in ("base", "relation"):
        sub = [r for r in rows if r["arm"] == arm]
        c = Counter(r["audit"].get("verdict") for r in sub)
        n = len(sub)
        leap = c.get("LEAP", 0)
        print(f"{arm:<10} n={n:<4} SUPPORTED {c.get('SUPPORTED',0):>2} · "
              f"LEAP {leap:>2} ({leap/n*100:.0f}%) · NO_RELATION {c.get('NO_RELATION',0):>2} · "
              f"기타 {n - c.get('SUPPORTED',0) - leap - c.get('NO_RELATION',0)}")

    print("\n── LEAP 판정 사례(오추론 의심) ──")
    for r in rows:
        if r["audit"].get("verdict") == "LEAP":
            print(f"\n[{r['arm']}·{r['lens']}] {r['headline'][:44]}")
            print(f"  주장: {r['audit'].get('relation','')[:130]}")
            print(f"  비약: {(r['audit'].get('leap_step') or r['audit'].get('evidence',''))[:180]}")

    print(f"\n전문: {DATA}/relation_audit.json")


if __name__ == "__main__":
    main()
