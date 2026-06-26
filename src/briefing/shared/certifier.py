"""certifier — Codex(`codex exec`) 독립 인증자. 최소 컨텍스트, BLOCK권만.

불변식 (design/architecture/four-component-analysis.md §6):
- **gate 가 호출** (author 아님). certifier 는 *tool-starved* — 화이트리스트 4필드 envelope 만 받음:
  {source_excerpt, claim_text, claim_type, schema}. narration/reasoning/confidence 는 *존재 자체* 금지.
- 다른 모델 계열(decorrelation) + 결정론 코어(산술=샌드박스 코드, 함의=pinned NLI 가능 시).
- certifier 모델은 **codex 자신의 설정**(`~/.codex/config.toml`: model_provider=amazon-bedrock, model)이 소유 —
  우리 .env 가 아님. certify() 는 *사용된 모델을 결과에 기록*(provenance)만 하고 설정하지 않는다.

이 모듈은 envelope *외* 어떤 author 산출도 받지 않는다(누설 0 = 토폴로지 불변식).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Verdict = Literal["VERIFIED", "DEMOTED", "BLOCKED"]


@dataclass(frozen=True)
class Envelope:
    """certifier 에 주는 *유일* 입력 (화이트리스트 4필드)."""
    source_excerpt: str
    claim_text: str
    claim_type: str
    schema: str


@dataclass(frozen=True)
class CertVerdict:
    claim_id: str
    verdict: Verdict
    evidence: str    # certifier 가 가리킨 원문 근거 구절
    model: str = ""  # 검증을 수행한 codex 모델 (provenance — runtime 에 codex 출력에서 채움)


def certify(claim_id: str, envelope: Envelope) -> CertVerdict:
    """envelope 1건 → per-claim verdict. **claim_type 으로 디스패치**("결정론 게이트=신뢰" 헤드라인).

    - `arithmetic` → **결정론 코드**(샌드박스 재추출·재계산, byte-stable) — verdict 가 LLM 판단이 아니라 *코드*.
    - `entailment` → **`codex exec`**(다른 계열, decorrelation) / 가능 시 pinned NLI.
    구현 불변식: ① envelope 4필드 *외* 아무것도 codex 프롬프트에 안 넣음(누설 0),
                 ② **codex 는 clean dir 에서 실행** — repo `CLAUDE.md`/`AGENTS.md` 자동 로드 금지
                 (decorrelation; CLAUDE.md '런타임 하니스 격리' 참조).
    """
    if envelope.claim_type == "arithmetic":
        return _certify_arithmetic(claim_id, envelope)
    return _certify_entailment(claim_id, envelope)


def _certify_arithmetic(claim_id: str, envelope: Envelope) -> CertVerdict:
    """결정론 산술 재도출 — source 에서 숫자/날짜/% 재추출 후 byte-stable 재계산(LLM 아님)."""
    raise NotImplementedError("deterministic arithmetic re-derivation — 구현 예정")


def _certify_entailment(claim_id: str, envelope: Envelope) -> CertVerdict:
    """함의 — `codex exec`(다른 계열, clean dir, envelope-only) 또는 pinned NLI.

    cross-lingual(영어 원문 ↔ 한국어 claim): **backtranslation 으로 monolingual 화** —
      한국어 claim → 영어 역번역 → *영어* 원문과 영어 NLI. cross-lingual 함의(어려움)를 monolingual NLI(쉬움)로 붕괴.
      단 역번역↔원문 비교는 LLM '눈대중'이 아니라 *결정론/다른-계열*로(Self-Correcting-Translation-Agent 대비 개선).
    참조: scratchpad/run_two_model.py (gpt-oss 는 reasoningContent 블록 반환 → text 블록만 파싱).
    """
    raise NotImplementedError("codex exec / pinned NLI entailment — 구현 예정")
