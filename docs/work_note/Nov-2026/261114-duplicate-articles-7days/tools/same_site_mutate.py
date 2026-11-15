#!/usr/bin/env python3
"""가드별 변이 검사 — 같은 사이트 판정(rereport_dedup (c))의 가드 한 줄을 지웠을 때 그 가드를 지키는 테스트가
실패하는지 본다. ★ `src/briefing/core/rereport_dedup.py` 를 잠깐 고쳐 쓰고 끝나면(예외가 나도) 원본으로 되돌린다.

    uv run python docs/work_note/Nov-2026/261114-duplicate-articles-7days/tools/same_site_mutate.py <저장소 루트>

바꿀 문자열이 소스에 정확히 1번 있어야 한다 — 코드가 바뀌어 못 찾으면 그 변이에서 assert 로 멈춘다.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

root = Path(sys.argv[1])
target = root / "src/briefing/core/rereport_dedup.py"
orig = target.read_text(encoding="utf-8")

MUTATIONS = [
    ("분야 조건 제거", " or b_cat not in SAME_SITE_B_CATEGORIES", "",
     "test_drop_rereports_same_site_never_asks_about_first_party_b"),
    ("정확히 걸린 링크도 호스트를 냄", "for k in keys if k not in sent_index and k not in by_url)", "for k in keys)",
     "test_drop_rereports_same_site_exact_link_adds_no_site_candidates"),
    ("정확히 인용한 A 를 후보에서 안 뺌",
     "skip = {b.source_id} | {sent_index[k] for k in keys if k in sent_index} \\\n"
     "            | {by_url[k][0].source_id for k in keys if k in by_url}",
     "skip = {b.source_id}",
     "test_drop_rereports_same_site_leaves_exactly_cited_pair_to_exact_rules"),
    ("같은 매체 건너뛰기 제거", "if a.source_id in drops or a.media == b.media:", "if a.source_id in drops:",
     "test_drop_rereports_same_site_skips_same_media"),
    ("빠진 A 를 다시 씀", "if a.source_id in drops or a.media == b.media:", "if a.media == b.media:",
     "test_drop_rereports_same_site_dropped_a_is_not_used"),
    ("원본 없음 예외를 안 잡음", "except Exception:  # noqa: BLE001 — 원본 없음은 그 후보만 건너뛴다", "except ZeroDivisionError:",
     "test_drop_rereports_same_site_skips_candidate_without_source"),
    ("(c) 를 기본으로 켬", "if recent_hosts is None:\n        return drops", "recent_hosts = recent_hosts or {}",
     "test_drop_rereports_same_site_is_off_without_recent_hosts"),
]

ok = True
try:
    for label, old, new, test in MUTATIONS:
        assert orig.count(old) == 1, (label, orig.count(old))
        target.write_text(orig.replace(old, new), encoding="utf-8")
        r = subprocess.run(["uv", "run", "pytest", "tests/test_rereport_dedup.py", "-q", "-k", test, "-p", "no:cacheprovider"],
                           cwd=root, capture_output=True, text=True)
        failed = r.returncode != 0
        ok &= failed
        print(f"{'잡음' if failed else '못 잡음 ★'}  {label} → {test}")
finally:
    target.write_text(orig, encoding="utf-8")
print("전부 잡음" if ok else "못 잡은 변이가 있음")
sys.exit(0 if ok else 1)
