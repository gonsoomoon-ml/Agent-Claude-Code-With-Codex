#!/usr/bin/env python
"""headline_check — 헤드라인 칸(AI타임스, 한국어 제목만) 분야 분류 임시 점검(스펙 §7 Q4): 라이브 피드 50제목 × 2회.

보고: 제목별 배정 수(미배정)·2회 일치율·all-or-nothing(운영 경로 `llm_headline_areas`) 결과·제목별 표(손 검토용).
합격선: 미배정 0 · 2회 일치 ≥ 90% · 50건 손 검토 1회(결과는 md 에 손으로 추가).

usage: uv run python scripts/area_eval/headline_check.py [--n 50] [--window-hours 72] [--out-dir DIR]
비용: Sonnet 5.5 × 2콜(≈ $0.02). 실패 시 헤드라인 호출만 Haiku·구 정의로 두는 선택지(스펙 §7).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from briefing.core.areas import AREAS
from briefing.core.config import load_settings
from briefing.core.retrieval import headlines as H
from briefing.core.retrieval import relevance_bedrock as rb
from briefing.core.retrieval import sources as src

DEFAULT_OUT = Path("docs/work_note/Oct-2026/261024-Reorder-Content")


def assign_tolerant(titles: list[str], invoke) -> list[str]:
    """llm_headline_areas 와 같은 파싱이되 일부 미배정도 그대로 돌려준다(제목별 집계용)."""
    ans = invoke(H._AREA_SYSTEM, "\n".join(f"{i}. {t}" for i, t in enumerate(titles, start=1))) or ""
    objs = re.findall(r"\{[^{}]*\}", ans)
    d = json.loads(objs[-1]) if objs else {}
    areas = [""] * len(titles)
    for area, nums in (d.items() if isinstance(d, dict) else []):
        if area not in AREAS:
            continue
        for i in nums if isinstance(nums, list) else []:
            if isinstance(i, int) and 1 <= i <= len(titles) and not areas[i - 1]:
                areas[i - 1] = area
    return areas


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--window-hours", type=int, default=72)
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    a = ap.parse_args(argv)
    source = src.resolve_sources(["aitimes"])[0]
    titles = [x.title for x in H.fetch_headline_feed(source, a.window_hours)][: a.n]
    settings = load_settings()
    client, model = rb._client(settings.region), rb._label_model(settings)
    invoke = lambda s, u: rb._converse_label_text(client, model, s, u)  # noqa: E731
    p1, p2 = assign_tolerant(titles, invoke), assign_tolerant(titles, invoke)
    strict = H.llm_headline_areas(titles, invoke=invoke)     # 운영 경로(all-or-nothing) — 3회차
    both = [i for i in range(len(titles)) if p1[i] and p2[i]]
    agree = (sum(1 for i in both if p1[i] == p2[i]) / len(both)) if both else 0.0
    unassigned = (p1.count(""), p2.count(""))
    ok = unassigned == (0, 0) and agree >= 0.9 and bool(strict)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    out = [f"# 헤드라인 분야 임시 점검 ({ts}) — 모델 `{model}` · 제목 {len(titles)}건(창 {a.window_hours}h)\n",
           f"- 미배정: 1회차 {unassigned[0]} · 2회차 {unassigned[1]} → {'OK' if unassigned == (0, 0) else 'FAIL'}",
           f"- 2회 일치: {agree:.1%} (양쪽 배정 {len(both)}건 기준) → {'OK' if agree >= 0.9 else 'FAIL'}",
           f"- 운영 경로(all-or-nothing, 3회차): {'소제목 OK' if strict else '소제목 없음(폴백)'}",
           f"- **판정: {'PASS' if ok else 'FAIL'}** (손 검토 결과는 아래 표에 ✗ 표시와 사유를 손으로 추가)\n",
           "| # | 1회차 | 2회차 | 제목 | 손 검토 |", "|---|---|---|---|---|"]
    out += [f"| {i + 1} | {p1[i] or '—'} | {p2[i] or '—'} | {t} | |" for i, t in enumerate(titles)]
    a.out_dir.mkdir(parents=True, exist_ok=True)
    path = a.out_dir / f"headline-check-{ts}.md"
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out[:5]), f"\n→ {path}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
