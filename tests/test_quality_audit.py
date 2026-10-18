"""M1 운영 품질 지표(2026-10-18) — 카드 1장 지표 · 묶음 집계 · 버전 복원 · DDB 읽기(가짜 테이블).

출처: work-list M1, 10-17 공통 기준 점검(work_note 01-research/criteria-application-audit.md).
숫자·이름 검사는 S3 quality_checks 를 그대로 쓴다 — 여기서는 '같은 정의를 가져다 쓰는지'와 집계만 고정한다.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import quality_audit as qa  # noqa: E402

from briefing.core.authoring.author import Claim, DraftCard  # noqa: E402
from briefing.core.gate import GatedCard  # noqa: E402
from briefing.core.retrieval.sources import TRUNCATED_MIN_CHARS  # noqa: E402
from briefing.core.stores.cache import _serialize, fact_card_key  # noqa: E402
from briefing.core.verification.certifier import CertVerdict  # noqa: E402

EN_SRC = "Anthropic hired 120 new employees this year."
KO_SRC = "앤트로픽이 올해 직원을 새로 뽑았다고 밝혔다."


def _gated(summary="새 모델을 공개했다.", why="", claims=("새 모델을 공개했다.",), verdicts=(),
           decision="PUBLISH", sid="sid1", based_on=()):
    card = DraftCard(sid, "제목", summary, why,
                     tuple(Claim(f"C{i}", t, "entailment", "core") for i, t in enumerate(claims, 1)), based_on)
    return GatedCard(card, tuple(verdicts), decision, 1)


# ── 카드 1장 지표 ─────────────────────────────────────────────────────────────

def test_sentences_split_like_criteria_audit():
    """10-17 점검과 같은 규칙(마침표·느낌표·물음표 뒤 공백) — 46% 기준선과 같은 자로 재야 전후 비교가 된다."""
    assert qa.sentences("첫 문장이다. 둘째 문장이다! 셋째는 4.5배다.") == ["첫 문장이다.", "둘째 문장이다!", "셋째는 4.5배다."]


def test_long_sentence_thresholds():
    s150, s151, s181 = "가" * 148 + "다.", "가" * 149 + "다.", "가" * 179 + "다."
    assert (len(s150), len(s151), len(s181)) == (150, 151, 181)
    row = qa.card_row(_gated(summary=s150), EN_SRC)
    assert (row["over150"], row["over180"]) == (False, False)
    row = qa.card_row(_gated(summary=f"짧다. {s151}"), EN_SRC)
    assert (row["over150"], row["over180"], row["sentences"]) == (True, False, 2)
    assert qa.card_row(_gated(summary=s181), EN_SRC)["over180"] is True


def test_card_row_reuses_quality_checks():
    """음역·숫자 미커버는 S3 그림자 검사 결과 그대로 — 운영 로그와 정기 점검이 같은 정의."""
    g = _gated(summary="앤트로픽이 직원 120명을 새로 뽑았다.", claims=("앤트로픽이 직원을 새로 뽑았다.",))
    row = qa.card_row(g, EN_SRC)
    assert {"transliterated_name", "summary_number_not_in_claims"} <= set(row["checks"])
    assert row["lang"] == "en"
    assert qa.card_row(g, KO_SRC)["lang"] == "ko"


def test_truncation_uses_shared_threshold():
    """잘림 = author 의 절단 경고와 같은 조건(TRUNCATED_MIN_CHARS). 원문이 없으면 모름(None) — '안 잘림'이 아니다."""
    assert qa.card_row(_gated(), "a" * TRUNCATED_MIN_CHARS)["truncated"] is True
    assert qa.card_row(_gated(), "a" * (TRUNCATED_MIN_CHARS - 1))["truncated"] is False
    row = qa.card_row(_gated(), None)
    assert (row["truncated"], row["lang"]) == (None, None)


def test_verdicts_counted_by_provenance():
    """막힌·미확인 claim 을 판정 출처별로, codex 2차 판정이 풀어 준 claim(deterministic→codex VERIFIED)은 따로 센다."""
    verdicts = (CertVerdict("C1", "BLOCKED", "", "deterministic"), CertVerdict("C2", "BLOCKED", "", "codex"),
                CertVerdict("C3", "VERIFIED", "", "deterministic→codex"), CertVerdict("C4", "DEMOTED", "", "codex"),
                CertVerdict("C5", "VERIFIED", "", "deterministic"))
    row = qa.card_row(_gated(verdicts=verdicts, decision="QUARANTINE"), EN_SRC)
    assert row["blocked"] == {"deterministic": 1, "codex": 1}
    assert row["demoted"] == {"codex": 1}
    assert (row["released"], row["decision"]) == (1, "QUARANTINE")


# ── 버전 복원 · 생성 시각 ─────────────────────────────────────────────────────

def test_version_of_recovers_model_and_prompt_version():
    """캐시 키 = sha256(source_id|모델|지시 버전) — 후보 조합으로 다시 계산해 맞추면 카드의 버전을 정확히 안다."""
    key = fact_card_key("sid1", "global.anthropic.claude-sonnet-5", "represent-v3.4")
    assert qa.version_of(key, "sid1", qa.candidates()) == "sonnet-5 · v3.4"
    assert qa.version_of("0" * 64, "sid1", qa.candidates()) == qa.UNKNOWN


def test_candidates_include_extra_model():
    """U8 ② 처럼 .env 의 요약 모델이 바뀌면 그 모델도 후보에 든다(모델 id 는 사용자가 .env 로 관리)."""
    assert ("global.anthropic.claude-x-9", "represent-v3.4") in qa.candidates(extra_models=("global.anthropic.claude-x-9",))


def test_born_at_inverts_cache_ttl():
    """카드 생성 시각 = ttl − 캐시 보관 30일(put 할 때 ttl = 지금 + 30일)."""
    born = qa.born_at(1_760_000_000 + 30 * 86400)
    assert born == datetime.fromtimestamp(1_760_000_000, timezone.utc)


# ── 행 만들기 · 고르기 · 묶기 · 집계 ──────────────────────────────────────────

def _item(sid, model="global.anthropic.claude-sonnet-5", pv="represent-v3.4", ttl=1_760_000_000, **kw):
    return (fact_card_key(sid, model, pv), ttl, _gated(sid=sid, **kw))


def test_build_rows_adds_day_and_version():
    """날짜는 한국 시각 기준 — 05:00 발송 카드(UTC 로는 전날 20시)가 발송일에 묶인다."""
    ttl = int(datetime(2026, 10, 18, 20, 30, tzinfo=timezone.utc).timestamp()) + 30 * 86400
    rows = qa.build_rows([_item("s1", ttl=ttl)], {"s1": EN_SRC}, qa.candidates())
    assert (rows[0]["day"], rows[0]["version"], rows[0]["source_id"]) == ("2026-10-19", "sonnet-5 · v3.4", "s1")
    assert qa.build_rows([_item("s2")], {}, qa.candidates())[0]["truncated"] is None   # 원문 없음 → 모름


def test_select_by_kst_day_inclusive():
    rows = [{"day": d} for d in ("2026-10-17", "2026-10-18", "2026-10-19")]
    assert [r["day"] for r in qa.select(rows, since="2026-10-18", until="2026-10-18")] == ["2026-10-18"]
    assert len(qa.select(rows)) == 3


def test_group_by_day_sorted_and_by_version():
    rows = [{"day": "2026-10-19", "version": "b", "born": "2026-10-18T20:00:00+00:00"},
            {"day": "2026-10-18", "version": "a", "born": "2026-10-17T20:00:00+00:00"},
            {"day": "2026-10-19", "version": "a", "born": "2026-10-18T21:00:00+00:00"}]
    assert list(qa.group(rows, "day")) == ["2026-10-18", "2026-10-19"]
    by_version = qa.group(rows, "version")
    assert list(by_version) == ["a", "b"] and len(by_version["a"]) == 2   # 먼저 생긴 버전이 앞


def test_summarize_uses_right_denominators():
    """음역은 원문 언어별, 잘림·한정어는 원문이 있는 카드만, 인용은 한국어 원문만 분모로 둔다."""
    rows = [qa.card_row(_gated(summary="구글이 공개했다."), EN_SRC),          # en · 음역
            qa.card_row(_gated(), EN_SRC),                                   # en
            qa.card_row(_gated(summary="앤트로픽이 공개했다."), KO_SRC),        # ko · 음역
            qa.card_row(_gated(summary="구글이 공개했다."), None)]              # 원문 없음 — 언어 모름
    s = qa.summarize(rows)
    assert (s["n"], s["n_en"], s["n_ko"], s["n_with_source"]) == (4, 2, 1, 3)
    assert (s["translit_en"], s["translit_ko"]) == (1, 1)


def test_summarize_quarantine_reasons_per_card():
    """⚠ 사유는 카드 단위 — 한 카드에 출처가 둘이면 둘 다 센다. 막힌 claim 없이 격리된 옛 카드는 '막힘 없음'."""
    both = (CertVerdict("C1", "BLOCKED", "", "deterministic"), CertVerdict("C2", "BLOCKED", "", "deterministic"),
            CertVerdict("C3", "BLOCKED", "", "codex"))
    rows = [qa.card_row(_gated(verdicts=both, decision="QUARANTINE"), EN_SRC),
            qa.card_row(_gated(decision="QUARANTINE"), EN_SRC),
            qa.card_row(_gated(verdicts=(CertVerdict("C1", "VERIFIED", "", "deterministic→codex"),)), EN_SRC)]
    s = qa.summarize(rows)
    assert s["quarantine"] == 2
    assert s["quarantine_reasons"] == {"deterministic": 1, "codex": 1, qa.NO_BLOCK: 1}
    assert s["blocked_claims"] == {"deterministic": 2, "codex": 1}
    assert (s["released_claims"], s["released_cards"]) == (1, 1)


def test_format_report_has_group_rows_and_total():
    rows = qa.build_rows([_item("s1"), _item("s2", pv="represent-v3.4.1")], {"s1": EN_SRC, "s2": EN_SRC},
                         qa.candidates())
    out = qa.format_report(qa.group(rows, "version"))
    assert "sonnet-5 · v3.4 " in out and "sonnet-5 · v3.4.1" in out and "전체" in out
    assert out.count("\n| 전체 |") == 3   # 표 3개 모두 마지막 줄이 전체


# ── DDB 읽기(가짜 테이블·저장소) ──────────────────────────────────────────────

class _FakeTable:
    def __init__(self, pages):
        self.pages, self.calls = pages, []

    def scan(self, **kw):
        self.calls.append(kw)
        i = len(self.calls) - 1
        return {"Items": self.pages[i], **({"LastEvaluatedKey": {"k": i}} if i + 1 < len(self.pages) else {})}


def _ddb_item(key, ttl, gated):
    return {"cache_key": key, "ttl": ttl, "card_json": json.dumps(_serialize(gated), ensure_ascii=False)}


def test_load_fact_cards_skips_interp_and_paginates():
    """해석층 항목(based_on 있음)은 사실층 verdicts 를 복제하므로 뺀다 — 같은 기사를 두 번 세지 않게."""
    fact, interp = _gated(sid="s1"), _gated(sid="s1", based_on=("C1",))
    table = _FakeTable([[_ddb_item("k1", 100, fact)], [_ddb_item("k2", 200, interp)]])
    got = qa.load_fact_cards(table)
    assert [(k, t, g.card.source_id) for k, t, g in got] == [("k1", 100, "s1")]
    assert table.calls[1]["ExclusiveStartKey"] == {"k": 0}


def test_load_sources_skips_missing():
    class Store:
        def get_source(self, sid):
            if sid == "gone":
                raise KeyError(sid)
            return type("FS", (), {"text": f"text-{sid}"})()

    assert qa.load_sources(Store(), ["s1", "gone"]) == {"s1": "text-s1"}
