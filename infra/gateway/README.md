# ① Gateway 승격 — 재현 가능한 배포 번들

§79 retrieval 채널(3 도구)을 **AgentCore Gateway** 에 MCP 도구로 승격한다. **off-by-default** —
`GATEWAY_ENABLED=1` 일 때만 fabric 이 Gateway 경유로 fetch. 안 켜면 현 파이프라인 무변경.

**상태: 실 배포·e2e 검증 완료**(us-east-1, 계정 057716757052). Gateway fetch_article 본문이 직접 경로와
**바이트동일**(char-for-char) 함을 기계 증명 — "identical channel".

## 무엇이 올라가나 (3 도구 = retrieval 채널뿐)
| 도구 | 동작 | 비고 |
|---|---|---|
| `fetch_article(source_key, window_hours)` | vetted catalog 출처에서 최근 기사 raw 페치 | fabric 권위 페치 |
| `get_source(source_id)` | content-addressed source-of-record 재열람(read-only) | source_id=sha256 |
| `discover_feed(url)` | 사이트의 RSS/Atom 피드 발견 | 비권위 보조 |

**guardrail(decorrelation 비협상):** gate/verify/certify/author/freeze 는 **절대 미노출**. Lambda
핸들러(`runtime/gateway_handler.py`)는 dispatch 화이트리스트 = 위 3 도구뿐 → certify/produce_card 도달 경로 없음.

## 구성 (aiops `infra/cognito-gateway/` 미러)
| 파일 | 역할 |
|---|---|
| `cognito.yaml` | **CFN** — Cognito(UserPool·Domain·ResourceServer·M2M Client) + IAM(Gateway 역할·Lambda 역할). 선언적·재현. |
| `../../src/briefing/runtime/deploy_gateway.py` | **boto3 오케스트레이터**(멱등) — CFN → zip Lambda(S3) → OAuth2 provider → Gateway+target. |
| `../../src/briefing/runtime/gateway_handler.py` | Lambda MCP dispatcher(기존 함수 호출, 구현 0 변경). |

## Lambda = zip (docker 불필요)
aiops 처럼 **zip Lambda**(python3.12). lxml/trafilatura 는 C 확장이지만 **네이티브 wheel** 로 해결 —
빌드 호스트(이 repo 의 dev 박스)가 Lambda 와 동일 플랫폼(linux x86_64, py3.12)이고 lxml manylinux wheel 의
glibc 요구(≤2.25)가 Lambda AL2023(2.34)에 포함되므로, `uv pip install --target` 결과를 그대로 zip 으로 묶는다.
**docker·CodeBuild 불필요.** boto3 는 Lambda 런타임 기본 제공 → 미번들(19MB zip).

> 빌드 호스트가 linux x86_64 가 아니면(예: macOS/ARM), `--python-platform x86_64-manylinux2014` 교차 타깃이
> 필요하지만 순수-파이썬 sdist(예 `sgmllib3k`)가 cross-build 를 막는다 → 그 경우만 linux x86_64 러너에서 빌드.

## 재현 절차
**전제:** AWS 자격증명 · `uv sync` · DDB 스택(`infra/ddb.yaml`) 배포됨 · region=`us-east-1` · 빌드 호스트=linux x86_64.

```bash
AWS_REGION=us-east-1 DEMO_USER=<id> uv run python -m briefing.runtime.deploy_gateway
```

전부 **멱등** — 재실행 안전(존재 시 재사용/갱신). 끝에 출력되는 키들을 `.env` 에 붙이고 `GATEWAY_ENABLED=1`.
`COGNITO_CLIENT_SECRET` 은 **로컬 전용**(.env, gitignore) — 커밋 금지. Runtime 은 `OAUTH_PROVIDER_NAME`(볼트) 사용.

## 인증 (Cognito CUSTOM_JWT, M2M)
- **Runtime**(클라우드): AgentCore Identity — `get_resource_oauth2_token` 으로 비밀 없이 토큰(볼트의 OAuth2 provider).
- **로컬**(테스트): `.env` 의 client_id/secret 으로 직접 token endpoint 호출(client_credentials).
- Gateway authorizer = `CUSTOM_JWT`(allowedClients=[client_id], scope=`briefing-gw-<id>/invoke`).

## e2e 검증 (실 배포 후)
fabric `gateway_client.fetch_article("openai")` → Gateway 경유 5건 ↔ 직접 경로 5건, **url 교집합 5/5 ·
본문 byte-identical**. = Cognito JWT → Gateway MCP → Lambda dispatch → Lambda 내 trafilatura → MCP 결과 파싱
전 체인 + 채널 동등성 증명. (스크립트 예: `scripts/` 또는 임시 — env 로 GATEWAY_*/COGNITO_* 주입.)
