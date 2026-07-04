# infra — 배포 단위 인덱스 (CFN + 셸 배포자)
| 배포 단위 | 코드 | 배포/철거 | CFN |
|---|---|---|---|
| ② AgentCore 컨테이너 | `src/briefing/runtime/` | `uv run python -m briefing.runtime.deploy_runtime` · `runtime/teardown.sh` | (toolkit 관리) |
| ① Gateway Lambda | `src/briefing/gateway/` | `uv run python -m briefing.gateway.deploy_gateway` | `infra/gateway/cognito.yaml` |
| ⑤ scheduler Lambda | `src/briefing/scheduler/` | `-m briefing.scheduler.deploy_scheduler` · `teardown_scheduler.sh` | — |
| ④ webapi Lambda + web | `src/briefing/webapi/` + `web/` | `-m briefing.webapi.deploy_api` · `deploy_web` · `teardown_webui.sh` | `infra/auth/cognito-users.yaml` |
| ③ DynamoDB 3테이블 | `src/briefing/core/stores/` | `infra/deploy_ddb.sh` | `infra/ddb.yaml` |
컨벤션: 각 어댑터의 배포 스크립트는 `deploy_*.py`/`teardown_*.sh` 파일명 접두어로 그 어댑터 패키지 안에 산다(ops/ 집결은 기각 — install.sh 페이즈에서 재검토).
