"""webapi — ④ Web UI 의 public API(FastAPI on Lambda). v1.0 = GET /catalog · GET /sample(무지출).

scheduler/ 와 동형(서브패키지). briefing.shared(sources·lenses) 재사용 — 카탈로그 단일 소유.
배포: deploy_api.py(Lambda+HTTP API) · deploy_web.py(S3+CloudFront).
"""
