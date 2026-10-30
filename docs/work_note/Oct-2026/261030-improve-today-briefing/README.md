# 261030 — 오늘 브리핑 리뷰 → 문제 목록 → 하나씩 결정

2026-10-30 아침(10-29 run, 7명 sent·24장·격리 0·$1.98·13분) 리뷰에서 문제 9건을 뽑고 하나씩 토론·승인·구현한다.
**배포는 목록을 다 처리한 뒤 한 번에**(사용자 결정 10-30). 브랜치 `worktree-offsite-warn-only`.

## 문제 목록 · 상태

| # | 문제 | 상태 |
|---|---|---|
| 1 | Meta 미러 글(canonical 교차)이 수집층 offsite 차단에 걸림 | **구현** `2b28b1a` — 경고만 통과. ★처음 "큰 발표 4일 누락"으로 오진 → 두 글은 2026-04-08·07-05 옛 고정 글, 48h 창에서 어차피 걸러짐 = 피해 없음, 미래 방어로 유지 |
| 2 | 핵심 3 "큰 발표" 칸을 how-to·기능 글이 차지(10일 중 ≈1/4) | **구현** `56f1286` — `launch` 정의 좁힘. 측정 아래. ★구현은 측정 승인만 받은 상태에서 진행했다가 사용자 지적 — 유지/되돌림 결정 대기 |
| 2b | 응용 칸(p2)을 Inference & Hardware how-to 가 차지(10-29 Nemotron on EKS) — 사용자 관심 = AI Agents·Applied AI·5대 기업 큰 발표 | **구현(승인 "apply and test first")** — `tier()` 2티어에 분야 조건(`APPLIED_AREAS`). 시뮬(10일, 변경안 라벨) 1일 변화: 10-29 p2 Nemotron → Nova Act |
| 3 | 분야 오분류(Lambda Web Functions 1부 → Models & Releases, ProtoStar → Applied AI) | 대기 |
| 4 | AI Agents 밴드 7장 중 4장이 PyTorch KR 커뮤니티 스킬 글 | 대기 |
| 5 | 요약의 수식어 탈락 2건(over 800,000 → 800,000) | 대기 |
| 6 | 해석층 lint 폴백 2건(미검증 수치) | 대기(정상 동작) |
| 7 | 목록에 날짜 없는 소스는 매일 같은 옛 글을 다시 열고 페이지 날짜로 버림(낭비) | 대기 |
| 8 | `fetch stub` 노이즈(anthropic Product/Security·pytorch-kr 카테고리) | 대기 |
| 9 | 요약 고유명사가 claims 에 없음 4건 | 대기(낮음) |
| + | ai.meta.com 페이지 trafilatura 날짜 추출 오류(Muse Image/Video → 2022-11-18) | 새 항목(1번에서 발견) |

## #2 측정 — 핵심 3 라벨 재생(2026-10-20~29, Sonnet 5.5 `LABEL_MODEL_ID`, 운영 경로 `make_bedrock_labels`)

방법: 사용자 ledger 의 날짜별 카드(PUBLISH+⚠) → card-cache 사실층 카드(제목·요약). ★해석층 폴백 카드는 interp 키로 캐시되지
않는데 ledger 는 그 키를 적어 두므로 `fact_card_key(source_id, 요약 모델, 지시 버전)` 로 재탐색(10-25 v62 전 모델 = Sonnet 5).
카드 순서 = 카탈로그 순(파이프라인 근사). 비용 ≈ 호출 51회(1차 27 · 2차 17 · 기준선 7).

| 레버 | 결과 | 판정 |
|---|---|---|
| 1티어 importance 하한 3 | 거의 무변화(후보 대부분 3~4) | 무용 |
| 하한 4 | Polly 3·AI for Science 3 탈락, 오분류 4점(TorchTPU·OpenAI 연구 보도)은 통과, 주말 핵심 3 생략(10-25) | 기각 |
| `launch` 좁히기 | 1티어 후보 58→33장(−43%), 플래그십 전부 유지, 10-29 = AI for Science + 응용 2장 | **채택** |
| "연구 결과→other" | 10-24 는 그대로 policy, 응용 칸 연구 픽(10-27·28) 밀어냄 | 기각 |
| importance 앵커 | Terra 5→4 등 점수 불안정 | 보류 |

분야 골든 게이트(132편, ≥85%): 현 프롬프트 89.3%(같은 날) vs 좁힌 87.8% — 2장 차이, 불일치 12건 공유 → 잡음.
잔존: 10-24 OpenAI 연구 보도가 policy/4(1건/10일, 수용) · 10-26 IAM Helper 가 launch/3(기능 글 1건 잔존).
주의: 같은 현 프롬프트도 운영과 재생 픽이 5일 달랐다 — 라벨 LLM 의 run 간 변동이 크므로 단건 뒤집힘은 결론에 넣지 않는다.

## 파일

- `toppicks-compare-per-day.md` — 날짜별 핵심 3: 운영 · 현 프롬프트 재생 · 좁힌 프롬프트 재생
- `toppicks-replay-1-current-vs-candidate.{md,json}` — 1차(현 vs 후보[좁힘+연구→other+앵커]) × 하한 0/3/4
- `toppicks-replay-2-refined.{md,json}` — 2차(좁힘만) × 하한 0/3/4 + 골든 게이트
- `refined_prompt.txt` — 채택 프롬프트 전문 · `golden-current-20261030.json` — 같은 날 기준선
- `tools/` — 재생·비교·기준선 스크립트(scratchpad 사본; 저장소 도구 승격은 별도 판단)
