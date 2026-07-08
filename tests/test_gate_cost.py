"""gate 의 recorder 배선 테스트 — verify_card 가 entailment claim 당 certify 추정치를 기록하는지."""
from briefing.core.gate import verify_card
from briefing.core.stores.usage import UsageRecorder, EST_CERTIFY_USD_PER_ENTAILMENT
from briefing.core.authoring.author import Claim, DraftCard


class _Store:
    def get_source(self, sid):
        return type("FS", (), {"text": "원문 100 달러"})()


def _card():
    return DraftCard(source_id="s", headline="h", summary="", why_it_matters="",
                     claims=(Claim("C1", "함의 주장", "entailment"),
                             Claim("C2", "숫자 100", "arithmetic")))


def test_verify_card_records_certify_estimate_for_entailment_only(monkeypatch):
    import briefing.core.gate as gate
    monkeypatch.setattr(gate, "certify",
                        lambda cid, env: gate.CertVerdict(cid, "VERIFIED", "", "x"))
    rec = UsageRecorder()
    verify_card(_card(), _Store(), recorder=rec)
    # 1 entailment claim → 1 추정 콜, arithmetic 은 무료 → 미포함
    assert rec.total() == EST_CERTIFY_USD_PER_ENTAILMENT
