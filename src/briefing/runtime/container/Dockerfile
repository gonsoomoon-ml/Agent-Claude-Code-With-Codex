# ②b Runtime 컨테이너 — Python(uv) + Node + headless 듀얼 하니스(author=claude, certifier=codex).
#
# ★ toolkit 동작: 빌드 dir 에 Dockerfile 이 *이미 있으면* 생성 대신 이걸 사용(container.py "Using existing Dockerfile").
#   빌드 컨텍스트 = deploy_runtime.stage_build_context() 가 만든 .agentcore_build/ —
#   {briefing/ 패키지, requirements.txt, codex_config.toml, claude_config.json, Dockerfile(이 파일)}
#   ★ 이 파일과 4종 자산의 출처: src/briefing/runtime/container/
# ★ 비밀값 0: claude(CLAUDE_CODE_USE_BEDROCK=1) · codex(config.toml model_provider=amazon-bedrock) 둘 다
#   **Bedrock SigV4 = execution role** 로 인증 → Anthropic/OpenAI API 키 안 구움.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim
WORKDIR /app
ENV UV_SYSTEM_PYTHON=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_NO_PROGRESS=1 \
    PYTHONUNBUFFERED=1 \
    DOCKER_CONTAINER=1

# ── Node.js (codex + claude code 둘 다 npm 글로벌) ──
# (codex 샌드박스=bubblewrap 은 컨테이너 microVM 에서 userns 가 활성이라 bundled bwrap 으로 정상 동작 —
#  별도 설치 불필요. 진단으로 확인: max_user_namespaces>0, unshare/bwrap rc=0.)
# ★ 공식 tarball 로 설치한다(NodeSource setup 스크립트 아님) — 2026-07-27 부터 deb.nodesource.com 이
#   403 을 반환해 빌드가 깨졌다. 게다가 `curl … | bash -` 는 **파이프라인 종료 상태가 bash 것**이라
#   curl 이 403 으로 죽어도 빌드가 계속됐고, 8단계 뒤 `npm: command not found`(exit 127)라는 엉뚱한
#   증상으로 나타났다 — 침묵 실패. tarball 은 `-o` 로 받아 curl 실패가 그 자리에서 빌드를 세운다.
ARG NODE_VERSION=v22.23.1
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates xz-utils \
 && rm -rf /var/lib/apt/lists/* \
 && arch="$(dpkg --print-architecture)" \
 && case "$arch" in arm64) narch=arm64 ;; amd64) narch=x64 ;; *) echo "unsupported arch: $arch" >&2; exit 1 ;; esac \
 && curl -fsSL -o /tmp/node.tar.xz "https://nodejs.org/dist/${NODE_VERSION}/node-${NODE_VERSION}-linux-${narch}.tar.xz" \
 && tar -xJf /tmp/node.tar.xz -C /usr/local --strip-components=1 \
 && rm /tmp/node.tar.xz \
 && node --version && npm --version

# ── 듀얼 하니스: author=claude(@anthropic-ai/claude-code) · certifier=codex(@openai/codex) ──
# ★ 버전 pin = 호스트의 *검증된* 버전과 일치(재현성 + codex 0.142.3 regression 회피):
#   codex 0.142.3 의 `exec` 는 stdin 처리가 바뀌어 "Reading additional input from stdin"(rc=1)로 실패 →
#   호스트가 e2e 검증한 0.142.2 로 고정. claude 도 호스트 버전 고정.
RUN npm install -g @anthropic-ai/claude-code@2.1.195 @openai/codex@0.142.2

# ── Python 의존성 (컨테이너 최소 목록 + OTEL) ──
COPY requirements.txt requirements.txt
RUN uv pip install -r requirements.txt && uv pip install aws-opentelemetry-distro==0.12.2

# ── 비-root 유저 + 하니스 설정 굽기(비밀 아님: 둘 다 Bedrock SigV4) ──
RUN useradd -m -u 1000 bedrock_agentcore
COPY codex_config.toml  /home/bedrock_agentcore/.codex/config.toml
COPY claude_config.json /home/bedrock_agentcore/.claude.json
RUN chown -R bedrock_agentcore:bedrock_agentcore /home/bedrock_agentcore
USER bedrock_agentcore
ENV HOME=/home/bedrock_agentcore

EXPOSE 8080
# 빌드 컨텍스트 전체 복사(.dockerignore 존중) → /app/briefing/... → `-m briefing.runtime.agentcore_runtime`
COPY . .
CMD ["opentelemetry-instrument", "python", "-m", "briefing.runtime.agentcore_runtime"]
