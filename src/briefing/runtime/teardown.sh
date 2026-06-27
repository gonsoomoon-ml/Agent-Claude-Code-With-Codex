#!/usr/bin/env bash
# teardown.sh — ② Briefing Runtime 자원 reverse 순서 삭제 (deploy_runtime.py 의 역).
# aiops monitor/runtime/teardown.sh 미러. OAuth/Cognito 단계는 우리(v1 공개 RSS)에 없음 → 제거.
# 삭제: Runtime → (DELETED 대기) → ECR repo(images 포함) → IAM role(inline+managed detach) → CW log group.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
[ -f "$PROJECT_ROOT/.env" ] && { set -a; source "$PROJECT_ROOT/.env"; set +a; }

REGION="${AWS_REGION:-us-east-1}"
AGENT_NAME="${BRIEFING_RUNTIME_NAME:-briefing_agent}"
RUNTIME_ID="${BRIEFING_RUNTIME_ID:-}"
ECR_REPO="bedrock-agentcore-${AGENT_NAME}"
LOG_GROUP_PREFIX="/aws/bedrock-agentcore/runtimes/${AGENT_NAME}-"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
echo -e "${YELLOW}=== ② teardown — ${AGENT_NAME} (region=${REGION}) ===${NC}"

# ── [1/5] Runtime 삭제 ──────────────────────────────────────────
echo -e "${YELLOW}[1/5] Runtime 삭제${NC}"
RUNTIME_ID="${RUNTIME_ID:-$(aws bedrock-agentcore-control list-agent-runtimes --region "$REGION" \
    --query "agentRuntimes[?agentRuntimeName=='${AGENT_NAME}'].agentRuntimeId" --output text 2>/dev/null || echo '')}"
# IAM role 은 runtime 삭제 전에 조회(삭제 후엔 못 읽음)
ROLE_ARN="$(aws bedrock-agentcore-control get-agent-runtime --region "$REGION" \
    --agent-runtime-id "${RUNTIME_ID:-none}" --query 'roleArn' --output text 2>/dev/null || echo '')"
if [ -n "${RUNTIME_ID:-}" ] && [ "$RUNTIME_ID" != "None" ]; then
    aws bedrock-agentcore-control delete-agent-runtime --region "$REGION" --agent-runtime-id "$RUNTIME_ID" || true
    echo -e "  ${GREEN}✓ Runtime ${RUNTIME_ID} 삭제 요청${NC}"
else
    echo -e "  (Runtime 없음 — skip)"
fi

# ── [2/5] DELETED 대기 ──────────────────────────────────────────
echo -e "${YELLOW}[2/5] Runtime DELETED 대기 (max 60s)${NC}"
if [ -n "${RUNTIME_ID:-}" ] && [ "$RUNTIME_ID" != "None" ]; then
    for i in $(seq 1 12); do
        STATUS=$(aws bedrock-agentcore-control get-agent-runtime --region "$REGION" \
            --agent-runtime-id "$RUNTIME_ID" --query 'status' --output text 2>/dev/null || echo "NOT_FOUND")
        { [ "$STATUS" = "NOT_FOUND" ] || [ "$STATUS" = "DELETED" ]; } && { echo -e "  ${GREEN}✓ ${STATUS}${NC}"; break; }
        echo -e "  [${i}/12] ${STATUS}"; sleep 5
    done
fi

# ── [3/5] ECR repo 삭제 (images 포함) ───────────────────────────
echo -e "${YELLOW}[3/5] ECR Repository 삭제${NC}"
if aws ecr describe-repositories --region "$REGION" --repository-names "$ECR_REPO" >/dev/null 2>&1; then
    aws ecr delete-repository --region "$REGION" --repository-name "$ECR_REPO" --force >/dev/null
    echo -e "  ${GREEN}✓ ${ECR_REPO} 삭제${NC}"
else
    echo -e "  (ECR repo 없음 — skip)"
fi

# ── [4/5] IAM role 삭제 (inline=BriefingRuntimeExtras 포함 detach → delete) ──
echo -e "${YELLOW}[4/5] IAM Role 삭제${NC}"
ROLE_NAME="${ROLE_ARN:+${ROLE_ARN##*/}}"
if [ -n "$ROLE_NAME" ] && [ "$ROLE_NAME" != "None" ] && aws iam get-role --role-name "$ROLE_NAME" >/dev/null 2>&1; then
    for P in $(aws iam list-role-policies --role-name "$ROLE_NAME" --query 'PolicyNames' --output text); do
        aws iam delete-role-policy --role-name "$ROLE_NAME" --policy-name "$P"; echo -e "  detached inline: $P"
    done
    for PA in $(aws iam list-attached-role-policies --role-name "$ROLE_NAME" --query 'AttachedPolicies[].PolicyArn' --output text); do
        aws iam detach-role-policy --role-name "$ROLE_NAME" --policy-arn "$PA"; echo -e "  detached managed: $PA"
    done
    aws iam delete-role --role-name "$ROLE_NAME"
    echo -e "  ${GREEN}✓ Role ${ROLE_NAME} 삭제${NC}"
else
    echo -e "  (Role 없음 — skip)"
fi

# ── [5/5] CW log group 삭제 (prefix — redeploy 흔적 포함) ────────
echo -e "${YELLOW}[5/5] CW Log Group 삭제${NC}"
N=0
for LG in $(aws logs describe-log-groups --region "$REGION" --log-group-name-prefix "$LOG_GROUP_PREFIX" \
    --query 'logGroups[].logGroupName' --output text 2>/dev/null); do
    aws logs delete-log-group --region "$REGION" --log-group-name "$LG" 2>/dev/null && { echo -e "  ${GREEN}✓ ${LG}${NC}"; N=$((N+1)); }
done
[ "$N" -eq 0 ] && echo -e "  (Log Group 없음 — skip)"

# ── 루트 .env 의 BRIEFING_RUNTIME_* + 섹션 마커 cleanup ─────────
if [ -f "$PROJECT_ROOT/.env" ]; then
    sed -i.bak '/^BRIEFING_RUNTIME_NAME=/d; /^BRIEFING_RUNTIME_ARN=/d; /^BRIEFING_RUNTIME_ID=/d; /^# ② Briefing Runtime/d' "$PROJECT_ROOT/.env"
    rm -f "$PROJECT_ROOT/.env.bak"
    echo -e "  ${GREEN}✓ .env 의 BRIEFING_RUNTIME_* cleanup${NC}"
fi
echo -e "${GREEN}=== ✅ ② teardown 완료 ===${NC}"
