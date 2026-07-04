# runtime — AgentCore 어댑터 (컨테이너로 배포)
`agentcore_runtime.py` = 엔트리포인트(컨테이너 CMD `-m briefing.runtime.agentcore_runtime`). `supervisor.py` = Strands supervisor 옵션 · `_trial.py` = trial 모드 · `_smoke.py` = 스모크.
`deploy_runtime.py`(배포: 스테이징→CodeBuild→launch) · `invoke_runtime.py`(호출 검증) · `teardown.sh`.
`container/` = 이미지 빌드 자산 4종(Dockerfile·requirements.txt·claude_config.json·codex_config.toml) — deploy_runtime 이 빌드 컨텍스트 루트로 복사. 4종은 한 세트: 일부만 옮기면 스테이징 crash.
⚠️ scheduled/trial 분기의 import 는 lazy — 스모크가 통과해도 발송 경로는 `mode=scheduled` dry_run 으로 따로 증명해야 한다.
