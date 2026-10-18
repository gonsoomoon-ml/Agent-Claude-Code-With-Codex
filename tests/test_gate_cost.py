"""gate 의 recorder 배선 — verify_card 가 검증 AI 의 실측 토큰 × 단가를 기록하는지(F5, claim 당 고정 추정치 대체)."""
import pytest

from briefing.core.gate import verify_card
from briefing.core.stores.usage import UsageRecorder
from briefing.core.authoring.author import Claim, DraftCard


class _Store:
    def get_source(self, sid):
        return type("FS", (), {"text": "원문 100 달러"})()


def _card():
    return DraftCard(source_id="s", headline="h", summary="", why_it_matters="",
                     claims=(Claim("C1", "함의 주장", "entailment"),
                             Claim("C2", "숫자 100", "arithmetic")))


def _patch(monkeypatch, model: str):
    import briefing.core.gate as gate

    def fake_certify(cid, env):   # 토큰은 codex 를 부른 함의 claim 에만 — 산술은 코드라 0
        usage = {"input_tokens": 7900, "output_tokens": 127} if env.claim_type == "entailment" else {}
        return gate.CertVerdict(cid, "VERIFIED", "", "x", usage)

    monkeypatch.setattr(gate, "certify", fake_certify)
    monkeypatch.setattr(gate, "codex_model_id", lambda: model)


def test_verify_card_records_measured_codex_cost(monkeypatch):
    _patch(monkeypatch, "openai.gpt-5.5")
    rec = UsageRecorder()
    verify_card(_card(), _Store(), recorder=rec)
    assert rec.total() == pytest.approx((7900 * 5.0 + 127 * 30.0) / 1e6)   # GPT-5.5 = 100만 토큰당 $5/$30


def test_unknown_certifier_model_is_not_priced(monkeypatch, capsys):
    """단가표에 없는 모델은 값을 지어내지 않는다 — 기록에서 빼고 경고를 남긴다."""
    _patch(monkeypatch, "openai.gpt-9")
    rec = UsageRecorder()
    verify_card(_card(), _Store(), recorder=rec)
    assert rec.total() == 0.0
    assert "단가 미상" in capsys.readouterr().err
