"""AgentCore Runtime entrypoint — shared/ 의 동일 코드를 Runtime 으로 감쌈.

shared(진실)=로직, 이 파일=배포 하니스. BedrockAgentCoreApp + @app.entrypoint.
호출 경로(U2): EventBridge Scheduler → Lambda(async) → invoke_agent_runtime.
컨테이너 계약: /invocations POST + /ping GET on :8080 (ARM64, toolkit/CodeBuild 빌드).
"""
from __future__ import annotations

# TODO(U1): 의존성(bedrock-agentcore) 설치·컨테이너 검증 후 활성화.
# from bedrock_agentcore import BedrockAgentCoreApp
# app = BedrockAgentCoreApp()


# @app.entrypoint
async def briefing_entrypoint(payload, context):
    """매일 1회 호출: 전체 파이프라인(fetch→freeze→author→gate→certifier→render→SES).

    TODO: shared 파이프라인 호출 + 진행 SSE yield. U1(컨테이너 CLI)·U2(스케줄) PoC 후 구현.
    """
    raise NotImplementedError("AgentCore entrypoint — U1/U2 PoC 후 구현")
