"""FastAPI 앱 — ④ Web UI public API. v1.0: GET /catalog·/sample·/health(무지출).

CORS 는 앱 레벨(CORSMiddleware) — 배포(Mangum→HTTP API)·로컬(uvicorn) 공통 + preflight 처리.
v1.0 allow_origins=* (public GET); v1.1+ env WEB_ORIGIN 로 CloudFront 도메인 좁힘.
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware

from .catalog import build_catalog

_SAMPLE_HTML = (Path(__file__).parent / "sample_briefing.html").read_text(encoding="utf-8")

app = FastAPI(title="Briefing Web API", version="1.0.0")

_origins = [o.strip() for o in os.getenv("WEB_ORIGIN", "*").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins or ["*"],
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["*"],
)


@app.get("/catalog")
def get_catalog() -> dict:
    """폼용 카탈로그(출처 그룹·시각·상한). 무지출 — CATALOG/LENS_LIBRARY 메모리 읽기."""
    return build_catalog()


@app.get("/sample")
def get_sample() -> Response:
    """랜딩 미리보기용 정적 샘플 브리핑 HTML."""
    return Response(content=_SAMPLE_HTML, media_type="text/html; charset=utf-8")


@app.get("/health")
def health() -> dict:
    return {"ok": True}
