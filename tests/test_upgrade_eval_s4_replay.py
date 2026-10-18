"""S4 재생 실험 — 지금 다시 쓰기(R0, 얼린 사본)와 S4(R4, 지시 + 범위 가드)를 같은 막힌 카드로 견주는 도구."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from upgrade_eval import s4_replay as r  # noqa: E402

from briefing.core.authoring.author import Claim, DraftCard  # noqa: E402
from briefing.core.gate import GatedCard  # noqa: E402
from briefing.core.stores.cache import _serialize  # noqa: E402
from briefing.core.stores.source_store import FrozenSource  # noqa: E402
from briefing.core.verification.certifier import CertVerdict  # noqa: E402

SRC = FrozenSource("sid", "https://example.com/a", "제목", "원문 본문이다.", "2026-10-18T00:00:00Z")
PRIOR = DraftCard("sid", "제목", "A사는 신제품을 출시했다. 신제품 점수는 72%다. 가격은 비싸다.", "독자에게 중요하다.",
                  (Claim("C1", "A사는 신제품을 출시했다.", "entailment", "core"),
                   Claim("C2", "신제품 점수는 72%다.", "arithmetic", "core"),
                   Claim("C3", "가격은 비싸다.", "entailment", "core")))


def _rev(summary, why="독자에게 중요하다."):
    return DraftCard("sid", "제목", summary, why, PRIOR.claims)


def test_old_prompt_is_frozen_copy_of_pre_s4_production():
    """R0 = main 40f9838 의 다시 쓰기 지시 그대로 — 이전 요약을 보여 주지 않고 전체를 다시 쓰게 한다."""
    p = r.old_revise_prompt(SRC, PRIOR, ("C2",), today="2026-10-18")
    assert p == ("오늘 날짜: 2026-10-18 (원문에 없는 날짜 생성 금지).\n\n"
                 "이전 초안의 일부 claim 이 독립 검증에 실패했다. **실패로 표시된 claim 만** 원문에서 다시 도출하고 "
                 "'유지' claim 은 그대로 둬라(왜 실패인지는 주어지지 않는다 — 원문만 다시 보라).\n\n"
                 "이전 claims:\n- C1 [유지]: A사는 신제품을 출시했다.\n- C2 [재도출 필요]: 신제품 점수는 72%다.\n"
                 "- C3 [유지]: 가격은 비싸다.\n\n"
                 "동일 JSON 형식으로 전체 카드를 다시 출력하라. 동결 원문:\n\n원문 본문이다.")


def test_scope_metrics_target_fix_stays_in_scope():
    m = r.scope_metrics(PRIOR, _rev("A사는 신제품을 출시했다. 신제품 점수는 70%다. 가격은 비싸다."), ("C2",))
    assert (m["in_scope"], m["kept_rate"], m["targets"], m["why_changed"]) == (True, 1.0, ["modified"], False)
    assert m["new_numbers"] == [70]


def test_scope_metrics_rewrite_outside_target_is_out_of_scope():
    m = r.scope_metrics(PRIOR, _rev("A사가 새 제품을 내놓았다. 신제품 점수는 72%다. 값이 꽤 비싸다.", why="새 why"), ("C2",))
    assert (m["in_scope"], m["kept_rate"], m["targets"], m["why_changed"]) == (False, 0.0, ["unchanged"], True)


def test_scope_metrics_target_deleted():
    m = r.scope_metrics(PRIOR, _rev("A사는 신제품을 출시했다. 가격은 비싸다."), ("C2",))
    assert (m["in_scope"], m["targets"], m["new_numbers"]) == (True, ["deleted"], [])


def test_scope_metrics_new_english_name():
    m = r.scope_metrics(PRIOR, _rev("A사는 신제품을 출시했다. 신제품 점수는 72%다. 가격은 비싸다. Nvidia 칩을 쓴다."), ("C2",))
    assert m["new_names"] == ["Nvidia"] and m["in_scope"] is False


class _Table:
    def __init__(self, items):
        self.items = items

    def scan(self, **kw):
        return {"Items": self.items}


def _item(key, gated):
    return {"cache_key": key, "card_json": json.dumps(_serialize(gated), ensure_ascii=False)}


def test_load_cases_keeps_revised_quarantined_fact_cards_with_blocked_ids():
    blocked = (CertVerdict("C1", "VERIFIED", "", "codex"), CertVerdict("C2", "BLOCKED", "", "deterministic"),
               CertVerdict("C3", "VERIFIED", "", "codex"))
    items = [_item("k1", GatedCard(PRIOR, blocked, "QUARANTINE", 2)),
             _item("k2", GatedCard(PRIOR, blocked, "QUARANTINE", 1)),                       # 다시 쓰기 전 격리 — 제외
             _item("k3", GatedCard(PRIOR, (), "PUBLISH", 2)),                               # 발행 — 제외
             _item("k4", GatedCard(DraftCard("s", "t", "x", "w", PRIOR.claims, ("C1",)), blocked, "QUARANTINE", 2))]
    cases = r.load_cases(_Table(items))
    assert [(c["cache_key"], c["failed_ids"]) for c in cases] == [("k1", ("C2",))]
