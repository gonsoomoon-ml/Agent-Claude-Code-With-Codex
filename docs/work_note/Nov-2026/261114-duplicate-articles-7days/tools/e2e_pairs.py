"""놓친 2쌍 + 경계 2쌍을 운영 경로(make_bedrock_rereport → llm_rereport)로 3회씩 판정(읽기 전용)."""
import json
import sys
from briefing.core.config import load_settings
from briefing.core.retrieval import rereport
from briefing.core.retrieval.relevance_bedrock import make_bedrock_rereport
from briefing.core.stores.dynamo import source_store_from_settings

s = load_settings()
store, judge = source_store_from_settings(s), make_bedrock_rereport(s)
print("프롬프트 끝줄:", rereport.REREPORT_SYSTEM.splitlines()[-1])
for p in json.load(open(sys.argv[1])):
    if not ((p["group"] == "sent" and p["expect"] is True) or p["expect"] is None):
        continue
    a, b = store.get_source(p["a_sid"]), store.get_source(p["b_sid"])
    vs = [judge(a.text, b.text) for _ in range(3)]
    print(f"{[v.same for v in vs]} {b.title[:44]!r} ← {a.title[:34]!r}\n    {vs[0].reason[:150]}")
