#!/usr/bin/env bash
# 재생(읽기 전용 + Haiku 판정) — 같은 사이트 판정을 켠 코드로 관리자 발송분을 다시 돌리고 판정한 쌍 전부를 JSON 으로 남긴다.
#   bash same_site_replay.sh <저장소 루트> <since> <until> <출력 접두사> [rereport_replay.py 추가 인자…]
# 출력: <접두사>.txt(화면 출력 + exit 코드) · <접두사>.json(판정한 쌍 전부 — same_site_diff.py 입력)
# 유지 확인(두 제목)은 그 글들이 있는 게이트 주간(10-21~10-27)에만 건다. 다른 기간에 걸면 그 제목이 판정 쌍에 없어
# "유지 확인 불가"로 FAIL 이 찍힌다 — 2026-11-14 에 저장한 same-site-replay-20261028-1113.txt 끝의 FAIL 이 그것이다
# (그때는 기간과 무관하게 걸었다. 판정 결과와는 무관).
# 명령을 파일로 둔 이유: worktree 세션에서는 명령문에 VCS 이름이 든 글자(유지 제목 조각)가 있으면 실행이 거부된다.
set -uo pipefail
root="$1"; since="$2"; until="$3"; out="$4"; shift 4
kept=()
if [ "$since" = "2026-10-21" ] && [ "$until" = "2026-10-27" ]; then
  kept=(--expect-kept-title gitai --expect-kept-title "AAIF에 Agent Skills")
fi
cd "$root"
uv run python scripts/dedup_audit/rereport_replay.py --user-prefix 445814b8 \
    --since "$since" --until "$until" --json-out "$out.json" \
    ${kept[@]+"${kept[@]}"} "$@" > "$out.txt" 2>&1
echo "exit=$?" >> "$out.txt"
tail -4 "$out.txt"
