# 최근 7회 발송 중복 점검 + 재보도 판정자 실험 (2026-11-14)

> 결론과 수정 내용은 `docs/deliveries/2026-10-28-cited-rereport-dedup-delivery.md` §6 에 있다. 이 폴더는 그 근거가 된 도구와 데이터다.
> 모든 도구는 프로덕션 **읽기 전용**(DynamoDB 조회 · CloudWatch 조회 · 기사 페이지 재수집 · Bedrock 판정 호출)이다.

## 무엇을 봤나

- **범위:** run_date 2026-11-07 ~ 11-13(메일은 다음 날 아침), 관리자 129장. 7명이 매일 같은 기사 집합을 받았다.
- **같은 기사 재발송:** 0건(⚠ 카드 포함).
- **같은 발표를 다룬 다른 글이 함께 나간 경우:** 최소 4쌍 + 원 발표 글이 재보도로 빠진 것으로 보이는 1건.

  | # | 받은 글 | 통과한 이유 | 상태 |
  |---|---|---|---|
  | 1 | Anthropic Engineering "The components of agent memory"(11-07) + PyTorch Korea 한국어 소개(11-09) | 판정까지 갔는데 "다름" | **수정함**(전달 기록 §6) |
  | 2 | Claude Blog "Claude for Manufacturing"(11-12) + The Decoder(11-13) | The Decoder 가 기사 대신 제품 페이지를 링크 | 미착수 |
  | 3 | DeepMind "Gemini 4 Carbon is now available" + The Decoder(11-10) | 본문에 원문 링크 없음 | 미착수 |
  | 4 | Claude Fable 5.2·Mythos 5.2 출시: The Decoder(11-10) + PyTorch Korea(11-11) | 원문이 발송된 적 없음 | 미착수 |
  | 5 | Gemini 4 Hydrogen(11-12): Search 글 + The Decoder — DeepMind 원 발표는 재보도로 빠짐 | 원 발표가 Search 글을 링크 · 판정이 갈림 | 미착수 |

  2~5 는 "링크가 없으면 판정하지 않는다"는 설계 범위 밖이거나 제외 방향 문제라 별개다(사용자 결정 대기).

## 도구 (`tools/`) — 저장소 루트에서 `uv run python docs/work_note/Nov-2026/261114-duplicate-articles-7days/tools/<이름>`

| 도구 | 하는 일 | 출력 |
|---|---|---|
| `dup7d.py <출력 폴더>` | 7회 발송: sent-log · 신원 중복 · `pipeline rereport`/`dedup` 로그 · 관리자 카드 덤프 | `dup7d-20261114.txt` · `admin-cards-20261107-1113.tsv` |
| `leak_diag.py <cards.tsv>` | 닮은 쌍마다 B 의 본문 인용 키가 보낸 기사 색인에 걸리는지 | (화면) |
| `hydrogen_diag.py` | Gemini 4 Hydrogen 세 글의 인용 방향 · 원장 · 로그 | (화면) |
| `judge_probe.py` · `final_checks.py` | 링크로 안 걸린 쌍을 판정자에 직접 · 사용자별 발송 집합 비교 | (화면) |
| `pair_reps.py "<A 제목>" "<B 제목>" [N]` | 한 쌍을 N 회 판정 — 값 · 사고 블록 유무 · 응답 원문 | (화면) |
| `scope_1028.py` | 출시(10-28) 이후 운영이 제외한 쌍 전부 + 놓친 두 원문의 발송일 | (화면) |
| `build_pairs.py <pairs.json>` | 실험용 쌍 목록 — 발송된 기사끼리 링크로 걸리는 쌍(10-21~11-13) + 운영이 제외한 쌍, 정답 표시 | `judge-exp-pairs.json` |
| `lengths.py <pairs.json>` | 쌍별 A·B 본문 길이 | (화면) |
| `smoke_effort.py` | Bedrock Converse 가 Haiku 5.5 의 effort 필드를 받는지 | (화면) |
| `run_variants.py <pairs> <결과.jsonl> V0,V1,… [반복]` | 변형별 판정(V0 운영 · V1 이유 먼저 · V2 effort=high · V3 본문 20K · V4 = V1+V3) | `judge-exp-results-*.jsonl` |
| `summarize.py <pairs> <결과.jsonl>` | 변형별 정답률 · 틀린 쌍 · 흔들린 쌍 · 사고 블록 비율 | `judge-exp-summary-*.txt` |
| `e2e_pairs.py <pairs.json>` | 놓친 2쌍 + 경계 2쌍을 운영 경로(`make_bedrock_rereport`)로 3회씩 | (화면) |
| `gate_1025_diag.py` | 게이트 10-25 쌍이 왜 사라졌나(The Decoder 기사 수정) | (화면) |
| `run_gate.sh <출력> [기대 제외 수]` | 재생 게이트 실행 | `gate-20261114-*.txt` |

## 데이터

- `judge-exp-pairs.json` — 49쌍: 정답 붙인 47쌍(게이트 주간 12 · 출시 뒤 발송된 쌍 17 · 운영이 제외한 쌍 18) + 경계 2쌍(`expect: null`). **정답은 본문과 판정 이유를 읽고 붙인 것**이다(`build_pairs.py` 의 `GATE_KEEP`·`MISS`·`SKIP`).
- `judge-exp-results-r1.jsonl`(5변형 × 2회, 놓친 쌍은 5회) · `judge-exp-results-r2-reason-first.jsonl`(채택안 3회 추가) — 응답 원문 포함.
- `replay-20261028-1106.txt` · `replay-20261107-1113.txt` — 옛 프롬프트로 돌린 `rereport_replay.py` 출력(발송된 쌍의 판정 이유).
- `gate-20261114-expect10-FAIL.txt` · `gate-20261114-expect9-PASS.txt` — 새 프롬프트 게이트 2회(판정 12 · 제외 9 · 유지 3).

## 다시 돌릴 때 주의

- 기사 페이지를 매번 다시 받으므로 **쌍 수는 날짜에 따라 달라진다**(게이트 13 → 12 가 그 예). 판정자도 호출마다 답이 조금 다르다.
- 옛 프롬프트(값 먼저)의 수치를 재현하려면 `run_variants.py` 의 V0 를 쓴다 — 두 끝줄을 스크립트가 직접 들고 있어 수정 전·후 어느 체크아웃에서도 같은 프롬프트다. `pair_reps.py`·`e2e_pairs.py`·`run_gate.sh` 는 현재 체크아웃의 프롬프트를 쓴다.
