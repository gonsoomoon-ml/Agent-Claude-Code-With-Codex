"""Lambda 진입점 — Mangum 이 API Gateway HTTP API(v2) 이벤트를 FastAPI(ASGI)로 변환.

Lambda Web Adapter 대신 Mangum(순수 파이썬) — 기존 zip-번들 배포 패턴에 레이어 없이 맞음.
deploy_api.py Handler = briefing.webapi.lambda_main.handler.
"""
from __future__ import annotations

from mangum import Mangum

from .app import app

handler = Mangum(app, lifespan="off")
