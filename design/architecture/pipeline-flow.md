# 파이프라인 흐름 — verify-before-publish (어떻게 한 카드가 만들어지나)

> **이 문서 = 런타임 흐름의 *정본 그림*(빠른 참조용).** 왜 이렇게 설계했는지의 근거·소스 검증은 [`four-component-analysis.md §5.5`](./four-component-analysis.md) 참조.

## 한 줄 요약 (TL;DR)

fabric 가 출처를 동결(sha256) → **gate** 가 Claude author 로 초안 작성 → gate 가 **4필드 envelope** 작성(= decorrelation 경계) → Codex certifier 가 **독립 검증** → gate 가 결정론 **AND-게이트**로 `PUBLISH` / `QUARANTINE` 결정. 비가역 발행 결정은 *언제나 코드*(LLM 아님)가 소유한다.

## (a) 흐름 (dynamic) — 단계 순서

세로로 읽는다. `[n]` = 단계, 가운데 `│` = 소유자가 하는 일, `└` = 그 단계의 **신뢰 속성**. 굵은 `═══` 줄이 **decorrelation 경계** — 그 위로는 author 의 최종 답변, 그 아래로는 4필드 envelope 만 흐른다.

```
[1] fabric/Graph │ collect · cluster · rank · 기사별 fan-out
                 └ 생성 층 — Graph 가 적합 (병렬 · 관측 · retry)
      │
[2] fabric       │ freeze source → sha256 → ledger
                 └ 권위 페치 = fabric 소유 (author 가 증거 자체를 통제 못함)
      │
[3] gate         │ draft_fn ─▶ Claude author   (claude -p, Bedrock)
[4] Claude       │ 초안 + atomic claims 반환    (gate 로 가는 건 최종 답변만)
      │
═════ decorrelation 경계 — gate 가 envelope 를 손으로 작성 ═════
[5] gate         │ envelope = 정확히 4필드
                 │   { source_excerpt, claim_text, claim_type, schema }
                 └ narration / reasoning / confidence = 필드 자체 부재
      │  envelope 만 건너감
[6] gate         │ verify_fn ─▶ Codex certifier (codex exec, Bedrock)
[7] Codex        │ claim별 독립 재도출 → verdict (cross-family · CoT 안봄)
      │
[8] gate         │ 실패 claim 있으면 → revise_fn(실패분만) ↺ [3]–[7]
                 └ Maker-Checker, cap 2회 (Graph 도 가능하나 코드가 단순·감사)
      │
[9] gate         │ verdict 적용: VERIFIED / DEMOTED / BLOCKED
      │
[10] gate        │ AND-gate 결정 (코드, LLM 아님) ── 비가역 = 결정론 · 감사
                 ├─ 전부 통과 ─▶ PUBLISH ─▶ SES → 이메일 (07:00 KST)
                 └─ 소진/불일치 ─▶ QUARANTINE ─▶ 사람 검토 큐
```

## (b) 아키텍처 (static) — 층 · 소유 · 신뢰 경계

위→아래 = 호스트 → 큐레이션 → 저장 → gate → 두 하니스. 가운데 점선 `┊` 이 두 CLI 를 가르는 **decorrelation 경계**. 맨 아래 `※` = certifier 를 Graph node 로 두지 않는 이유.

```
┌─ AgentCore Runtime ── 관리형 호스트 (컨테이너 · egress · 07:00 KST 트리거)
│
│  ◆ Strands curation fabric ── [생성/평가 층 — Graph 가 빛나는 곳]
│      Graph: collect → scrape → thread-cluster → rank → 기사별 fan-out
│      (조건 edge · bounded loop · 병렬 · 중첩 = 모두 native)
│          │ frozen + sha256
│          ▼
│  ◆ source_store ── content-addressed source-of-record + durable ledger
│          │ 동결본 read
│          ▼
│  ◆ gate (plain Python) ── [신뢰 경계 · 비가역 결정 소유 · 오케스트레이터]
│      produce_card:  draft → envelope(4f) → verify → verdict → decide
│          │ draft_fn/revise_fn                    │ verify_fn
│          │ (build_system_prompt 만)               │ (4필드 envelope 만)
│          ▼                                        ▼
│      ╔═ Claude author ════╗   ┊   ╔═ Codex certifier ═══╗
│      ║ claude -p, Bedrock ║   ┊   ║ codex exec, Bedrock ║
│      ║ Sonnet 4.6         ║   ┊   ║ gpt-5.5             ║
│      ║ clean dir          ║   ┊   ║ clean dir           ║
│      ╚════════════════════╝   ┊   ╚═════════════════════╝
│        author ≠ certifier     ┊     certifier: narration · user 안봄
│        (import 구조적 차단)   decorrelation 경계
│                                                  │ GateDecision
└──────────────────────────────────────────────────┼───────────────
                                        PUBLISH ────┴──── QUARANTINE
                                           ▼                 ▼
                                      SES → 이메일       사람 검토 큐

※ certifier 가 Graph node 가 *아닌* 이유: Graph 의 `_build_node_input` 이
  선행 node(author) 의 최종 답변을 다음 node 입력에 자동 주입 → certifier 가
  envelope 대신 author 답변을 보게 됨(decorrelation 붕괴). gate 가 envelope 를
  손으로 작성하면 그 경계가 구조적으로 자명 · 테스트로 assert 가능.
```

## 읽는 법 (legend)

- **굵은 `═══`(흐름)과 점선 `┊`(아키텍처)는 *같은* decorrelation 경계** — 하나는 시간 축, 하나는 공간(컴포넌트) 축에서 본 것.
- **gate** = plain Python, 신뢰 경계·비가역 결정 소유. **Graph** = gate *아래*(생성/평가 층)에서만.
- `draft_fn` / `revise_fn` / `verify_fn` = gate 의 **DI seam** — 지금은 plain 함수, 나중엔 Strands-graph-backed 로 *주입만 교체*(gate 결정 로직 무변경).

## 핵심 불변식 (그림이 강제하는 것)

1. **권위 페치 = fabric 소유**(content-addressed sha256) → author 가 *나중에 채점받을 증거*를 스스로 통제하지 못한다.
2. **certifier 입력 = 정확히 4필드 envelope** — `narration`/`reasoning`/`confidence` 는 *필드 자체가 부재*(블랙리스트 아닌 화이트리스트, dataclass 로 구조적 강제).
3. **gate 가 certifier 를 호출**(author 아님) → narration 차단을 *토폴로지로* 강제.
4. **비가역 발행 결정 = 코드**(LLM 아님), AND-게이트 — 모델 불일치 시 `QUARANTINE`(사람 검토).
5. **certifier 가 Graph node 가 아닌 이유** = Strands `_build_node_input` 누출(상세: §5.5.1).

> 위 1·2·4 는 테스트로 고정돼 있다(`tests/test_invariants.py`, `tests/test_gate.py`): `Envelope` = 정확히 4필드, author 가 certifier 를 import 하지 않음, gate 가 `certify` 를 호출.
