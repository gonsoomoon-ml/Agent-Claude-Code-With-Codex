# tools/ — 주간 도구(읽기 전용 입력)

- 주간 카드 추출: `briefing-ledger`(run_date 토~금) → `briefing-card-cache` → `briefing-source-store`. 읽기 전용 boto3 스크립트.
- 저장소 링크 확인: 리다이렉트 해소 → 최근 push → README/경로 확인(`../README.md` §7).
- 발송: SES, 표시 이름 `Field Experiment`, 제목 `[현장 실험] …`.
- **기사 lint: `lint_issue.py`** — 발송 전 결정론 검사(`../README.md` §4 · §6 · §7 중 기계로 잴 수 있는 것). FAIL 이면 보내지 않는다. 실행 `uv run --no-project python tools/lint_issue.py issues/YYYY-MM-DD.md`.

lint 외에는 아직 미작성. 스크립트는 저장소 CLAUDE.md 의 AWS 접근 방식(boto3 파일 · `uv run python`)을 따른다.
