#!/usr/bin/env python3
"""재보도 판정자 원인 실험(읽기 전용 — Bedrock 호출만). pairs.json 의 쌍을 설정 변형별로 판정해 results.jsonl 에 쌓는다.

    uv run python run_variants.py <pairs.json> <results.jsonl> <variant,variant,...> [reps]

변형:
  V0  2026-11-14 이전 운영(same 먼저 · 앞 8,000자 · effort 기본)
  V1  JSON 순서만 바꿈(reason 먼저 → same) — 2026-11-14 채택
  V2  effort=high 만 추가
  V3  본문 20,000자만
  V4  V1 + V3
"""
from __future__ import annotations

import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor

from botocore.exceptions import ClientError

from briefing.core.config import load_settings
from briefing.core.retrieval.relevance_bedrock import _client
from briefing.core.retrieval.rereport import REREPORT_SYSTEM
from briefing.core.stores.dynamo import source_store_from_settings

PAIRS, OUT, VARIANTS = sys.argv[1], sys.argv[2], sys.argv[3].split(",")
REPS = int(sys.argv[4]) if len(sys.argv) > 4 else 2
MISS_REPS = 5

_SAME_FIRST_END = 'Answer only JSON: {"same": true|false, "reason": "<one short sentence>"}'   # 2026-11-14 이전 운영
_REASON_FIRST_END = 'Answer only JSON: {"reason": "<one short sentence>", "same": true|false}'  # 2026-11-14 채택
for _end in (_SAME_FIRST_END, _REASON_FIRST_END):   # 수정 전·후 어느 체크아웃에서 돌려도 두 프롬프트가 같게 본문만 떼어 낸다
    if REREPORT_SYSTEM.endswith(_end):
        _BODY = REREPORT_SYSTEM[: -len(_end)]
        break
else:
    raise SystemExit("운영 프롬프트 끝줄이 예상과 다르다 — 변형 정의를 다시 맞출 것")
SAME_FIRST, REASON_FIRST = _BODY + _SAME_FIRST_END, _BODY + _REASON_FIRST_END

CFG = {
    "V0": dict(system=SAME_FIRST, chars=8000, fields=None, max_tokens=1500),
    "V1": dict(system=REASON_FIRST, chars=8000, fields=None, max_tokens=1500),
    "V2": dict(system=SAME_FIRST, chars=8000, fields={"output_config": {"effort": "high"}}, max_tokens=4000),
    "V3": dict(system=SAME_FIRST, chars=20000, fields=None, max_tokens=1500),
    "V4": dict(system=REASON_FIRST, chars=20000, fields=None, max_tokens=1500),
}

s = load_settings()
store = source_store_from_settings(s)
client = _client(s.region)
pairs = json.load(open(PAIRS))
texts: dict[str, str] = {}
for p in pairs:
    for k in ("a_sid", "b_sid"):
        if p[k] not in texts:
            texts[p[k]] = store.get_source(p[k]).text


def json_objects(ans: str) -> list[dict]:
    dec, out, i = json.JSONDecoder(), [], ans.find("{")
    while i != -1:
        try:
            obj, end = dec.raw_decode(ans, i)
            if isinstance(obj, dict):
                out.append(obj)
                i = ans.find("{", end)
                continue
        except ValueError:
            pass
        i = ans.find("{", i + 1)
    return out


def call(job):
    variant, idx, rep = job
    cfg, p = CFG[variant], pairs[idx]
    user = f"<A>\n{texts[p['a_sid']][:cfg['chars']]}\n</A>\n\n<B>\n{texts[p['b_sid']][:cfg['chars']]}\n</B>"
    kw = dict(modelId=s.relevance_model_id, system=[{"text": cfg["system"]}],
              messages=[{"role": "user", "content": [{"text": user}]}], inferenceConfig={"maxTokens": cfg["max_tokens"]})
    if cfg["fields"]:
        kw["additionalModelRequestFields"] = cfg["fields"]
    err = None
    for attempt in range(5):
        try:
            r = client.converse(**kw)
            break
        except ClientError as e:
            err = f"{e.response['Error']['Code']}: {e.response['Error']['Message'][:120]}"
            time.sleep(2 * (attempt + 1))
        except Exception as e:  # noqa: BLE001 — 읽기 타임아웃 등: 한 호출 실패가 전체 run 을 끊지 않게
            err = f"{type(e).__name__}: {str(e)[:120]}"
            time.sleep(2 * (attempt + 1))
    else:
        return dict(variant=variant, idx=idx, rep=rep, error=err)
    blocks = r["output"]["message"]["content"]
    text = next((b["text"] for b in blocks if "text" in b), "")
    objs = [o for o in json_objects(text) if isinstance(o.get("same"), bool)]
    return dict(variant=variant, idx=idx, rep=rep, kinds=[next(iter(b)) for b in blocks], stop=r["stopReason"],
                out_tokens=r["usage"]["outputTokens"], in_tokens=r["usage"]["inputTokens"],
                first=objs[0]["same"] if objs else None, last=objs[-1]["same"] if objs else None,
                n_json=len(objs), text=text)


jobs = [(v, i, k) for v in VARIANTS for i, p in enumerate(pairs)
        for k in range(MISS_REPS if (p["group"] == "sent" and p["expect"] is True) else REPS)]
print(f"쌍 {len(pairs)} · 변형 {VARIANTS} · 호출 {len(jobs)}", flush=True)
t0 = time.time()
assert not __import__("os").path.exists(OUT), "결과 파일이 이미 있다 — run 마다 새 파일"
with ThreadPoolExecutor(6) as ex, open(OUT, "w") as f:
    for n, res in enumerate(ex.map(call, jobs), 1):
        f.write(json.dumps(res, ensure_ascii=False) + "\n")
        if n % 40 == 0:
            f.flush()
            print(f"  {n}/{len(jobs)} ({time.time() - t0:.0f}s)", flush=True)
print(f"끝 {time.time() - t0:.0f}s")
