# webapi — ④ Web UI 백엔드 어댑터 (Lambda + CloudFront 프론트는 web/)
`app.py`(FastAPI; `sample_briefing.html` 은 import-time 로드라 같은 디렉토리 필수) · `catalog.py`(공개 카탈로그 — core lenses/sources 소비) · `profile.py` · `trial.py`(체험 가드) · `lambda_main.py`(Handler=`briefing.webapi.lambda_main.handler`) · `run.py`(로컬 uvicorn).
`deploy_api.py`·`deploy_web.py`·`teardown_webui.sh` = 배포/철거.
⚠️ `/profile` 의존성은 함수 안 lazy import — 배포 후 curl 로만 실증 가능.
