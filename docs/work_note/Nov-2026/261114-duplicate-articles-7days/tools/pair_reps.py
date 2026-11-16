#!/usr/bin/env python3
"""한 쌍을 운영 판정자와 같은 호출로 여러 번 판정해 값·사고 블록 유무·응답 원문을 본다(읽기 전용 — Bedrock 호출만).

    uv run python pair_reps.py "<A 제목 조각>" "<B 제목 조각>" [반복 수=10]

예) 놓친 쌍:  pair_reps.py "The components of agent memory" "에이전트 메모리, 많이 저장하기보다"
            pair_reps.py "Transformers Model Integration Contracts" "모델 통합 계약" 5
★ 현재 체크아웃의 `REREPORT_SYSTEM` 을 쓴다 — 옛 프롬프트(값 먼저)의 0/10 을 재현하려면 2026-11-14 이전 커밋에서 돌린다.
제목 조각이 source-store 에서 여러 건이면(같은 글을 다시 받은 동결본) A 는 PyTorch Korea 가 아닌 쪽, B 는 그대로 첫 건을 쓴다.
"""
from __future__ import annotations

import sys

import boto3
from boto3.dynamodb.conditions import Attr

from briefing.core.config import load_settings
from briefing.core.retrieval.relevance_bedrock import REREPORT_MAX_TOKENS, _client
from briefing.core.retrieval.rereport import MAX_JUDGE_CHARS, REREPORT_SYSTEM, _first_json_object
from briefing.core.stores.dynamo import source_store_from_settings

A_SUB, B_SUB = sys.argv[1], sys.argv[2]
REPS = int(sys.argv[3]) if len(sys.argv) > 3 else 10

s = load_settings()
store = source_store_from_settings(s)
table = boto3.resource("dynamodb", region_name="us-east-1").Table("briefing-source-store")
client = _client(s.region)


def src(sub: str, *, original: bool):
    kw = dict(FilterExpression=Attr("title").contains(sub), ProjectionExpression="source_id, title, media")
    r = table.scan(**kw)
    items = list(r["Items"])
    while "LastEvaluatedKey" in r:
        r = table.scan(ExclusiveStartKey=r["LastEvaluatedKey"], **kw)
        items += r["Items"]
    if original:
        items = [i for i in items if "PyTorch" not in i.get("media", "")] or items
    assert items, f"source-store 에 없음: {sub}"
    return store.get_source(items[0]["source_id"])


a, b = src(A_SUB, original=True), src(B_SUB, original=False)
print(f"A [{a.media}] {a.title[:70]} · {len(a.text)}자\nB [{b.media}] {b.title[:70]} · {len(b.text)}자")
print("프롬프트 끝줄:", REREPORT_SYSTEM.splitlines()[-1], "\n")
user = f"<A>\n{a.text[:MAX_JUDGE_CHARS]}\n</A>\n\n<B>\n{b.text[:MAX_JUDGE_CHARS]}\n</B>"
n_true = n_false = n_think = 0
for i in range(REPS):
    resp = client.converse(modelId=s.relevance_model_id, system=[{"text": REREPORT_SYSTEM}],
                           messages=[{"role": "user", "content": [{"text": user}]}],
                           inferenceConfig={"maxTokens": REREPORT_MAX_TOKENS})
    blocks = resp["output"]["message"]["content"]
    kinds = [next(iter(x)) for x in blocks]
    text = next((x["text"] for x in blocks if "text" in x), "")
    same = (_first_json_object(text) or {}).get("same")
    n_true += same is True
    n_false += same is False
    n_think += "reasoningContent" in kinds
    print(f"{i + 1:2}) same={same} blocks={kinds} out={resp['usage'].get('outputTokens')}\n    raw: {text!r}")
print(f"\nsame=true {n_true}/{REPS} · same=false {n_false}/{REPS} · 사고 블록 있음 {n_think}/{REPS}")
