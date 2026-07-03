#!/usr/bin/env bash
# headless Claude Code(author 하니스)를 Bedrock 로 라우팅해 실행 — 수동 테스트/디버깅 편의용.
#
# 코드의 src/briefing/core/authoring/author.py:bedrock_author_env() 와 *동일* 라우팅을 셸에서 재현한다.
# 글로벌 ~/.claude/settings.json 은 건드리지 않는다(인터랙티브 Claude Code 기본값 보존).
# claude 의 기본 설정엔 Bedrock 라우팅이 없으므로 호출 시 env 를 주입(codex 가 자기 config 로 상주하는 것과 대조).
#
# 사용: scripts/claude-author.sh -p "프롬프트..."   (claude 의 모든 인자를 그대로 전달)
set -euo pipefail

# 프로젝트 루트(.env 위치) 기준 — .env 가 있으면 로드해 AUTHOR_MODEL_ID·AWS_REGION 을 앱과 단일 출처로 공유
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
fi

exec env \
  CLAUDE_CODE_USE_BEDROCK=1 \
  AWS_REGION="${AWS_REGION:-us-east-1}" \
  ANTHROPIC_MODEL="${AUTHOR_MODEL_ID:-global.anthropic.claude-sonnet-4-6}" \
  ENABLE_TOOL_SEARCH=false \
  claude "$@"
