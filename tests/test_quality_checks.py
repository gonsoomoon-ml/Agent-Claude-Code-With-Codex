"""S3 그림자 검사(2026-10-18) — 로그만 남기고 판정·메일은 안 바꾼다. 검사마다 '걸림'과 '안 걸림'을 쌍으로 고정한다.

출처: 요약 품질 공통 기준 점검(work_note 01-research/criteria-application-audit.md)과 work-list S3.
"""
from types import SimpleNamespace

from briefing.core.authoring.author import Claim, DraftCard
from briefing.core.quality_checks import shadow_checks


def _card(summary="", why="", claims=()):
    return DraftCard("sid", "헤드라인", summary, why, tuple(Claim(f"C{i}", t, "entailment", "core")
                                                         for i, t in enumerate(claims, 1)))


def _checks(card, source):
    return {f.check: f.detail for f in shadow_checks(card, source)}


# ── 1. 요약의 숫자·이름이 claim 에 있는지 ───────────────────────────────────────

def test_summary_number_not_in_claims():
    card = _card(summary="매출은 70억 달러였고 직원은 120명이다.", claims=("매출은 70억 달러였다.",))
    assert "120" in _checks(card, "Revenue was $7 billion with 120 employees.")["summary_number_not_in_claims"]


def test_summary_numbers_all_covered():
    card = _card(summary="매출은 70억 달러였다.", claims=("매출은 70억 달러였다.",))
    assert "summary_number_not_in_claims" not in _checks(card, "Revenue was $7 billion.")


def test_summary_name_not_in_claims():
    card = _card(summary="Anthropic 이 Claude Sonnet 5.5 를 냈다.", claims=("Claude Sonnet 5.5 가 나왔다.",))
    assert "Anthropic" in _checks(card, "Anthropic released Claude Sonnet 5.5.")["summary_name_not_in_claims"]


# ── 2. 수치 한정어: 원문 'up to 2x' 를 요약이 '2배'로(한정어를 떨어뜨림) ─────────────────

def test_qualifier_dropped_from_bounded_source_number():
    src = "The new kernel boosts throughput by up to 2x on long sequences."
    card = _card(summary="새 커널은 긴 시퀀스에서 처리량을 2배 높인다.", claims=("처리량을 2배 높인다.",))
    assert "2" in _checks(card, src)["qualifier_dropped"]


def test_qualifier_kept_is_fine():
    src = "The new kernel boosts throughput by up to 2x on long sequences."
    card = _card(summary="새 커널은 긴 시퀀스에서 처리량을 최대 2배 높인다.", claims=("처리량을 최대 2배 높인다.",))
    assert "qualifier_dropped" not in _checks(card, src)


def test_bare_source_number_is_fine():
    """원문에 한정어 없는 같은 숫자도 있으면 떨어뜨렸다고 보지 않는다."""
    src = "It is up to 2x faster in tests. In production it was 2x faster."
    card = _card(summary="운영에서 2배 빨랐다.", claims=("운영에서 2배 빨랐다.",))
    assert "qualifier_dropped" not in _checks(card, src)


def test_next_number_does_not_leak_into_previous_occurrence():
    """30일 기준값 점검에서 나온 오탐: '기존 3개에서 최대 20개' 의 '3' 자리가 뒤의 20 까지 읽어 20 을 한정어 없는 숫자로 셌다."""
    src = "참조 이미지 입력 한도를 최대 20개까지 확대했다."
    card = _card(summary="입력 한도를 기존 3개에서 최대 20개로 늘렸다.", claims=("입력 한도를 최대 20개로 늘렸다.",))
    assert "qualifier_dropped" not in _checks(card, src)


def test_korean_qualifiers_inai_and_seon():
    """'800ms 이내'·'25달러 선' 도 한정어다(기준값 점검에서 나온 오탐)."""
    src = "The first token now arrives in under 800 ms, while the typical user spends around $25."
    card = _card(summary="첫 토큰이 800ms 이내에 오고, 일반 사용자는 월 25달러 선을 쓴다.", claims=("800ms 이내, 25달러 선.",))
    assert "qualifier_dropped" not in _checks(card, src)


# ── 3. 따옴표 인용은 원문 그대로(한국어 원문만 — 영어 원문은 번역이라 제외) ───────────────


def test_apostrophe_is_not_a_quote():
    """기준값 점검에서 나온 오탐: 'Claude's' 의 아포스트로피를 여는 따옴표로 읽어 다음 따옴표까지를 인용으로 잡았다."""
    src = "앤트로픽은 새 기능을 소개했다. 이는 2년간의 실험 결과로 ‘시뮬레이션’을 거쳤다."
    card = _card(summary="Claude's 새 기능을 소개했다. 이는 2년간의 실험 결과로 ‘시뮬레이션’을 거쳤다.", claims=("새 기능을 소개했다.",))
    assert "quote_not_verbatim" not in _checks(card, src)

def test_korean_quote_not_verbatim():
    src = "김 대표는 \"AI 는 결국 도구일 뿐\"이라고 말했다."
    card = _card(summary="김 대표는 \"AI 는 도구에 불과하다\"고 말했다.", claims=("김 대표가 말했다.",))
    assert "AI 는 도구에 불과하다" in _checks(card, src)["quote_not_verbatim"]


def test_korean_quote_verbatim_is_fine():
    src = "김 대표는 \"AI 는 결국 도구일 뿐\"이라고 말했다."
    card = _card(summary="김 대표는 \"AI 는 결국 도구일 뿐\"이라고 말했다.", claims=("김 대표가 말했다.",))
    assert "quote_not_verbatim" not in _checks(card, src)


def test_english_source_quotes_are_skipped():
    src = 'The CEO said "AI is just a tool."'
    card = _card(summary="CEO 는 \"AI 는 도구일 뿐\"이라고 말했다.", claims=("CEO 가 말했다.",))
    assert "quote_not_verbatim" not in _checks(card, src)


# ── 4. 이름 표기: 영문 이름이 확실한 회사·모델을 한글 음역으로(D4: 원어로 통일) ──────────────

def test_transliterated_name():
    card = _card(summary="앤트로픽은 새 모델을 냈고 메타의 반응도 나왔다.", claims=("새 모델을 냈다.",))
    detail = _checks(card, "Anthropic released a new model.")["transliterated_name"]
    assert "앤트로픽" in detail and "메타" in detail


def test_meta_inside_another_word_is_not_a_name():
    card = _card(summary="메타데이터를 정리했다.", claims=("메타데이터를 정리했다.",))
    assert "transliterated_name" not in _checks(card, "They cleaned up metadata.")


# ── 5. 사실층 '왜 중요한가'의 새 숫자 ─────────────────────────────────────────────

def test_why_new_number():
    card = _card(summary="매출은 70억 달러였다.", why="경쟁사보다 3배 빠른 성장이다.", claims=("매출은 70억 달러였다.",))
    assert "3" in _checks(card, "Revenue was $7 billion.")["why_new_number"]


def test_why_without_new_numbers_is_fine():
    card = _card(summary="매출은 70억 달러였다.", why="70억 달러 규모는 업계 상위권이다.", claims=("매출은 70억 달러였다.",))
    assert "why_new_number" not in _checks(card, "Revenue was $7 billion.")


# ── 파이프라인 배선: 로그만 남기고 판정·메일은 그대로 ─────────────────────────────

def test_pipeline_logs_shadow_findings_without_changing_output(tmp_path, capsys):
    from briefing.core.pipeline import run_briefing
    from briefing.core.retrieval.sources import FetchedArticle
    from briefing.core.stores.source_store import SourceStore
    from briefing.core.verification.certifier import CertVerdict

    def fetch(source, _w):
        return [FetchedArticle(source.key, "https://example.com/a", "T", "Revenue was $7 billion.", "2026-06-27T00:00:00Z")]

    user = SimpleNamespace(id="u", recipient="u@x.com", sources=["aws-ml"], depth="full", lens="", skill_md="")
    out = run_briefing(
        SimpleNamespace(), SourceStore(str(tmp_path / "s")), [user], window_hours=0, fetch_article_fn=fetch,
        draft_fn=lambda source, *_a: DraftCard(source.source_id, "H", "매출은 70억 달러였고 직원은 120명이다.", "W",
                                               (Claim("C1", "매출은 70억 달러였다.", "entailment", "core"),)),
        verify_fn=lambda c: (CertVerdict("C1", "VERIFIED", "ev"),),
    )
    err = capsys.readouterr().err
    assert "quality shadow" in err and "summary_number_not_in_claims" in err
    assert "quality shadow 집계" in err
    assert out[0].published == 1                                 # 판정은 그대로
    assert "120명" in out[0].email                                # 메일 내용도 그대로(그림자 = 로그만)
