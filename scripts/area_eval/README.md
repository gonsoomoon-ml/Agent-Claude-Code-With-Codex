# area_eval — 분야(topic) 라벨 품질 평가 (머지 게이트)

스펙 `docs/superpowers/specs/2026-10-24-topic-grouping-design.md` §7. 실 호출은 `main` 에서만(테스트는 fake).

| 파일 | 역할 |
|---|---|
| `golden_7d.json` | 골든셋 138행(고유 132편, 2026-10-17~23 run, 손분류 + 사실층 요약 스냅숏). `area=null` 1건 제외. 라벨 수정은 상한 7장·사유 기록(스펙 §7) |
| `run_golden.py` | 골든셋 × 라벨 호출(LABEL_MODEL_ID) → 정확 일치율(**게이트 ≥85%**)·boundary 분해·안정성·핵심 3 관찰. `--dry-run` = fake. 결과 md+json → `docs/work_note/Oct-2026/261024-Reorder-Content/golden-eval-<ts>.*` |
| `headline_check.py` | AI타임스 라이브 50제목 × 2회 — 미배정 0·일치 ≥90%·손 검토 표 |

```bash
BACKEND=dynamo uv run python scripts/area_eval/run_golden.py --passes 2      # ≈ $0.5
uv run python scripts/area_eval/headline_check.py                             # ≈ $0.02
```
