#!/usr/bin/env bash
# src/briefing/webapi/teardown_webui.sh — ④ Web UI 자원 역순 삭제(API + web 공통; web 자원은 deploy_web 후 채워짐).
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

# --- CloudFront + S3 ---
source "$(git rev-parse --show-toplevel)/.env" 2>/dev/null || true
if [ -n "${BRIEFING_CF_DIST_ID:-}" ]; then
  ETAG=$(aws cloudfront get-distribution-config --id "$BRIEFING_CF_DIST_ID" --query ETag --output text 2>/dev/null)
  if [ -n "$ETAG" ] && [ "$ETAG" != "None" ]; then
    echo "CloudFront $BRIEFING_CF_DIST_ID: disable 후 콘솔/CLI 로 삭제 필요(전파 ~15분)."
    echo "  1) get-distribution-config → Enabled:false 로 update-distribution(--if-match $ETAG)"
    echo "  2) 배포 Deployed 후 delete-distribution --if-match <new ETag>"
  fi
fi
if [ -n "${BRIEFING_WEB_BUCKET:-}" ]; then
  aws s3 rm "s3://$BRIEFING_WEB_BUCKET" --recursive 2>/dev/null
  aws s3api delete-bucket --bucket "$BRIEFING_WEB_BUCKET" --region "$REGION" 2>/dev/null \
    && echo "deleted S3 $BRIEFING_WEB_BUCKET" || echo "S3 삭제 보류(CloudFront 가 아직 참조 중일 수 있음)"
fi
echo "== teardown done (CloudFront distribution 은 콘솔/별도에서 disable 후 삭제) =="
