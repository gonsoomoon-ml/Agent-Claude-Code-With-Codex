#!/usr/bin/env bash
# 브리핑 영속 계층 DDB 배포(재현 가능). 4 테이블: card-cache · ledger · source-store · users(H4).
# 순수 CFN(infra/ddb.yaml) + 멱등(--no-fail-on-empty-changeset). 옵션 SEED=1 → users/*.yaml → briefing-users 시드.
# 전제: aws CLI + 자격증명. 비용: PAY_PER_REQUEST(idle ≈ $0).
# 사용(저장소 루트 또는 어디서나):
#   bash infra/deploy_ddb.sh                       # 테이블만(멱등)
#   SEED=1 bash infra/deploy_ddb.sh                # 테이블 + users 시드(H4 — runtime 재배포 *전* 필수)
#   AWS_REGION=us-east-1 TABLE_PREFIX=briefing bash infra/deploy_ddb.sh
# 출력: 4 테이블명 → .env(CACHE_TABLE/LEDGER_TABLE/SOURCE_TABLE/USERS_TABLE).
set -euo pipefail

REGION="${AWS_REGION:-us-east-1}"
PREFIX="${TABLE_PREFIX:-briefing}"
STACK="${DDB_STACK:-briefing-ddb}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${HERE}/.." && pwd)"

aws sts get-caller-identity --query Account --output text >/dev/null \
  || { echo "❌ AWS 자격증명 없음"; exit 1; }

echo "▶ deploy ${STACK} (region=${REGION}, prefix=${PREFIX})"
aws cloudformation deploy \
  --region "${REGION}" \
  --stack-name "${STACK}" \
  --template-file "${ROOT}/infra/ddb.yaml" \
  --parameter-overrides "TablePrefix=${PREFIX}" \
  --no-fail-on-empty-changeset

out() {
  aws cloudformation describe-stacks --region "${REGION}" --stack-name "${STACK}" \
    --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue" --output text
}

echo ""
echo "=== ✅ 테이블(.env 에 반영) ==="
echo "CACHE_TABLE=$(out CardCacheTableName)"
echo "LEDGER_TABLE=$(out LedgerTableName)"
echo "SOURCE_TABLE=$(out SourceStoreTableName)"
echo "USERS_TABLE=$(out UsersTableName)"

if [[ "${SEED:-}" == "1" ]]; then
  echo ""
  echo "=== ② users 시드(users/*.yaml → ${PREFIX}-users; ★ skill_md 제외 — 파일 오버레이) ==="
  AWS_REGION="${REGION}" uv run python "${ROOT}/scripts/seed_users.py"
fi

echo ""
echo "⚠️ H4 다음 단계: runtime 재배포(load_user 의 DDB 분기 라이브 반영) — 시드 후에만."
