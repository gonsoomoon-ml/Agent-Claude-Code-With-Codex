"""gate — verify-before-publish 오케스트레이터 (결정론 코드 = 신뢰의 원천).

★ 이 모듈이 오케스트레이터다 (Strands/author 아님). 흐름(Maker-Checker 루프 포함):
  gate → author(초안+claims) → gate 가 envelope sanitize → certifier(판정)
       → 실패 claim 있으면 author 재도출(최소 피드백) → 재검증 … (캡) → PUBLISH/QUARANTINE → render.

불변식:
- certifier 호출 주체 = gate (이 모듈이 certify 를 import·호출; author 는 못 함). **verify 는 user-blind**.
- envelope 외 author 산출(narration) 누설 0 — _build_envelope 가 동결본에서 4필드만 추출.
- 실패 정책: 조용한 드롭 금지 — DEMOTED='(미확인)' 라벨로 남김, BLOCKED 소진 시 **QUARANTINE**(fail-closed).
- ★ 루프 decorrelation 보존: 다른 계열(Claude↔Codex) + 피드백은 *실패 claim id 만*(certifier 추론 미전달)
  + 실패 claim 만 재도출(thrashing 방지) + 캡 + 소진 시 QUARANTINE.
  (Self-Correcting-Translation-Agent 의 *같은-모델·전체-재생성* 루프가 thrashing 한 것과 대조.)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from . import author
from .author import Claim, DraftCard
from .certifier import CertVerdict, Envelope, certify
from .config import Settings, UserConfig
from .source_store import FrozenSource, SourceStore

_SCHEMA = '{"verdict":"VERIFIED|DEMOTED|BLOCKED","evidence":"str"}'

GateDecision = Literal["PUBLISH", "QUARANTINE"]


@dataclass(frozen=True)
class GatedCard:
    card: DraftCard
    verdicts: tuple[CertVerdict, ...]
    decision: GateDecision   # 카드 최종: PUBLISH / QUARANTINE(author↔certifier 불일치 소진 → 사람 검토)
    attempts: int            # author↔certifier 라운드 수 (감사 = 원장)


def _build_envelope(source: FrozenSource, claim: Claim) -> Envelope:
    """gate 가 동결본에서 화이트리스트 4필드만 추출 — narration 절대 미포함."""
    return Envelope(
        source_excerpt=source.text,  # TODO: claim 관련 구절로 좁히기(현재는 동결 전문)
        claim_text=claim.text,
        claim_type=claim.claim_type,
        schema=_SCHEMA,
    )


def verify_card(card: DraftCard, store: SourceStore) -> tuple[CertVerdict, ...]:
    """카드의 각 claim 을 certifier 로 독립 검증 (gate 가 호출, **user-blind**). per-claim verdicts 반환."""
    source = store.get_source(card.source_id)
    # TODO(fail-closed): certify 실패(codex 오류·타임아웃)는 *보수적으로* — DEMOTED/BLOCKED, **절대 VERIFIED 아님**.
    #   per-claim try/except 로 격리(한 claim 실패가 전체 run 을 죽이지 않게). 구현 시 추가
    #   (지금은 stub 의 NotImplementedError 를 가리지 않으려 propagate).
    return tuple(certify(c.id, _build_envelope(source, c)) for c in card.claims)


def failed_claim_ids(verdicts: tuple[CertVerdict, ...]) -> tuple[str, ...]:
    """재도출 대상 = BLOCKED claim. (DEMOTED 는 '(미확인)' 라벨로 남김 — 재도출 안 함.)"""
    return tuple(v.claim_id for v in verdicts if v.verdict == "BLOCKED")


def produce_card(
    source: FrozenSource,
    user: UserConfig,
    settings: Settings,
    store: SourceStore,
    *,
    max_attempts: int = 2,
    draft_fn=None,
    revise_fn=None,
    verify_fn=None,
) -> GatedCard:
    """★ Maker-Checker 루프 (author↔certifier) — **decorrelation 보존형**.

    author(초안) → verify → 실패 claim 있으면 author 재도출(실패 claim 만, 피드백=실패 id 만) → 재verify …
    캡(max_attempts) 소진 시 **QUARANTINE**(BLOCKED 남음 → 자동 발행 금지, 사람 검토).
    *피드백에 certifier 추론·정답을 안 줌* → 라운드 간에도 'teaching to the test'(상관) 회피.
    (draft_fn/revise_fn/verify_fn = 의존성 주입 — 테스트용; 기본은 author·verify_card.)
    """
    draft_fn = draft_fn or author.draft_card
    revise_fn = revise_fn or author.revise_claims
    verify_fn = verify_fn or (lambda c: verify_card(c, store))

    card = draft_fn(source, user, settings)
    verdicts: tuple[CertVerdict, ...] = ()
    for attempt in range(1, max_attempts + 1):
        verdicts = verify_fn(card)
        failed = failed_claim_ids(verdicts)
        if not failed:
            return GatedCard(card, verdicts, "PUBLISH", attempt)
        if attempt < max_attempts:
            card = revise_fn(source, user, settings, prior=card, failed_ids=failed)
    # 캡 소진: BLOCKED 가 남음 → 자동 발행 금지(fail-closed), 사람 검토로 격리
    return GatedCard(card, verdicts, "QUARANTINE", max_attempts)
