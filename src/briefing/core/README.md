# core — 도메인 전부 (구 shared/)
파이프라인의 진실이 사는 곳. 루트 = 척추: `pipeline.py`(fetch→curate→author→gate→render 조립) · `gate.py`(verify-before-publish 게이트, maker-checker 루프) · `config.py` · `render.py`(이메일 HTML) · `lenses.py`+`lenses.yaml`(관점 — webapi 카탈로그도 소비).
하위: `retrieval/`(증거 수집 + catalog.yaml) · `authoring/`(author.py = `claude -p` 작성자) · `verification/`(certifier.py = `codex exec` 검증자) · `stores/`(ledger·cache·source_store, backends.py 가 로컬/DDB seam) · `prompts/`(template.py 와 .md 는 같은 디렉토리 필수 — 로더가 자기 폴더에서만 읽음).
⚠️ authoring/verification 폴더 분리는 **가독성**이다 — decorrelation 의 실제 메커니즘은 gate 가 만드는 4필드 Envelope 화이트리스트 + certifier 의 clean-dir subprocess. lenses.yaml·catalog.yaml 은 import-time 로드: .py 와 분리하면 기동 crash.
새 기능: 관점 추가=`lenses.yaml` 한 항목 · 미디어 추가=`retrieval/catalog.yaml` 한 항목 · 저장 교체=`stores/backends.py`.
