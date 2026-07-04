# infra — 배포 단위 인덱스 (CFN + 셸 배포자)
| 배포 단위 | 코드 | 배포/철거 | CFN |
|---|---|---|---|
| ② AgentCore 컨테이너 | `src/briefing/runtime/` | `uv run python -m briefing.runtime.deploy_runtime` · `runtime/teardown.sh` | (toolkit 관리) |
| ① Gateway Lambda | `src/briefing/gateway/` | `uv run python -m briefing.gateway.deploy_gateway` | `infra/gateway/cognito.yaml` |
| ⑤ scheduler Lambda | `src/briefing/scheduler/` | `-m briefing.scheduler.deploy_scheduler` · `teardown_scheduler.sh` | — |
| ④ webapi Lambda + web | `src/briefing/webapi/` + `web/` | `-m briefing.webapi.deploy_api` · `deploy_web` · `teardown_webui.sh` | `infra/auth/cognito-users.yaml` |
| ③ DynamoDB 3테이블 | `src/briefing/core/stores/` | `infra/deploy_ddb.sh` | `infra/ddb.yaml` |
컨벤션: 각 어댑터의 배포 스크립트는 `deploy_*.py`/`teardown_*.sh` 파일명 접두어로 그 어댑터 패키지 안에 산다(ops/ 집결은 기각 — install.sh 페이즈에서 재검토).

## 사용자·admin 런북 (Cognito 풀 us-east-1_ANfcEK61A — self-signup 차단)
- 사용자 생성: `aws cognito-idp admin-create-user --user-pool-id us-east-1_ANfcEK61A --username <email>` → 초대 메일(임시 비밀번호) → 첫 로그인 시 hosted UI 가 새 비밀번호 강제
- admin 부여: `aws cognito-idp create-group --group-name admins --user-pool-id us-east-1_ANfcEK61A`(1회) → `aws cognito-idp admin-add-user-to-group --user-pool-id us-east-1_ANfcEK61A --username <sub|email> --group-name admins` → 재로그인(토큰 재발급) 후 적용
- admin 회수: `admin-remove-user-from-group` — 기존 >5 프로필은 발송 유지, 다음 저장부터 5 제한
