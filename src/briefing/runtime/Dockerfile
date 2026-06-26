# AgentCore Runtime 컨테이너. 스캐폴드 stub — 빌드 컨텍스트·경로는 U1 에서 확정.
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

WORKDIR /app
RUN useradd -m app

# 컨테이너는 uv.lock 대신 최소 requirements.txt 사용
COPY src/briefing/runtime/requirements.txt .
RUN uv pip install --system -r requirements.txt

# shared(진실) + runtime entrypoint 복사 — TODO(U1): 패키지 경로/엔트리 확정
COPY src/briefing /app/briefing

USER app
# /invocations POST + /ping GET on :8080 (AgentCore 계약), OTEL 계측
CMD ["opentelemetry-instrument", "python", "-m", "briefing.runtime.agentcore_runtime"]
