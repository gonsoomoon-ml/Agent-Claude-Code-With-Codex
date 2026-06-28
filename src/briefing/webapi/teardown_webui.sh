# src/briefing/webapi/teardown_webui.sh — ④ Web UI 자원 역순 삭제(API + web 공통; web 자원은 deploy_web 후 채워짐).
#!/usr/bin/env bash
set -uo pipefail
REGION="${AWS_REGION:-us-east-1}"
echo "== ④ Web UI teardown (region=$REGION) =="

# --- HTTP API ---
API_ID=$(aws apigatewayv2 get-apis --region "$REGION" \
  --query "Items[?Name=='briefing-webapi-http'].ApiId" --output text 2>/dev/null)
if [ -n "$API_ID" ] && [ "$API_ID" != "None" ]; then
  aws apigatewayv2 delete-api --api-id "$API_ID" --region "$REGION" && echo "deleted HTTP API $API_ID"
fi

# --- Lambda ---
aws lambda delete-function --function-name briefing-webapi --region "$REGION" 2>/dev/null \
  && echo "deleted Lambda briefing-webapi"

# --- IAM role ---
aws iam detach-role-policy --role-name briefing-webapi-lambda-role \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole 2>/dev/null
aws iam delete-role --role-name briefing-webapi-lambda-role 2>/dev/null \
  && echo "deleted role briefing-webapi-lambda-role"

# --- CloudFront + S3 (deploy_web.py 후 존재; 없으면 skip) ---
# CloudFront 는 disable→배포완료대기(~15분)→delete 가 필요해 수동/별도. 아래는 S3 만 정리.
BUCKET=$(aws cloudformation describe-stacks 2>/dev/null >/dev/null; echo "${BRIEFING_WEB_BUCKET:-}")
if [ -n "$BUCKET" ]; then
  aws s3 rm "s3://$BUCKET" --recursive 2>/dev/null && aws s3api delete-bucket --bucket "$BUCKET" --region "$REGION" 2>/dev/null \
    && echo "deleted S3 $BUCKET" || echo "S3 $BUCKET: 비우기/삭제 보류(CloudFront OAC 정책·배포중 가능)"
fi
echo "== teardown done (CloudFront distribution 은 콘솔/별도에서 disable 후 삭제) =="
