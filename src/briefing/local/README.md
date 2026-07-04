# local — AWS-free 베이스라인
`run.py`: fake DI(author/certifier 스텁)로 전체 파이프라인을 로컬에서 완주 — `uv run python -m briefing.local.run`.
리팩토링·의존성 변경 후 첫 번째 검증 관문(카탈로그/lens yaml 동거, import 정합을 실행으로 증명).
