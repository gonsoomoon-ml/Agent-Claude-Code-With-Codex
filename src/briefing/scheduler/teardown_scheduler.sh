#!/usr/bin/env bash
# teardown_scheduler.sh — ⑤ 자원 역순 삭제 (deploy_scheduler.py 의 역).
# 삭제: schedule 3개(시간당 + 주간 build/send) → Lambda → log group → scheduler role → lambda role → DDB 표 2개 → .env cleanup.
# ②(runtime)·③(DDB card/ledger/source)는 미터치 — 각자 teardown.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
[ -f "$PROJECT_ROOT/.env" ] && { set -a; source "$PROJECT_ROOT/.env"; set +a; }

REGION="${AWS_REGION:-us-east-1}"
LAMBDA_NAME="${BRIEFING_SCHEDULER_LAMBDA_NAME:-briefing-scheduler-dispatch}"
SCHEDULE_NAME="${BRIEFING_SCHEDULER_SCHEDULE_NAME:-briefing-hourly-tick}"
LAMBDA_ROLE="${BRIEFING_SCHEDULER_LAMBDA_ROLE:-briefing-scheduler-lambda-role}"
SCHED_ROLE="${BRIEFING_SCHEDULER_EVENTBRIDGE_ROLE:-briefing-scheduler-eventbridge-role}"
SENT_LOG_TABLE="${BRIEFING_SENT_LOG_TABLE:-briefing-sent-log}"
WEEKLY_ISSUES_TABLE="${BRIEFING_WEEKLY_ISSUES_TABLE:-briefing-weekly-issues}"
WEEKLY_SCHEDULES="briefing-weekly-build briefing-weekly-send"   # deploy_scheduler.py SCHEDULES 와 같다
LOG_GROUP="/aws/lambda/${LAMBDA_NAME}"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
echo -e "${YELLOW}=== ⑤ scheduler teardown (region=${REGION}) ===${NC}"

_del_role() {  # $1=role name — inline+managed detach 후 삭제
    local R="$1"
    aws iam get-role --role-name "$R" >/dev/null 2>&1 || { echo -e "  (role ${R} 없음 — skip)"; return; }
    for P in $(aws iam list-role-policies --role-name "$R" --query 'PolicyNames' --output text); do
        aws iam delete-role-policy --role-name "$R" --policy-name "$P"
    done
    for PA in $(aws iam list-attached-role-policies --role-name "$R" --query 'AttachedPolicies[].PolicyArn' --output text); do
        aws iam detach-role-policy --role-name "$R" --policy-arn "$PA"
    done
    aws iam delete-role --role-name "$R" && echo -e "  ${GREEN}✓ role ${R}${NC}"
}

echo -e "${YELLOW}[1/6] schedule 삭제${NC}"
for S in "$SCHEDULE_NAME" $WEEKLY_SCHEDULES; do
    aws scheduler delete-schedule --name "$S" --region "$REGION" 2>/dev/null \
        && echo -e "  ${GREEN}✓ ${S}${NC}" || echo -e "  (schedule ${S} 없음 — skip)"
done

echo -e "${YELLOW}[2/6] Lambda 삭제${NC}"
aws lambda delete-function --function-name "$LAMBDA_NAME" --region "$REGION" 2>/dev/null \
    && echo -e "  ${GREEN}✓ ${LAMBDA_NAME}${NC}" || echo -e "  (Lambda 없음 — skip)"

echo -e "${YELLOW}[3/6] CW Log Group 삭제${NC}"
aws logs delete-log-group --log-group-name "$LOG_GROUP" --region "$REGION" 2>/dev/null \
    && echo -e "  ${GREEN}✓ ${LOG_GROUP}${NC}" || echo -e "  (Log Group 없음 — skip)"

echo -e "${YELLOW}[4/6] Scheduler role 삭제${NC}"; _del_role "$SCHED_ROLE"
echo -e "${YELLOW}[5/6] Lambda role 삭제${NC}"; _del_role "$LAMBDA_ROLE"

echo -e "${YELLOW}[6/6] DDB 테이블 삭제(sent-log · weekly-issues)${NC}"
for T in "$SENT_LOG_TABLE" "$WEEKLY_ISSUES_TABLE"; do
    aws dynamodb delete-table --table-name "$T" --region "$REGION" >/dev/null 2>&1 \
        && echo -e "  ${GREEN}✓ ${T}${NC}" || echo -e "  (테이블 ${T} 없음 — skip)"
done

if [ -f "$PROJECT_ROOT/.env" ]; then
    sed -i.bak '/^BRIEFING_SCHEDULER_/d; /^BRIEFING_SENT_LOG_TABLE=/d; /^BRIEFING_WEEKLY_ISSUES_TABLE=/d; /^# ⑤ Briefing Scheduler/d' "$PROJECT_ROOT/.env"
    rm -f "$PROJECT_ROOT/.env.bak"
    echo -e "  ${GREEN}✓ .env cleanup${NC}"
fi
echo -e "${GREEN}=== ✅ ⑤ teardown 완료 ===${NC}"
