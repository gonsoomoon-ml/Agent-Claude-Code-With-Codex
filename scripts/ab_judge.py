#!/usr/bin/env python
"""ab_judge — A/B 산출물을 **블라인드 심사 자료**로 변환.

**왜 필요한가:** `ab_prompt.py` 의 앵커 최심은 *다 쏟아붓기에 상을 준다* — 요약이 길수록 앵커가
많아 최심이 깊어진다. 그래서 예산 있는 팔(v3.1)은 **필연적으로** 최심이 낮고, 지표만으론
"옳은 사실을 골랐는가"를 알 수 없다. 그건 지표가 아니라 판단이다.

심사 오염 방지 3장치:
  · 팔 이름을 **가린다**(A/B/C) — 어느 게 신형인지 알면 심사가 기운다.
  · 라벨 배정을 **기사마다 회전** — 위치 편향(항상 A 가 신형) 차단. 결정론이라 재현 가능.
  · 팔마다 **길이 중앙값 반복**을 보인다 — 최고도 최악도 아닌 *전형*(체리피킹 금지).
    (반복 간 흔들림이 크다: 같은 v2 가 같은 기사에 343↔984자.)

매핑은 `judge_key.json` 으로 빼둔다 — **심사가 끝난 뒤에만** 연다.

usage: uv run python scripts/ab_judge.py > packet.md      # 자료는 stdout, 매핑은 파일
"""
from __future__ import annotations

import json
import statistics
import sys

from scripts.ab_prompt import _SCRATCH, _sample

_LABELS = "ABCDEF"


def _typical(recs: list[dict]) -> dict:
    """팔의 *전형* 산출물 = 길이 중앙값 반복(동률이면 rep 낮은 쪽 — 결정론)."""
    ok = sorted((r for r in recs if "error" not in r), key=lambda r: (r["len"], r["rep"]))
    return ok[len(ok) // 2] if ok else {}


def main() -> None:
    rows = json.loads((_SCRATCH / "ab_result.json").read_text(encoding="utf-8"))
    n = max(r["idx"] for r in rows) + 1
    sample = _sample(n)

    key: dict[str, dict[str, str]] = {}
    out: list[str] = []

    for i, (fs, prod_sd, prod_cd) in enumerate(sample):
        arms = sorted({r["arm"] for r in rows if r["idx"] == i})
        picks = {a: _typical([r for r in rows if r["idx"] == i and r["arm"] == a]) for a in arms}
        picks = {a: p for a, p in picks.items() if p}
        if len(picks) < 2:
            continue
        names = sorted(picks)
        rot = i % len(names)                       # 기사마다 라벨 회전 = 위치 편향 차단
        mapping = {_LABELS[j]: names[(j + rot) % len(names)] for j in range(len(names))}
        key[f"기사{i}"] = {"title": fs.title, **mapping}

        out.append(f"\n\n{'=' * 100}\n# 기사 {i}: {fs.title}\n{'=' * 100}\n")
        out.append(f"\n## 원문 ({len(fs.text)}자)\n\n{fs.text}\n")
        out.append(f"\n## 이 기사의 요약 후보 {len(names)}개\n")
        for lab in _LABELS[: len(names)]:
            p = picks[mapping[lab]]
            reps = [r["len"] for r in rows
                    if r["idx"] == i and r["arm"] == mapping[lab] and "error" not in r]
            spread = f"같은 설정 반복 {len(reps)}회 길이 {min(reps)}~{max(reps)}자" if len(reps) > 1 else ""
            out.append(f"\n### 후보 {lab}  ({p['len']}자 · {p['sent']}문장{' · ' + spread if spread else ''})\n\n"
                       f"{p['summary']}\n")

    (_SCRATCH / "judge_key.json").write_text(json.dumps(key, ensure_ascii=False, indent=1),
                                             encoding="utf-8")
    sys.stdout.write("".join(out))
    lens_note = statistics.median([r["len"] for r in rows if "error" not in r])
    print(f"\n\n(전체 median 길이 {lens_note:.0f}자 · 매핑={_SCRATCH / 'judge_key.json'} — "
          f"심사 후에만 열 것)", file=sys.stderr)


if __name__ == "__main__":
    main()
