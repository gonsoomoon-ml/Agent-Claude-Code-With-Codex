#!/usr/bin/env python
"""ab_judge — A/B 산출물을 **블라인드 심사용 자료**로 변환.

**왜 필요한가:** `ab_prompt.py` 의 앵커 최심은 *다 쏟아붓기에 상을 준다* — 요약이 길수록 앵커가
많아 최심이 깊어진다. 그래서 예산 있는 팔(v3.1)은 **필연적으로** 최심이 낮고, 지표만으론
"옳은 사실을 골랐는가"를 알 수 없다. 그건 지표가 아니라 판단이다.

이 스크립트는 심사자에게 줄 자료를 만든다:
  · 팔 이름을 **가린다**(A/B/C) — 어느 게 신형인지 알면 심사가 오염된다.
  · 라벨 배정을 **기사마다 섞는다** — 위치 편향(항상 A 가 신형) 차단.
  · 매핑은 별도 파일로 빼서 심사 후에만 연다.

usage: uv run python scripts/ab_judge.py > judge_packet.md
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_SCRATCH = Path("/tmp/claude-1000/-home-ubuntu-Agent-Claude-Code-With-Codex/"
                "a80ab529-104b-4976-8e30-7d1cb2390975/scratchpad")
_LABELS = "ABC"


def main() -> None:
    rows = json.loads((_SCRATCH / "ab_result.json").read_text(encoding="utf-8"))
    key: dict[str, dict[str, str]] = {}
    out: list[str] = []

    for i, r in enumerate(rows):
        arms = [a for a in ("v2", "v3", "v3.1") if a in r]
        if len(arms) < 2:
            continue
        # 기사마다 라벨을 회전 — 결정론(재현 가능)이면서 위치 편향은 없앤다.
        rot = i % len(arms)
        mapping = {_LABELS[j]: arms[(j + rot) % len(arms)] for j in range(len(arms))}
        key[r["title"][:60]] = mapping

        out.append(f"\n{'=' * 96}\n## 기사 {i + 1}: {r['title']}\n원문 {r['src_len']}자\n{'=' * 96}\n")
        for lab in _LABELS[: len(arms)]:
            a = r[mapping[lab]]
            out.append(f"\n### 요약 {lab}  ({a['len']}자 · {a['sent']}문장)\n\n{a['summary']}\n")

    (_SCRATCH / "judge_key.json").write_text(json.dumps(key, ensure_ascii=False, indent=1),
                                             encoding="utf-8")
    sys.stdout.write("".join(out))
    print(f"\n\n(매핑 = {_SCRATCH / 'judge_key.json'} — 심사 후에만 열 것)", file=sys.stderr)


if __name__ == "__main__":
    main()
