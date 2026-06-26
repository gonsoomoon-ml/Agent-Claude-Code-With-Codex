"""briefing-agent — 검증 후 발행(verify-before-publish) 데일리 AI 뉴스 브리핑.

직무 분리(separation of duties):
- author (Claude Code, `claude -p`)  : 클러스터링·요약·"What is Important" 작성 (Skill 로 정의). Strands 아님.
- gate   (결정론 코드)        : 오케스트레이터 — 발행 전 certifier 호출 + verdict 적용.
- certifier (Codex)         : 최소 컨텍스트 함의/산술 독립 재도출, BLOCK권만.

핵심 불변식 (설계 = design/architecture/*):
1. 오케스트레이션·비가역 발송 결정은 **gate(결정론 코드)** 가 소유 (author/LLM 아님).
2. **gate 가 certifier 를 호출** (author 아님) — narration 차단을 *토폴로지로* 강제.
3. 권위(authoritative) 페치는 **fabric 소유 + content-addressed(sha256) source-of-record**;
   author 는 동결본 *read* 만, certifier 는 *tool-starved(envelope-fed)*.
4. 개인화(per-user `skill.md`·lens·출처 선택)는 *편집 렌즈*만 — base 계약을 못 바꾸고 certifier 가 미열람.
   trust 경계를 *함수 시그니처*로 강제: `gate.verify_card`·certifier 는 `user` 를 인자로 안 받는다.
"""

__version__ = "0.1.0"
