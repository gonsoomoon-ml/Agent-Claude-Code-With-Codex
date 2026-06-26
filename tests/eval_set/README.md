# 적대적 평가셋 (adversarial eval set) — 슬롯

검증 게이트(verify-before-publish)가 *rubber-stamp* 가 아님을 **catch-rate** 로 증명하는 라벨 회귀셋.

- **규모(v1):** ~20–30건. 라벨된 환각 수치·잘못된 귀속·함의 실패 케이스.
- **cross-lingual 포함:** 영어 원문 ↔ 한국어 요약 함의(우리 게이트의 사각 — 측정 대상).
- **지표:** catch-rate = (BLOCK/DEMOTE 되어야 할 것 중 실제로 잡은 비율). 위양성(유령 BLOCK)도 함께.
- **포맷(TODO):** `cases.jsonl` — `{source_excerpt, claim_text, claim_type, gold_verdict, lang}`.

참조: design/prd/prd_news.md §7(성공 기준 #3) · design/research/briefing-news-agent-spec-research.md §6.
