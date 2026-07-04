# gateway — ① AgentCore Gateway 어댑터 (독립 Lambda 배포 단위)
`gateway_handler.py` = retrieval 3도구(fetch_article·get_source·discover_feed) Lambda(.gw_build.zip). `deploy_gateway.py` = 멱등 배포(CFN Cognito→zip→provider→Gateway).
기본 off — `GATEWAY_ENABLED=1` 일 때만 fabric 이 경유. guardrail(비협상): 노출 도구는 retrieval 3개뿐(gate/certify/author 미노출 — decorrelation).
zip 은 briefing 패키지 전체를 담는다(handler 가 core config/retrieval/stores 를 import-time 로드) — 슬림화 금지. 재현 번들·검증: `infra/gateway/` + `scripts/e2e_gateway.py`.
