#!/usr/bin/env bash
# 브리핑 ④ H3 — 인간 end-user Cognito pool 배포(재현 가능). 순수 CFN, 출력 = 핸드셰이크 5값.
#
# 무엇: self sign-up + hosted UI + public SPA client(authorization_code+PKCE)를 가진 별도 Cognito pool 생성
#       — Gateway M2M pool(infra/gateway/)과 물리적으로 분리. 멱등(재실행 안전 — no-fail-on-empty-changeset).
# 전제: aws CLI + 자격증명(us-east-1). 비용 ~0 (Cognito MAU 무료구간 + 기본 이메일).
# 사용:
#   bash infra/auth/deploy_users.sh                              # 기본(gonsoo·us-east-1·템플릿 기본 URL)
#   AWS_REGION=us-east-1 DEMO_USER=alice \
#     CALLBACK_URLS="https://app.example/cb,http://localhost:5173/" \
#     LOGOUT_URLS="https://app.example/,http://localhost:5173/" \
#     bash infra/auth/deploy_users.sh                            # ④ 가 실제 프론트 URL 확정 시
# 출력: 끝에 5개 핸드셰이크 값 → .env 또는 design/architecture/lane-a-handshake-web-ui.md 로 LANE B 전달.
set -euo pipefail

REGION="${AWS_REGION:-us-east-1}"
DEMO_USER="${DEMO_USER:-gonsoo}"
STACK="briefing-users-${DEMO_USER}-auth"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATE="${HERE}/cognito-users.yaml"

aws sts get-caller-identity --query Account --output text >/dev/null \
  || { echo "❌ AWS 자격증명 없음"; exit 1; }

# DemoUser 는 항상, callback/logout URL 은 env 로 줄 때만 override(아니면 템플릿 기본).
PARAMS=("DemoUser=${DEMO_USER}")
[[ -n "${CALLBACK_URLS:-}" ]] && PARAMS+=("CallbackUrls=${CALLBACK_URLS}")
[[ -n "${LOGOUT_URLS:-}" ]] && PARAMS+=("LogoutUrls=${LOGOUT_URLS}")

echo "▶ deploy ${STACK} (region=${REGION}, user=${DEMO_USER})"
aws cloudformation deploy \
  --region "${REGION}" \
  --stack-name "${STACK}" \
  --template-file "${TEMPLATE}" \
  --parameter-overrides "${PARAMS[@]}" \
  --no-fail-on-empty-changeset

out() {
  aws cloudformation describe-stacks --region "${REGION}" --stack-name "${STACK}" \
    --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue" --output text
}

echo ""
echo "=== ✅ H3 핸드셰이크 값 (LANE B 로 전달 / .env) ==="
echo "COGNITO_USER_POOL_ID=$(out UserPoolId)"
echo "COGNITO_REGION=$(out Region)"
echo "COGNITO_HOSTED_UI=$(out HostedUI)"
echo "COGNITO_PUBLIC_CLIENT_ID=$(out PublicClientId)"
echo "JWT_AUDIENCE=$(out JwtAudience)"
