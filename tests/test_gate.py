"""gate — 오케스트레이터 + Maker-Checker 루프 + 불변식 + 2층화(reroute·해석층 가드)."""
import inspect

from briefing.core.authoring.author import Claim, DraftCard, Interpretation
from briefing.core.verification.certifier import CertVerdict
from briefing.core.gate import (
    GatedCard, _build_envelope, failed_claim_ids, interpret_card, produce_card,
    reroute_claim_types, verify_card,
)
from briefing.core.stores.source_store import FrozenSource


def _card(claims=()):
    return DraftCard("sid", "h", "s", "w", claims)


def _v(verdict, cid="C1"):
    return CertVerdict(cid, verdict, "ev")


def test_failed_claim_ids_only_blocked():
    vs = (_v("VERIFIED", "A"), _v("DEMOTED", "B"), _v("BLOCKED", "C"))
    assert failed_claim_ids(vs) == ("C",)  # DEMOTED 는 재도출 대상 아님


def test_produce_card_publish_first_round():
    g = produce_card(None, None, None, None,
                     draft_fn=lambda *a: _card(), verify_fn=lambda c: (_v("VERIFIED"),))
    assert g.decision == "PUBLISH" and g.attempts == 1


def test_produce_card_revise_then_publish():
    n = {"i": 0}

    def vf(_c):
        n["i"] += 1
        return (_v("BLOCKED"),) if n["i"] == 1 else (_v("VERIFIED"),)

    g = produce_card(None, None, None, None, max_attempts=2,
                     draft_fn=lambda *a: _card(), revise_fn=lambda *a, **k: _card(), verify_fn=vf)
    assert g.decision == "PUBLISH" and g.attempts == 2


def test_produce_card_quarantine_on_exhaustion():
    g = produce_card(None, None, None, None, max_attempts=2,
                     draft_fn=lambda *a: _card(), revise_fn=lambda *a, **k: _card(),
                     verify_fn=lambda c: (_v("BLOCKED"),))
    assert g.decision == "QUARANTINE" and g.attempts == 2


def test_produce_card_degrades_dropping_blocked_supporting():
    # graceful degradation: supporting claim 만 BLOCKED + 다른 claim VERIFIED → PUBLISH(미검증만 드롭)
    card = DraftCard("sid", "h", "s", "w",
                     (Claim("C1", "ok", "entailment", "core"), Claim("C2", "bad", "arithmetic", "supporting")))
    g = produce_card(None, None, None, None, max_attempts=1, draft_fn=lambda *a: card,
                     verify_fn=lambda c: (_v("VERIFIED", "C1"), _v("BLOCKED", "C2")))
    assert g.decision == "PUBLISH"  # 검증분 발행, 미검증만 드롭(카드 안 잃음)


def test_produce_card_quarantine_when_core_blocked():
    # 핵심(core) claim 이 BLOCKED → spine 붕괴 → QUARANTINE(드묾, 표본 감사)
    card = DraftCard("sid", "h", "s", "w",
                     (Claim("C1", "headline-support", "entailment", "core"),
                      Claim("C2", "ok", "entailment", "supporting")))
    g = produce_card(None, None, None, None, max_attempts=1, draft_fn=lambda *a: card,
                     verify_fn=lambda c: (_v("BLOCKED", "C1"), _v("VERIFIED", "C2")))
    assert g.decision == "QUARANTINE"


def test_build_envelope_is_four_fields_no_narration():
    src = FrozenSource("id", "u", "t", "원문 텍스트", "ts")
    env = _build_envelope(src, Claim("C1", "주장", "arithmetic"))
    assert set(env.__dataclass_fields__) == {"source_excerpt", "claim_text", "claim_type", "schema"}
    assert env.source_excerpt == "원문 텍스트" and env.claim_text == "주장"


def test_verify_card_is_user_blind():
    # 불변식 #4: verify 단계는 user/lens/skill 을 안 본다 (recorder 는 role-blind 순수 비용 sink — 예외 아님)
    assert set(inspect.signature(verify_card).parameters) == {"card", "store", "recorder"}


# ── claim_type 결정론 재라우팅 (card-layering §6 0단계 ⓑ) ──────────


def test_reroute_forces_arithmetic_on_numeric_text():
    # 숫자 포함 claim 은 author 라벨과 무관하게 arithmetic(결정론 코드 검증) — 분류 추첨 제거
    card = _card((Claim("C1", "직원이 100명이다.", "entailment", "core"),))
    assert reroute_claim_types(card).claims[0].claim_type == "arithmetic"


def test_reroute_keeps_entailment_without_numbers():
    card = _card((Claim("C1", "서울에 오피스를 개소했다.", "entailment", "core"),))
    assert reroute_claim_types(card).claims[0].claim_type == "entailment"


def test_produce_card_applies_reroute_to_draft():
    card = _card((Claim("C1", "직원이 100명이다.", "entailment", "core"),))
    g = produce_card(None, None, None, None,
                     draft_fn=lambda *a: card, verify_fn=lambda c: (_v("VERIFIED"),))
    assert g.card.claims[0].claim_type == "arithmetic"


# ── 해석층 (interpret_card) — 가드·격리·폴백 (card-layering §5) ──────────

_SRC = FrozenSource("sid", "u", "t", "서울 오피스 개소. 직원 약 100명 규모로 시작.", "ts")


def _fact(decision="PUBLISH", why="일반 해석."):
    card = DraftCard("sid", "h", "s", why,
                     (Claim("C1", "직원이 100명이다.", "arithmetic", "core"),
                      Claim("C2", "서울에 개소했다.", "entailment", "supporting")))
    return GatedCard(card, (_v("VERIFIED", "C1"), _v("VERIFIED", "C2")), decision, 1)


def test_interpret_card_swaps_why_only():
    out = interpret_card(_fact(), _SRC, None, None,
                         interp_fn=lambda *a: Interpretation("엔지니어에게 중요한 이유.", ("C1",)))
    assert out.card.why_it_matters == "엔지니어에게 중요한 이유."
    assert out.card.summary == "s" and out.card.headline == "h"     # 사실층 불변
    assert out.verdicts == _fact().verdicts and out.decision == "PUBLISH"


def test_interpret_card_grounded_number_passes():
    # why 의 숫자가 원문/검증 claims 에 존재하면 통과 (100명 은 원문에 있음)
    out = interpret_card(_fact(), _SRC, None, None,
                         interp_fn=lambda *a: Interpretation("직원 100명 규모라는 점이 핵심.", ("C1",)))
    assert "100" in out.card.why_it_matters


def test_interpret_card_new_number_falls_back():
    # 검증 우회 차단: 원문·claims 에 없는 수치(300%)를 밀수 → 사실층 why 로 폴백(trust laundering 방지)
    out = interpret_card(_fact(), _SRC, None, None,
                         interp_fn=lambda *a: Interpretation("생산성이 300% 오른다.", ("C1",)))
    assert out.card.why_it_matters == "일반 해석."


def test_interpret_card_requires_valid_citation():
    # 근거 claim id 인용 필수 — 없거나 미상 id 면 폴백
    no_cite = interpret_card(_fact(), _SRC, None, None,
                             interp_fn=lambda *a: Interpretation("해석.", ()))
    bad_cite = interpret_card(_fact(), _SRC, None, None,
                              interp_fn=lambda *a: Interpretation("해석.", ("C9",)))
    assert no_cite.card.why_it_matters == "일반 해석."
    assert bad_cite.card.why_it_matters == "일반 해석."


def test_interpret_card_strips_parenthetical_claim_citations():
    # 회귀(2026-07-27 라이브 발송 발견): "역할 분리(C4, C5)가…"처럼 괄호 claim id 인용이 독자
    # 이메일까지 노출됐다 — interp_system.md 계약은 id 를 based_on 으로만 허용한다.
    # 괄호 인용은 들어내도 문장이 온전하므로 결정론 살균(제거)한다.
    # (동시에 2026-07-06 오탐 회귀도 덮는다: id 속 숫자 1·2 가 살균으로 사라져 수치 검사를 안 건드림.)
    out = interpret_card(_fact(), _SRC, None, None,
                         interp_fn=lambda *a: Interpretation("역할 분리(C1, C2)가 비용을 낮춘다.", ("C1",)))
    assert out.card.why_it_matters == "역할 분리가 비용을 낮춘다."


def test_interpret_card_strips_citation_without_leaving_whitespace_scar():
    # 앞 공백형 인용 "…낮춘다 (C1)." — 제거 흔적(이중 공백·" .")이 독자 문장에 남으면 안 됨
    out = interpret_card(_fact(), _SRC, None, None,
                         interp_fn=lambda *a: Interpretation("비용을 낮춘다 (C1). 그래서 중요하다.", ("C1",)))
    assert out.card.why_it_matters == "비용을 낮춘다. 그래서 중요하다."


def test_interpret_card_keeps_prose_parentheses():
    # 과잉 제거 방지: 괄호 안이 *id 목록일 때만* 제거 — 산문 괄호는 보존(숫자는 원문 근거라 통과)
    out = interpret_card(_fact(), _SRC, None, None,
                         interp_fn=lambda *a: Interpretation("규모(직원 100명)가 핵심.", ("C1",)))
    assert out.card.why_it_matters == "규모(직원 100명)가 핵심."


def test_interpret_card_bare_claim_id_falls_back():
    # 인라인 인용 "C1이 보여주듯…"은 id 가 문장의 주어라 지우면 한국어가 깨진다 → 결정론 수리 불가.
    # 깨진 문장을 독자에게 보내느니 사실층 why 로 폴백(층별 격리와 같은 원칙).
    out = interpret_card(_fact(), _SRC, None, None,
                         interp_fn=lambda *a: Interpretation("C1이 보여주듯 규모가 핵심.", ("C1",)))
    assert out.card.why_it_matters == "일반 해석."


def test_interpret_card_fallback_is_visible_without_debug(capsys, monkeypatch):
    # 폴백은 lens 해석 한 단락을 조용히 버리는 열화다 — DEBUG off 인 프로덕션에서도 관측돼야
    # 발동 빈도를 재평가할 수 있다(dprint 는 DEBUG 게이트라 운영에서 무증상이었음).
    monkeypatch.delenv("DEBUG", raising=False)
    out = interpret_card(_fact(), _SRC, None, None,
                         interp_fn=lambda *a: Interpretation("생산성이 300% 오른다.", ("C1",)))
    assert out.card.why_it_matters == "일반 해석."
    assert "미검증 수치 밀수" in capsys.readouterr().err


def test_interpret_card_isolates_interp_failure():
    # 층별 격리(2026-07-02 인시던트 교훈의 층 하강): 해석 실패 → 카드가 아니라 해석만 강등
    def boom(*_a):
        raise RuntimeError("interp harness down")
    out = interpret_card(_fact(), _SRC, None, None, interp_fn=boom)
    assert out.card.why_it_matters == "일반 해석." and out.decision == "PUBLISH"


def test_interpret_card_skips_quarantined_fact():
    # QUARANTINE 사실층엔 해석층 생성 차단(gate 결정 재사용) — interp 호출 자체가 없어야 함
    called = {"n": 0}

    def spy(*_a):
        called["n"] += 1
        return Interpretation("x", ("C1",))

    fact = _fact(decision="QUARANTINE")
    out = interpret_card(fact, _SRC, None, None, interp_fn=spy)
    assert called["n"] == 0 and out is fact


def test_interpret_card_passes_only_verified_claims():
    # 해석은 VERIFIED claims 위에서만 — DEMOTED/BLOCKED 는 seam 에서 이미 제외
    card = DraftCard("sid", "h", "s", "일반 해석.",
                     (Claim("C1", "ok", "entailment", "core"),
                      Claim("C2", "meh", "entailment", "supporting")))
    fact = GatedCard(card, (_v("VERIFIED", "C1"), _v("DEMOTED", "C2")), "PUBLISH", 1)
    seen = {}

    def spy(source, claims, user, settings):
        seen["ids"] = tuple(c.id for c in claims)
        return Interpretation("해석.", ("C1",))

    interpret_card(fact, _SRC, None, None, interp_fn=spy)
    assert seen["ids"] == ("C1",)


def test_interpret_card_persists_based_on():
    """해석층이 밝힌 근거 claim 을 카드에 남긴다 — 사후 감사의 전제.

    계약(interp_system.md:13)은 `based_on` 인용을 **필수**로 요구하고 lint 가 검사하지만,
    2026-07-28 이전에는 검사 후 폐기돼 "이 해석이 근거를 옳게 골랐나"를 물을 방법이 없었다
    (해석층은 certifier 를 거치지 않는 유일한 발행 텍스트라 더 중요하다).
    """
    out = interpret_card(_fact(), _SRC, None, None,
                         interp_fn=lambda *a: Interpretation("엔지니어에게 중요한 이유.", ("C1", "C2")))
    assert out.card.based_on == ("C1", "C2")
    assert out.card.why_it_matters == "엔지니어에게 중요한 이유."      # 기존 동작 불변


def test_interpret_card_fallback_claims_no_basis():
    """폴백(해석 실패)은 사실층 why 를 쓰므로 근거 인용도 없어야 한다 — 없는 근거를 주장하지 않는다."""
    out = interpret_card(_fact(), _SRC, None, None,
                         interp_fn=lambda *a: Interpretation("생산성이 300% 오른다.", ("C1",)))  # 수치 밀수 → 폴백
    assert out.card.why_it_matters == "일반 해석."
    assert out.card.based_on == ()
