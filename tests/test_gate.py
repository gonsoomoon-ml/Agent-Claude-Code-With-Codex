"""gate — 오케스트레이터 + Maker-Checker 루프 + 불변식."""
import inspect

from briefing.shared.author import Claim, DraftCard
from briefing.shared.certifier import CertVerdict
from briefing.shared.gate import _build_envelope, failed_claim_ids, produce_card, verify_card
from briefing.shared.source_store import FrozenSource


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
    # 불변식 #4: verify 단계는 user/lens/skill 을 안 본다
    assert set(inspect.signature(verify_card).parameters) == {"card", "store"}
