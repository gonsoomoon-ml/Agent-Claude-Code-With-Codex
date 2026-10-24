# 구현 메모 — 주제 밴드(topic-grouping) (2026-10-24)

계획: `docs/superpowers/plans/2026-10-24-topic-grouping.md` · 스펙: `docs/superpowers/specs/2026-10-24-topic-grouping-design.md`

## Task 6 스모크 — Sonnet 5.5 Converse 파라미터 (확인 먼저)
- 등록 프로필(us-east-1 `list-inference-profiles`): `us.anthropic.claude-sonnet-5-5`, `global.anthropic.claude-sonnet-5-5` → `.env` 는 global.
- 후보 A `additionalModelRequestFields={"thinking": {"type": "between_tools"}}`, `maxTokens=6000`(`LABEL_MAX_TOKENS`) → **통과**: 텍스트 블록 `"OK"` 수신, ValidationException 없음. 후보 B(adaptive 기본 + effort)는 시도하지 않음.
- 관련성·선별·헤드라인 선별 헬퍼(`_converse_text`, `thinking: disabled`)는 바이트 동일 유지(테스트 `test_relevance_helper_still_sends_thinking_disabled`).
