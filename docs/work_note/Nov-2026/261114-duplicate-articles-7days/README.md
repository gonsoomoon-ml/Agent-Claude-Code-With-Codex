# 최근 7회 발송 중복 점검 + 재보도 판정자 실험 + 같은 사이트 쌍 측정 (2026-11-14)

> 결론과 수정 내용은 `docs/deliveries/2026-10-28-cited-rereport-dedup-delivery.md` §6(판정 답 순서) · §7(같은 사이트의 다른 페이지를 링크한 재보도)에 있다. 이 폴더는 그 근거가 된 도구와 데이터다.
> 모든 도구는 프로덕션 **읽기 전용**(DynamoDB 조회 · CloudWatch 조회 · 기사 페이지 재수집 · Bedrock 판정 호출)이다.

## 무엇을 봤나

- **범위:** run_date 2026-11-07 ~ 11-13(메일은 다음 날 아침), 관리자 129장. 7명이 매일 같은 기사 집합을 받았다.
- **같은 기사 재발송:** 0건(⚠ 카드 포함).
- **같은 발표를 다룬 다른 글이 함께 나간 경우:** 최소 4쌍 + 원 발표 글이 재보도로 빠진 것으로 보이는 1건.

  | # | 받은 글 | 통과한 이유 | 상태 |
  |---|---|---|---|
  | 1 | Anthropic Engineering "The components of agent memory"(11-07) + PyTorch Korea 한국어 소개(11-09) | 판정까지 갔는데 "다름" | **수정함**(전달 기록 §6) |
  | 2 | Claude Blog "Claude for Manufacturing"(11-12) + The Decoder(11-13) | The Decoder 가 기사 대신 제품 페이지를 링크 | **수정함**(전달 기록 §7) |
  | 3 | DeepMind "Gemini 4 Carbon is now available" + The Decoder(11-10) | 원문 주소 대신 같은 사이트의 프로그램 페이지를 링크 — 2번과 같은 문제 | **수정함**(전달 기록 §7) |
  | 4 | Claude Fable 5.2·Mythos 5.2 출시: The Decoder(11-10) + PyTorch Korea(11-11) | 원문이 발송된 적 없음 | 미착수 |
  | 5 | Gemini 4 Hydrogen(11-12): Search 글 + The Decoder — DeepMind 원 발표는 재보도로 빠짐 | 원 발표가 Search 글을 링크 · 판정이 갈림 | 미착수 — §7 뒤에는 The Decoder 기사도 Search 글의 재보도로 빠져 Search 글만 남는다 |
  | 6 | The Decoder "Mistral releases "Le Chonk""(10-29) ← Hugging Face "Welcome Le Chonk" | 판정자는 "같은 발표"라고 답하지만 이유 문장의 큰따옴표로 응답 JSON 이 깨져 판정 실패 → 통과 | 미착수 — 2번을 측정하다 발견(7회 점검 범위 밖) |

  2·3 은 범위를 17회 발송(10-28~11-13)으로 넓혀 다시 쟀다: 놓친 중복 7쌍(아래 「같은 사이트 쌍 측정」). 4~6 은 사용자 결정 대기다.

## 같은 사이트 쌍 측정 (문제 2·3)

- **무엇을 쟀나:** 발송된 기사 B 가, 최근 7일 안에 보냈거나 같은 날 보낸 기사 A 와 **같은 사이트의 다른 페이지**를 링크한 쌍. 관리자 발송 17회(run_date 10-28~11-13), 쌍마다 판정 2회.
- **결과:** 후보 627쌍 중 2회 모두 "같은 발표" 10쌍 · 갈림 0 · 다름 616 · 2회 모두 판정 실패 1.
  - 10쌍은 전부 B 가 The Decoder(6) 또는 PyTorch Korea(4)다. B 가 그 밖 매체인 256쌍에서는 0쌍.
  - 10쌍 중 3쌍은 원문 주소도 정확히 링크한다(§6 에서 고친 한국어 소개 글) → 새로 잡는 것은 7쌍.
- **결정:** B 가 News & Media·Community 매체 글일 때만 같은 사이트 쌍을 판정한다(사용자 결정 2026-11-14, 전달 기록 §7).
- **구현 뒤 재생:** 17회 → 제외 10건이 측정의 10건과 일치하고 측정 후보 밖 판정이 0 이다(`same-site-diff-20261028-1113.txt`). 게이트 주간(10-21~10-27) → 제외 10 = 기존 9 + 10-25 The Decoder 기사 1건.

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
| `run_gate.sh <출력> [기대 제외 수=10] [추가 인자…]` | 재생 게이트 실행. 정확히 링크한 쌍만 보려면 `<출력> 9 --exact-only` | `gate-2026111*-*.txt` |
| `same_site_measure.py <출력.json>` | 같은 사이트 후보 쌍을 모아 쌍마다 2회 판정(17회 발송) | `same-site-measure.json` · `same-site-measure.txt` |
| `same_site_analyze.py <measure.json>` | 후보 쌍을 B 매체 분야·날짜 차·호스트별로 나눠 수와 "같은 발표" 수(Bedrock 호출 없음) | `same-site-analyze.txt` |
| `same_site_replay.sh <저장소 루트> <since> <until> <출력 접두사> [추가 인자…]` | 구현한 코드로 재생하고 판정한 쌍 전부를 JSON 으로 | `same-site-replay-*.txt` · `.json` |
| `same_site_diff.py <replay.json> <measure.json>` | 재생 결과를 측정과 기계적으로 대조 — 제외 집합 일치 · 측정 후보 밖 판정 · 다른 판정(Bedrock 호출 없음) | `same-site-diff-20261028-1113.txt` |
| `same_site_mutate.py <저장소 루트>` | 같은 사이트 규칙의 가드 7개를 하나씩 지워 테스트가 잡는지 확인(소스를 잠깐 고치고 되돌린다) | (화면) |
| `judge_raw_probe.py <replay.json> <B 제목 조각> [N]` | 판정이 실패한 쌍을 N 회 다시 물어 응답 원문과 파서가 읽는지 | `judge-raw-probe-lechonk.txt` |
| `judge_fail_scan.py <이 폴더>` | 판정 실패 빈도 — 저장된 판정 결과 + 운영 로그(10-28 이후) | `judge-fail-scan-20261115.txt` |

## 데이터

- `judge-exp-pairs.json` — 49쌍: 정답 붙인 47쌍(게이트 주간 12 · 출시 뒤 발송된 쌍 17 · 운영이 제외한 쌍 18) + 경계 2쌍(`expect: null`). **정답은 본문과 판정 이유를 읽고 붙인 것**이다(`build_pairs.py` 의 `GATE_KEEP`·`MISS`·`SKIP`).
- `judge-exp-results-r1.jsonl`(5변형 × 2회, 놓친 쌍은 5회) · `judge-exp-results-r2-reason-first.jsonl`(채택안 3회 추가) — 응답 원문 포함.
- `replay-20261028-1106.txt` · `replay-20261107-1113.txt` — 옛 프롬프트로 돌린 `rereport_replay.py` 출력(발송된 쌍의 판정 이유).
- `gate-20261114-expect10-FAIL.txt` · `gate-20261114-expect9-PASS.txt` — 새 프롬프트 게이트 2회(판정 12 · 제외 9 · 유지 3). ★ 같은 사이트 판정을 넣기 **전** 코드다 — `expect10-FAIL` 은 옛 기대값 10 으로 돌려 9 가 나온 기록이고, 지금 기본 실행의 10 과는 다른 이야기다.
- `gate-20261115-same-site-expect10-PASS.txt` · `gate-20261115-exact-only-expect9-PASS.txt` — 같은 사이트 판정을 넣은 뒤 게이트(2026-11-15): 기본 실행 판정 222 · 제외 10, `--exact-only` 판정 12 · 제외 9.
- `same-site-measure.json`(627쌍 — A·B·B 가 건 링크·판정 2회·이유) · `same-site-measure.txt`(그때 화면 출력) · `same-site-analyze.txt`(분야·날짜 차·호스트별 집계).
  - ★ `same-site-measure.txt` 끝줄의 "2회 모두 다름 617"은 **다름 616 + 2회 모두 판정 실패 1** 이다. 그때 집계가 판정 실패를 "다름"에 섞어 셌다(도구는 고쳤다). 정확한 수는 `same-site-analyze.txt`.
- `same-site-replay-20261028-1113.txt` · `.json`(17회: 판정 323 · 제외 10) · `same-site-replay-20261021-1027.txt` · `.json`(게이트 주간: 판정 222 · 제외 10) · `same-site-diff-20261028-1113.txt`(17회 재생과 측정의 대조).
  - ★ `same-site-replay-20261028-1113.txt` 끝의 `FAIL` · `exit=1` 은 판정 결과와 무관하다. 그때 스크립트가 그 기간에 없는 두 제목(게이트 주간의 유지 확인용)을 기간과 상관없이 걸어서 "유지 확인 불가"가 찍혔다(스크립트는 고쳤다).
- `judge-raw-probe-lechonk.txt`(판정이 실패하는 쌍의 응답 원문 6회 — 전부 `"same": true` 인데 파서가 못 읽음) · `judge-fail-scan-20261115.txt`(저장된 판정 1,799회 중 실패 3회 = 그 한 쌍 · 운영 로그의 `판정 실패` 줄 0건).

## 다시 돌릴 때 주의

- 기사 페이지를 매번 다시 받으므로 **쌍 수는 날짜에 따라 달라진다**(게이트 13 → 12 가 그 예). 판정자도 호출마다 답이 조금 다르다.
- `same_site_measure.py` 는 `first_run`(그 기사를 처음 보낸 날)으로 최근 7일을 가리고, 운영 코드(`published_keys(recent_hosts=)`)는 색인에 남은 가장 최근 발송일로 가린다. 17회 재생에서는 두 방식의 후보가 어긋나지 않았다(측정 후보 밖 판정 0).
- 옛 프롬프트(값 먼저)의 수치를 재현하려면 `run_variants.py` 의 V0 를 쓴다 — 두 끝줄을 스크립트가 직접 들고 있어 수정 전·후 어느 체크아웃에서도 같은 프롬프트다. `pair_reps.py`·`e2e_pairs.py`·`run_gate.sh` 는 현재 체크아웃의 프롬프트를 쓴다.
