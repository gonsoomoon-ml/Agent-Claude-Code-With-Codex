"""업그레이드 비교 실험 — 코드 지표 테스트(문장·150자·유보·이름 표기·숫자 커버·인용·F2 표기)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from upgrade_eval import metrics  # noqa: E402


def test_split_sentences_korean_and_edge_cases():
    s = 'A사는 3.5% 늘었다고 밝혔다. U.S. 기준이다. 그는 "준비됐다."고 했다. 그는 "끝났다”. 마지막'
    assert metrics.split_sentences(s) == [
        "A사는 3.5% 늘었다고 밝혔다.", "U.S. 기준이다.", '그는 "준비됐다."고 했다.', '그는 "끝났다”.', "마지막"]


def test_long_sentence_ratio():
    assert metrics.long_sentence_ratio(["가" * 151, "나" * 150]) == 0.5
    assert metrics.long_sentence_ratio([]) == 0.0


def test_numbers_cover_and_why():
    assert metrics.uncovered_numbers("가격은 74.99달러다.", ["가격은 74.99달러다."]) == []
    assert metrics.uncovered_numbers("31,200명이 참여했다.", ["참여자가 많았다."]) == [31200.0]
    assert metrics.why_new_numbers("6배 빠르다", "속도가 늘었다.", ["속도가 늘었다."]) == [6.0]
    assert metrics.uncovered_names("Anthropic이 Claude Sonnet을 냈다.", ["Anthropic이 새 모델을 냈다."]) == ["Claude", "Sonnet"]


def test_transliteration():
    assert metrics.transliterated_names("앤트로픽과 오픈AI, 구글이") == ["앤트로픽", "오픈AI", "구글"]
    assert metrics.transliterated_names("메타데이터를 쓰는 Anthropic") == []


def test_quote_mismatch_same_language_only():
    src = '그는 "준비됐다"고 말했다. 이어 다른 말을 했다.'
    assert metrics.quote_mismatches('그는 "준비됐다"고 했다.', src) == []
    assert metrics.quote_mismatches('그는 "다 준비됐다"고 했다.', src) == ["다 준비됐다"]
    assert metrics.quote_mismatches('그는 "우리는 준비됐다"고 했다.', 'He said "we are ready".') == []


def test_known_f2_patterns():
    assert metrics.is_known_f2_block("입력 토큰 100만 개당 2달러이다.", "원문에 없는 수치: 수량=[1000000.0]")
    assert metrics.is_known_f2_block("2분기부터 함께 일해왔다.", "원문에 없는 수치: 수량=[2.0]")
    assert metrics.is_known_f2_block("121개국 중 2위다.", "원문에 없는 수치: 수량=[2.0]")
    assert metrics.is_known_f2_block("기부액의 3배다.", "원문에 없는 수치: 수량=[3.0]")
    assert metrics.is_known_f2_block("약 40년간의 연구다.", "원문에 없는 수치: 수량=[40.0]")
    assert metrics.is_known_f2_block("건당 약 1만2000달러를 받았다.", "원문에 없는 수치: 수량=[2000.0, 10000.0]")
    assert not metrics.is_known_f2_block("매출은 46억달러다.", "원문에 없는 수치: 수량=[46.0]")
    assert not metrics.is_known_f2_block("기부액의 3배다.", "excerpt contradicts claim")


def test_hedge_and_title_repeat():
    assert metrics.has_hedge("확인되지 않았다") and not metrics.has_hedge("출시했다")
    assert metrics.repeats_title("앤트로픽, 새 모델 공개", "앤트로픽, 새 모델 공개했다.")
    assert not metrics.repeats_title("Anthropic releases Claude", "Anthropic이 Claude 새 버전을 공개했다.")


def test_deepest_position():
    src = "Alpha 로 시작하는 문장. " + "가" * 60 + " Omega 로 끝난다."
    assert metrics.deepest_position(src, "Omega 를 담았다.") > 0.5
    assert metrics.deepest_position(src, "고유명사가 없는 요약") is None
