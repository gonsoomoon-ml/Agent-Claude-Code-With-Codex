#!/usr/bin/env bash
# 재생 게이트(읽기 전용 + Haiku 판정) — 현재 디렉터리(저장소 루트 또는 worktree)의 코드로 돌린다.
#   bash run_gate.sh <출력 파일> [기대 제외 수=9]
# 기대 제외 수: 2026-10-28 에는 10, 2026-11-14 부터 9(10-25 The Decoder 기사가 수정돼 1쌍 소멸 — 전달 기록 §6).
# 명령을 파일로 둔 이유: worktree 세션에서는 명령문에 VCS 이름이 든 글자(유지 제목 조각)가 있으면 실행이 거부된다.
set -u
uv run python scripts/dedup_audit/rereport_replay.py --user-prefix 445814b8 \
  --since 2026-10-21 --until 2026-10-27 --expect-dropped "${2:-9}" \
  --expect-kept-title gitai --expect-kept-title "AAIF에 Agent Skills" > "$1" 2>&1
echo "exit=$?"
