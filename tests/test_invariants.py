"""trust 불변식 — 구조적 강제를 *테스트*로 고정 (회귀 방지).

옵션 B(all-Strands 런타임 + subprocess certifier): author=Strands Agent, certifier=codex subprocess, gate=SOP.
실 LLM/codex 호출은 AWS·codex 필요(여기서 안 돎) — 대신 *구조적 불변식*과 *순수/결정론 부분*만 테스트.
"""
import inspect

import briefing.shared.harness.certifier as cert
from briefing.shared import gate
from briefing.shared.harness import author
from briefing.shared.harness.author import _parse_card_json, _to_draft_card
from briefing.shared.harness.certifier import Envelope, _build_codex_prompt, certify


def test_author_does_not_import_certifier():
    # 불변식: gate 가 certifier 를 호출, author 는 못 함 → author 는 certifier 를 import 하지 않는다
    src = inspect.getsource(author)
    assert "import certifier" not in src and "from .certifier" not in src


def test_gate_calls_certify():
    assert "certify" in inspect.getsource(gate)  # gate 가 certify 를 import·호출


def test_envelope_is_exactly_four_fields():
    # certifier 가 보는 전부 = 화이트리스트 4필드 (narration 필드 *부재* = 구조적 차단)
    assert set(Envelope.__dataclass_fields__) == {"source_excerpt", "claim_text", "claim_type", "schema"}


def test_certify_dispatches_by_claim_type(monkeypatch):
    # arithmetic → 결정론 코드 / 그 외 → codex. (실제 실행 없이 *라우팅*만 검증.)
    monkeypatch.setattr(cert, "_certify_arithmetic", lambda cid, env: cert.CertVerdict(cid, "VERIFIED", "ARITH"))
    monkeypatch.setattr(cert, "_certify_entailment", lambda cid, env: cert.CertVerdict(cid, "VERIFIED", "ENTAIL"))
    assert certify("C1", Envelope("s", "c", "arithmetic", "{}")).evidence == "ARITH"
    assert certify("C1", Envelope("s", "c", "entailment", "{}")).evidence == "ENTAIL"


def test_certify_arithmetic_is_deterministic_and_fail_closed():
    # 결정론 산술 = 다른 모델 불필요, byte-stable. 날조된 절대수는 BLOCKED(절대 거짓 VERIFIED 금지).
    src = "직원 약 100명 규모로 시작한다."
    assert certify("C1", Envelope(src, "직원이 100명이다.", "arithmetic", "{}")).verdict == "VERIFIED"
    blocked = certify("C2", Envelope(src, "매출 500억원을 기록했다.", "arithmetic", "{}"))
    assert blocked.verdict == "BLOCKED" and blocked.model == "deterministic"  # 500 ∉ source → 날조


def test_codex_prompt_contains_only_envelope_fields():
    # decorrelation 가드: certifier 프롬프트엔 envelope 4필드만 — narration/lens/skill 류 누설 0.
    p = _build_codex_prompt(Envelope("SRC-EXCERPT", "CLAIM-TEXT", "entailment", "SCHEMA-X"))
    assert "SRC-EXCERPT" in p and "CLAIM-TEXT" in p and "SCHEMA-X" in p
    for forbidden in ("narration", "reasoning", "lens", "skill", "why_it_matters", "confidence"):
        assert forbidden not in p.lower()


def test_author_parser_is_pure_and_normalizes_claim_type():
    # author 출력 파서는 순수(strands/AWS 불필요) — 노이즈에 견고 + claim_type 정규화.
    data = _parse_card_json(
        '잡음 {부분} 앞 {"headline":"H","summary":"S","why_it_matters":"W",'
        '"claims":[{"id":"C1","text":"t","claim_type":"arithmetic","importance":"core"},'
        '{"id":"C2","text":"u","claim_type":"weird"}]} 뒤 잡음'
    )
    card = _to_draft_card("SID", data)
    assert card.source_id == "SID" and card.headline == "H"
    assert card.claims[0].claim_type == "arithmetic" and card.claims[0].importance == "core"
    assert card.claims[1].claim_type == "entailment"  # 미상 값 → entailment 로 정규화
    assert card.claims[1].importance == "supporting"  # importance 누락 → 기본 supporting
