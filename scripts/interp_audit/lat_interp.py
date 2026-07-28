# -*- coding: utf-8 -*-
"""해석층 순차 지연 실측 — **동시성 1 = 프로덕션 조건**.

파일럿의 초는 동시 4 실행이라 부풀려진다(pipeline 은 카드를 순차 처리). 배포 전 타임아웃 위험
판단에는 순차 실측이 필요하다 — 2026-07-28 아침, 동시 실행 수치를 믿었다가 장문 기사가
프로덕션에서 통째로 드롭될 뻔했다(fat 조항: 동시에선 두 팔 다 타임아웃이라 차이가 묻혔고,
순차로 재니 195s 완주 vs 400s 실패였다).

기준: 프로덕션 한도 `_AUTHOR_TIMEOUT_S = 360s`. 게이트 = 최대 지연 < 300s.

usage: uv run python scripts/interp_audit/lat_interp.py [arm,arm] [N]   # 기본: base,beyond × 6(장문 우선)
"""
import os
import sys
import time


import briefing.core.authoring.author as A
from briefing.core.authoring.author import _parse_interp, _run_author, build_interp_user_prompt
from briefing.core.config import load_settings
from briefing.core.lenses import resolve_lens
from pilot import ARMS, load_sample, system_for

# 중간 산출물(JSON) 보관 위치 — 코드만 저장소에 살고 데이터(수 MB·재생성 가능)는 밖에 둔다.
DATA = os.environ.get("INTERP_AUDIT_DIR", "/tmp/interp-audit")
os.makedirs(DATA, exist_ok=True)

A._AUTHOR_TIMEOUT_S = 420   # 게이트(300s)보다 여유 — 초과분도 값으로 보기 위해


def main():
    arms = sys.argv[1].split(",") if len(sys.argv) > 1 else ["base", "beyond"]
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 6
    s = load_settings()
    lensg = resolve_lens("engineer").guidance
    sample = load_sample(30)
    # 장문 우선 — 지연 위험은 거기 있다
    sample.sort(key=lambda it: -len(it["src"].text))
    sample = sample[:n]
    print(f"순차(동시성 1) · 표본 {len(sample)}건(장문 우선) · 팔 {arms} · 프로덕션 한도 360s\n")

    res = {a: [] for a in arms}
    for it in sample:
        for a in arms:
            sysmsg = system_for(a, lensg)
            user = build_interp_user_prompt(it["src"], it["claims"], today="2026-07-28")
            if ARMS[a].get("show_summary"):
                user = f"[이미 발행된 요약]\n{it['summary']}\n\n" + user
            t0 = time.monotonic()
            try:
                why = _parse_interp(_run_author(sysmsg, user, s)).why_it_matters
                el = time.monotonic() - t0
                res[a].append(el)
                print(f"  {len(it['src'].text):>5}자 · {a:<8} {el:>6.0f}s · why {len(why):>3}자 · {it['headline'][:38]}",
                      flush=True)
            except Exception as e:  # noqa: BLE001
                el = time.monotonic() - t0
                res[a].append(el)
                print(f"  {len(it['src'].text):>5}자 · {a:<8} {el:>6.0f}s · 실패 {type(e).__name__}", flush=True)

    import statistics as st
    print("\n" + "=" * 64)
    for a in arms:
        v = res[a]
        over = sum(1 for x in v if x > 300)
        print(f"{a:<9} n={len(v)} · median {st.median(v):>5.0f}s · max {max(v):>5.0f}s · "
              f"300s 초과 {over}/{len(v)}  {'✅' if max(v) < 300 else '❌ 게이트 실패'}")


if __name__ == "__main__":
    main()
