#!/usr/bin/env python3
"""판정 실패 쌍의 원 응답 보기(읽기 전용) — 운영 판정자와 같은 호출을 N회 하고 응답 원문을 그대로 찍는다.

    uv run python docs/work_note/Nov-2026/261114-duplicate-articles-7days/tools/judge_raw_probe.py \\
        <same-site-replay-….json> <b_title 부분 문자열> [횟수=3] [same-first]

재생 JSON 에서 제목이 맞고 판정이 실패(`same` 이 null)한 쌍만 고른다. 줄마다 파서(`llm_rereport` 가 쓰는
`_first_json_object`)가 그 응답을 읽는지도 함께 찍는다.
넷째 인자 `same-first` 를 주면 2026-11-14 이전 운영의 답 순서(값 먼저·이유 나중)로 묻는다 — 답 순서와 무관한지 볼 때.
"""
from __future__ import annotations

import json
import sys

from briefing.core.config import load_settings
from briefing.core.retrieval import relevance_bedrock as rb
from briefing.core.retrieval.rereport import MAX_JUDGE_CHARS, REREPORT_SYSTEM, _first_json_object
from briefing.core.stores.dynamo import source_store_from_settings

rows = [r for r in json.load(open(sys.argv[1], encoding="utf-8")) if sys.argv[2] in r["b_title"] and r["same"] is None]
n = int(sys.argv[3]) if len(sys.argv) > 3 else 3
SAME_FIRST_END = 'Answer only JSON: {"same": true|false, "reason": "<one short sentence>"}'   # 2026-11-14 이전 운영
same_first = len(sys.argv) > 4 and sys.argv[4] == "same-first"
system = REREPORT_SYSTEM.rsplit("\n", 1)[0] + "\n" + SAME_FIRST_END if same_first else REREPORT_SYSTEM
print(f"답 순서: {'값 먼저(옛 운영)' if same_first else '이유 먼저(현재)'}")
s = load_settings()
store = source_store_from_settings(s)
client = rb._client(s.region)
for r in rows:
    a, b = store.get_source(r["a_sid"]), store.get_source(r["b_sid"])
    user = f"<A>\n{a.text[:MAX_JUDGE_CHARS]}\n</A>\n\n<B>\n{b.text[:MAX_JUDGE_CHARS]}\n</B>"
    print(f"B: {b.title}\nA: {a.title}")
    for i in range(n):
        resp = client.converse(modelId=s.relevance_model_id, system=[{"text": system}],
                               messages=[{"role": "user", "content": [{"text": user}]}],
                               inferenceConfig={"maxTokens": rb.REREPORT_MAX_TOKENS})
        blocks = resp["output"]["message"]["content"]
        text = next((x["text"] for x in blocks if "text" in x), "")
        obj = _first_json_object(text)
        parsed = f"읽음(same={obj.get('same')})" if obj is not None else "못 읽음"
        print(f"--- {i + 1}회 · 블록 {[list(x)[0] for x in blocks]} · stop={resp['stopReason']} · 파서 {parsed}\n{text}")
