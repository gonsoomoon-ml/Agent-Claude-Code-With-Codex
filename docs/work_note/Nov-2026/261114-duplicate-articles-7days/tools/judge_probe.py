#!/usr/bin/env python3
"""걸러지지 않은 쌍을 운영 판정자에 직접 넣어 본다(읽기 전용) + 응답 블록 종류·토큰 확인."""
from __future__ import annotations

import boto3
from boto3.dynamodb.conditions import Attr

from briefing.core.config import load_settings
from briefing.core.retrieval.relevance_bedrock import REREPORT_MAX_TOKENS, _client
from briefing.core.retrieval.rereport import MAX_JUDGE_CHARS, REREPORT_SYSTEM, _first_json_object
from briefing.core.stores.dynamo import source_store_from_settings

s = load_settings()
store = source_store_from_settings(s)
t = boto3.resource("dynamodb", region_name="us-east-1").Table("briefing-source-store")
client = _client(s.region)


def src(sub: str):
    kw = dict(FilterExpression=Attr("title").contains(sub), ProjectionExpression="source_id, title, media")
    r = t.scan(**kw)
    items = list(r["Items"])
    while "LastEvaluatedKey" in r:
        r = t.scan(ExclusiveStartKey=r["LastEvaluatedKey"], **kw)
        items += r["Items"]
    assert len(items) == 1, (sub, [(i["media"], i["title"]) for i in items])
    return store.get_source(items[0]["source_id"])


def call(a, b):
    user = f"<A>\n{a.text[:MAX_JUDGE_CHARS]}\n</A>\n\n<B>\n{b.text[:MAX_JUDGE_CHARS]}\n</B>"
    resp = client.converse(modelId=s.relevance_model_id, system=[{"text": REREPORT_SYSTEM}],
                           messages=[{"role": "user", "content": [{"text": user}]}],
                           inferenceConfig={"maxTokens": REREPORT_MAX_TOKENS})
    blocks = resp["output"]["message"]["content"]
    kinds = [next(iter(b)) for b in blocks]
    text = next((b["text"] for b in blocks if "text" in b), "")
    think = next((b["reasoningContent"].get("reasoningText", {}).get("text", "") for b in blocks if "reasoningContent" in b), "")
    obj = _first_json_object(text) or {}
    u = resp["usage"]
    return obj.get("same"), obj.get("reason", text[:200]), kinds, u.get("outputTokens"), resp.get("stopReason"), think


PAIRS = [
    ("메모리", "The components of agent memory", "에이전트 메모리, 많이 저장하기보다"),
    ("Carbon", "Gemini 4 Carbon is now available", "Gemini 4 Carbon arrives just in time"),
    ("Manufacturing", "Claude for Manufacturing: AI plugin", "Anthropic's Claude for Manufacturing plugs"),
    ("Hydrogen(원 발표→Decoder)", "Introducing Gemini 4 Hydrogen", "Google's Gemini 4 Hydrogen outscores"),
    ("Hydrogen(Search→원 발표) 운영에서 제외된 쌍", "Google Search gets a major upgrade with Gemini 4 Hydrogen", "Introducing Gemini 4 Hydrogen"),
    ("Fable 5.2(Decoder→KR)", "Claude Fable 5.2 and Mythos 5.2 cement", "Anthropic, Claude Fable 5.2와 Mythos 5.2 출시"),
    ("Inkling(Decoder→KR)", "Thinking Machines' Inkling 2 Small drops", "Thinking Machines Lab, 활성 17B"),
]
for label, a_sub, b_sub in PAIRS:
    a, b = src(a_sub), src(b_sub)
    print(f"== {label}\n   A [{a.media}] {a.title[:60]}\n   B [{b.media}] {b.title[:60]}")
    for i in range(2):
        same, reason, kinds, out_tok, stop, think = call(a, b)
        print(f"   {i + 1}) same={same} blocks={kinds} out={out_tok} stop={stop}\n      reason: {reason[:260]}")
        if label == "메모리" and i == 0:
            print(f"      thinking({len(think)}자): {think[:700]!r}")
    print()
