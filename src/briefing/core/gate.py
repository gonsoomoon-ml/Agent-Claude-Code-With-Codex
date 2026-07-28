"""gate — verify-before-publish 오케스트레이터 (결정론 코드 = 신뢰의 원천).

★ 이 모듈이 오케스트레이터다 (Strands/author 아님). 흐름(Maker-Checker 루프 포함):
  gate → author(초안+claims) → gate 가 envelope sanitize → certifier(판정)
       → 실패 claim 있으면 author 재도출(최소 피드백) → 재검증 … (캡) → PUBLISH/QUARANTINE → render.

불변식:
- certifier 호출 주체 = gate (이 모듈이 certify 를 import·호출; author 는 못 함). **verify 는 user-blind**.
- envelope 외 author 산출(narration) 누설 0 — _build_envelope 가 동결본에서 4필드만 추출.
- 실패 정책(graceful degradation, 스케일): DEMOTED='(미확인)' 라벨로 남김; BLOCKED 소진 시 *그 claim 만 드롭*하고
  검증분 발행 — **핵심(core) claim 막힘 or VERIFIED 0** 일 때만 카드 QUARANTINE(드묾·표본 감사). 미검증은 발행 안 됨(fail-closed).
- ★ 루프 decorrelation 보존: 다른 계열(Claude↔Codex) + 피드백은 *실패 claim id 만*(certifier 추론 미전달)
  + 실패 claim 만 재도출(thrashing 방지) + 캡 + 소진 시 QUARANTINE.
  (*같은-모델·전체-재생성* 루프가 thrashing 하는 것과 대조 — 우리는 cross-family + 최소 피드백.)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, replace
from functools import partial
from typing import Literal

from . import _debug
from .config import Settings, UserConfig
from .authoring import author
from .authoring.author import Claim, DraftCard, Interpretation
from .stores.usage import EST_CERTIFY_USD_PER_ENTAILMENT
from .verification.certifier import _NUM_RE, CertVerdict, Envelope, certify
from .stores.source_store import FrozenSource, SourceStore

_SCHEMA = '{"verdict":"VERIFIED|DEMOTED|BLOCKED","evidence":"str"}'

GateDecision = Literal["PUBLISH", "QUARANTINE"]


@dataclass(frozen=True)
class GatedCard:
    card: DraftCard
    verdicts: tuple[CertVerdict, ...]
    decision: GateDecision   # 카드 최종: PUBLISH / QUARANTINE(author↔certifier 불일치 소진 → 사람 검토)
    attempts: int            # author↔certifier 라운드 수 (감사 = 원장)


def reroute_claim_types(card: DraftCard) -> DraftCard:
    """claim_type 결정론 재라우팅(card-layering §6 ⓑ) — 숫자 포함 claim 은 author 라벨 무시하고 arithmetic 강제.

    같은 사실이 lens/시행마다 arithmetic↔entailment 로 흔들리던 '분류 추첨'을 제거 — 검증 경로를
    author 의 확률 분류가 아니라 *코드*가 정한다(certifier 의 _NUM_RE 와 단일 정의 공유).
    """
    claims = tuple(
        replace(c, claim_type="arithmetic") if _NUM_RE.search(c.text) and c.claim_type != "arithmetic" else c
        for c in card.claims
    )
    return card if claims == card.claims else replace(card, claims=claims)


def _build_envelope(source: FrozenSource, claim: Claim) -> Envelope:
    """gate 가 동결본에서 화이트리스트 4필드만 추출 — narration 절대 미포함."""
    return Envelope(
        source_excerpt=source.text,  # TODO: claim 관련 구절로 좁히기(현재는 동결 전문)
        claim_text=claim.text,
        claim_type=claim.claim_type,
        schema=_SCHEMA,
    )


def verify_card(card: DraftCard, store: SourceStore, *, recorder=None) -> tuple[CertVerdict, ...]:
    """카드의 각 claim 을 certifier 로 독립 검증 (gate 가 호출, **user-blind**). per-claim verdicts 반환.

    `recorder`(옵션) — entailment claim 1건당 `EST_CERTIFY_USD_PER_ENTAILMENT` 추정치를 기록(certifier 무수정 —
    certifier 는 자기 비용을 모름·envelope-only 불변식 보존; 추정은 gate 가 claim_type 개수로 계산).
    """
    source = store.get_source(card.source_id)
    # TODO(fail-closed): certify 실패(codex 오류·타임아웃)는 *보수적으로* — DEMOTED/BLOCKED, **절대 VERIFIED 아님**.
    #   per-claim try/except 로 격리(한 claim 실패가 전체 run 을 죽이지 않게). 구현 시 추가.
    verdicts: list[CertVerdict] = []
    for c in card.claims:
        envelope = _build_envelope(source, c)
        _debug.dprint_box(f"envelope → certifier · claim {c.id} ({c.claim_type})", _debug.redact_envelope(envelope))
        v = certify(c.id, envelope)
        _debug.dprint(f"certifier ⊢ {c.id}", f"{v.verdict} ({v.model}) — {v.evidence}",
                      "red" if v.verdict == "BLOCKED" else "yellow")
        verdicts.append(v)
    if recorder is not None:
        n_entail = sum(1 for c in card.claims if c.claim_type == "entailment")
        recorder.add(n_entail * EST_CERTIFY_USD_PER_ENTAILMENT)
    return tuple(verdicts)


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
    recorder=None,
) -> GatedCard:
    """★ Maker-Checker 루프 (author↔certifier) — **decorrelation 보존형**.

    author(초안) → verify → 실패 claim 있으면 author 재도출(실패 claim 만, 피드백=실패 id 만) → 재verify …
    캡(max_attempts) 소진 시 **QUARANTINE**(BLOCKED 남음 → 자동 발행 금지, 사람 검토).
    *피드백에 certifier 추론·정답을 안 줌* → 라운드 간에도 'teaching to the test'(상관) 회피.
    (draft_fn/revise_fn/verify_fn = 의존성 주입 — 테스트용; 기본은 author·verify_card.)
    `recorder`(옵션) — 기본 DI 경로(draft_fn/revise_fn/verify_fn 미주입 시)에만 partial 바인딩되어
    author 실비용 + certify 추정치를 누적(주입된 fake 는 3-인자 그대로 — recorder 무관).
    """
    # DI seam — None 이면 실제 구현으로 배선. 테스트는 fake 주입(결정론), 미래엔 Strands-graph-backed 로
    # *주입만 교체* → gate 결정 로직 무변경. verify_fn 만 store 클로저(certify 는 envelope 만 보므로 store 미전달).
    draft_fn = draft_fn or partial(author.draft_card, recorder=recorder)  # 기본 = headless Claude Code(`claude -p`) 작성자
    revise_fn = revise_fn or partial(author.revise_claims, recorder=recorder)  # 기본 = 같은 `claude -p`(실패 claim 만 재도출)
    verify_fn = verify_fn or (lambda c: verify_card(c, store, recorder=recorder))  # 기본 = codex certifier(per claim)

    card = reroute_claim_types(draft_fn(source, user, settings))  # 재라우팅 = 검증 경로를 코드가 결정
    _debug.dprint("gate ← author", f"draft: {len(card.claims)} claims · source={card.source_id[:12]}")
    verdicts: tuple[CertVerdict, ...] = ()
    for attempt in range(1, max_attempts + 1):
        verdicts = verify_fn(card)
        failed = failed_claim_ids(verdicts)
        if not failed:
            _debug.dprint("gate decision", f"PUBLISH (attempt {attempt})", "green")
            return GatedCard(card, verdicts, "PUBLISH", attempt)
        if attempt < max_attempts:
            _debug.dprint("gate → revise", f"failed={list(failed)} → 실패 claim 재도출 (attempt {attempt + 1})", "yellow")
            card = reroute_claim_types(revise_fn(source, user, settings, prior=card, failed_ids=failed))
    # 캡 소진: BLOCKED 가 남음 → claim-단위 graceful degradation (카드 통째 격리 대신)
    return _degrade_or_quarantine(card, verdicts, max_attempts)


def _degrade_or_quarantine(
    card: DraftCard, verdicts: tuple[CertVerdict, ...], attempts: int
) -> GatedCard:
    """캡 소진 후 BLOCKED 잔존 시 — 카드 통째 격리 대신 **claim-단위 graceful degradation**.

    스케일 근거: "QUARANTINE → 사람 전수검토"는 대량 처리에서 비현실적(큐가 안 읽히면 silent drop) →
    BLOCKED claim 만 *드롭*하고 검증된 부분집합을 발행. 처분은 사람 큐가 아니라 드롭 + 표본 감사 + 집계율 모니터링.
      - **핵심(core) claim 이 BLOCKED** → 카드 spine 붕괴 → QUARANTINE(드묾, 표본 감사 대상).
      - VERIFIED ≥1 + 핵심 안 막힘 → **PUBLISH**(BLOCKED 는 render 가 생략 + '보류' 표시 — graceful degradation).
      - VERIFIED 0 (남은 게 DEMOTED/BLOCKED 뿐) → QUARANTINE(확실히 발행할 게 없음).
    fail-closed 유지: 미검증 claim 은 *발행되지 않음*(드롭 ≠ 발행).
    """
    by_id = {v.claim_id: v.verdict for v in verdicts}
    core_blocked = any(c.importance == "core" and by_id.get(c.id) == "BLOCKED" for c in card.claims)
    has_verified = any(v.verdict == "VERIFIED" for v in verdicts)
    if core_blocked or not has_verified:
        _debug.dprint("gate decision", "QUARANTINE (core BLOCKED 또는 VERIFIED 0 — 표본 감사)", "red")
        return GatedCard(card, verdicts, "QUARANTINE", attempts)
    dropped = sum(1 for v in verdicts if v.verdict == "BLOCKED")
    _debug.dprint("gate decision", f"PUBLISH degraded — BLOCKED {dropped}개 드롭, 검증분 발행", "green")
    return GatedCard(card, verdicts, "PUBLISH", attempts)


# ───────────────────────── 해석층 (interpretation layer) — card-layering §5 ─────────────────────────


def verified_claims(fact: GatedCard) -> tuple[Claim, ...]:
    """사실층에서 VERIFIED 로 판정된 claim 만 — 해석층 seam 은 이것만 본다(미검증 claim 미노출)."""
    ok = {v.claim_id for v in fact.verdicts if v.verdict == "VERIFIED"}
    return tuple(c for c in fact.card.claims if c.id in ok)


def _num_tokens(text: str) -> set[str]:
    """텍스트의 숫자 토큰(콤마 정규화) — certifier 의 _NUM_RE 와 단일 정의 공유."""
    return {m.group().replace(",", "") for m in _NUM_RE.finditer(text)}


# claim id 토큰. 후행 \b 없음: 한글 조사가 id 에 직접 붙고("C1이") 한글도 \w 라 boundary 가 성립하지 않는다.
_CLAIM_ID_RE = re.compile(r"\bC\d+")
# 괄호 안이 **오직** claim id 목록일 때만 '인용'으로 본다 — "(C4, C5)" O / "(직원 100명)" X.
_CITATION_PAREN_RE = re.compile(r"\s*[(（]\s*C\d+(?:\s*[,·、]\s*C\d+)*\s*[)）]")


def _strip_claim_citations(why: str) -> str:
    """독자 대면 why 에서 **괄호형 claim id 인용만** 제거한다(앞 공백까지 함께 — 흔적 0).

    계약(interp_system.md): id 인용은 `based_on` 필드로만 — 독자는 claim id 를 볼 수 없다.
    괄호 인용("역할 분리(C4, C5)가")은 들어내도 문장이 온전하므로 결정론 수리가 가능하다.
    인라인 인용("C1이 보여주듯")은 id 가 문장 성분(주어)이라 지우면 한국어가 깨진다 — 여기서
    손대지 않고 lint 가 폴백시킨다(깨진 문장 발행 < 사실층 why 발행).
    """
    return _CITATION_PAREN_RE.sub("", why).strip()


def _interp_lint(interp: Interpretation, fact: GatedCard, source: FrozenSource) -> str | None:
    """해석층 결정론 lint (no-new-facts 가드) — 통과 None / 실패 사유 문자열.

    ★ 입력은 `_strip_claim_citations` 로 **살균된 뒤**의 해석이다(= 실제 발행될 문자열을 검사).

    trust laundering 차단: 해석은 "✓ 검증" 배지 카드에 실리므로, 검증되지 않은 새 사실(특히 수치)을
    밀수할 수 없어야 한다. 규칙(v1 — 미결 #5 의 '결정론 lint 부터' 채택):
      ① why 비어있지 않음  ② based_on ≠ ∅ 이고 전부 VERIFIED claim id
      ③ 본문에 claim id 잔존 없음(살균 불가 형태 = 독자 노출) — 2026-07-27 라이브 회귀
      ④ why 의 모든 숫자 토큰이 (동결 원문 ∪ VERIFIED claims) 에 존재.
    ③ 이 ④ 보다 앞서므로 id 속 숫자가 '미검증 수치'로 오탐될 여지가 없다(2026-07-06 오탐 회귀를
    가리개(re.sub)가 아니라 **제거 또는 기각**으로 해소 — 관용이 유출로 굳던 경로를 끊는다).
    """
    if not interp.why_it_matters.strip():
        return "why 빈값"
    ok_ids = {c.id for c in verified_claims(fact)}
    if not interp.based_on or not set(interp.based_on) <= ok_ids:
        return f"based_on 인용 무효 ({list(interp.based_on)} ⊄ {sorted(ok_ids)})"
    if leaked := _CLAIM_ID_RE.findall(interp.why_it_matters):
        return f"본문 claim id 인용 잔존 {sorted(set(leaked))} (살균 불가 형태)"
    allowed = _num_tokens(source.text) | {t for c in verified_claims(fact) for t in _num_tokens(c.text)}
    smuggled = _num_tokens(interp.why_it_matters) - allowed
    if smuggled:
        return f"미검증 수치 밀수 {sorted(smuggled)}"
    return None


def interpret_card(
    fact: GatedCard,
    source: FrozenSource,
    user: UserConfig,
    settings: Settings,
    *,
    interp_fn=None,
    recorder=None,
) -> GatedCard:
    """검증된 사실층 위에 lens 해석(why)만 교체 — 가드 통과 시에만. 실패는 **해석만 강등**(층별 격리).

    - QUARANTINE 사실층 → 해석 생성 자체를 차단(gate 결정 재사용, LLM 비용 0).
    - interp 실패(예외)·lint 실패 → 사실층(일반 lens) why 그대로 반환 — 카드·브리핑은 무붕괴
      (2026-07-02 인시던트의 격리 교훈을 카드→층 단위로 하강).
    - verdicts·decision·summary·claims 는 불변 — 해석층은 검증 결과를 절대 못 건드린다.
    `recorder`(옵션) — 기본 DI 경로(interp_fn 미주입 시)에만 partial 바인딩(주입된 fake 는 recorder 무관).
    """
    if fact.decision == "QUARANTINE":
        return fact
    interp_fn = interp_fn or partial(author.draft_interpretation, recorder=recorder)  # 기본 = 같은 headless `claude -p`(짧은 출력)
    try:
        interp = interp_fn(source, verified_claims(fact), user, settings)
    except Exception as e:  # noqa: BLE001 — 층별 격리: 해석 실패가 검증된 카드를 죽이면 안 됨
        _debug.warn("gate interp", f"{fact.card.source_id[:12]}: {type(e).__name__}: {e} → 사실층 why 폴백")
        return fact
    interp = replace(interp, why_it_matters=_strip_claim_citations(interp.why_it_matters))  # 살균 후 lint = 발행문 검사
    reason = _interp_lint(interp, fact, source)
    if reason is not None:
        # warn(=DEBUG 무관 stderr→CloudWatch): 폴백은 lens 해석 한 단락을 버리는 조용한 열화다.
        # dprint 였을 땐 운영에서 무증상 → 가드 발동 빈도를 재평가할 수 없었다(2026-07-27).
        _debug.warn("gate interp", f"{fact.card.source_id[:12]}: lint 실패({reason}) → 사실층 why 폴백")
        return fact
    # based_on 도 함께 이식 — 인용을 요구·검사하고 버리면 사후 감사가 불가능하다(2026-07-28).
    # 폴백 경로(위 두 return)는 fact 를 그대로 돌려주므로 based_on 이 빈 튜플로 남는다 = 없는 근거를 주장하지 않음.
    return replace(fact, card=replace(fact.card, why_it_matters=interp.why_it_matters,
                                      based_on=interp.based_on))
