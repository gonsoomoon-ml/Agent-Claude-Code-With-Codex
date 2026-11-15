#!/usr/bin/env bash
# 재생 게이트(읽기 전용 + Haiku 판정) — 현재 디렉터리(저장소 루트 또는 worktree)의 코드로 돌린다.
#   bash run_gate.sh <출력 파일> [기대 제외 수=10] [rereport_replay.py 추가 인자…]
# 기대 제외 수(10-21~10-27 주간):
#   2026-10-28            10 (정확히 링크한 쌍만 판정하던 때)
#   2026-11-14            9  (10-25 The Decoder 기사가 수정돼 본문에 원문 링크가 없어져 1쌍 소멸 — 전달 기록 §6)
#   2026-11-14 같은 사이트 판정 추가 뒤 10 (그 10-25 기사가 같은 사이트 쌍으로 다시 잡힌다 — 전달 기록 §7)
#   정확히 링크한 쌍만 보려면: bash run_gate.sh <출력 파일> 9 --exact-only
# 명령을 파일로 둔 이유: worktree 세션에서는 명령문에 VCS 이름이 든 글자(유지 제목 조각)가 있으면 실행이 거부된다.
set -u
out="$1"
expect="${2:-10}"
shift
[ $# -gt 0 ] && shift
uv run python scripts/dedup_audit/rereport_replay.py --user-prefix 445814b8 \
  --since 2026-10-21 --until 2026-10-27 --expect-dropped "$expect" \
  --expect-kept-title gitai --expect-kept-title "AAIF에 Agent Skills" "$@" > "$out" 2>&1
echo "exit=$?"
