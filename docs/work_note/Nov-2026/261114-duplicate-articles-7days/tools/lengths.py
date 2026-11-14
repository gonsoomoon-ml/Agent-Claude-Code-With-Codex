"""쌍별 A·B 본문 길이(읽기 전용)."""
import json
import sys
from briefing.core.config import load_settings
from briefing.core.stores.dynamo import source_store_from_settings
store = source_store_from_settings(load_settings())
pairs = json.load(open(sys.argv[1]))
L = {}
for p in pairs:
    for k in ("a_sid", "b_sid"):
        if p[k] not in L:
            L[p[k]] = len(store.get_source(p[k]).text)
for p in sorted(pairs, key=lambda p: (p["group"], str(p["expect"]), p["run_date"])):
    e = {True: "제외", False: "유지", None: "경계"}[p["expect"]]
    print(f"{p['group']:7} {e} {p['run_date'][5:]} A={L[p['a_sid']]:6} B={L[p['b_sid']]:6} {p['b_media'][:12]:12} {p['b_title'][:38]!r} ← {p['a_media'][:12]} {p['a_title'][:30]!r}")
