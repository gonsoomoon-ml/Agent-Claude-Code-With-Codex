"""webapi.profile.validate_profile — 6 선호 필드 catalog 검증(순수)."""
from __future__ import annotations

from briefing.webapi.profile import validate_profile

KW = dict(catalog_keys=("aitimes", "openai"), lens_keys=("general", "engineer"),
          depths=("title-only", "summary", "full"), send_hours=(6, 7, 8))


def test_ok():
    assert validate_profile({"sources": ["aitimes"], "send_hour": 7}, **KW) is None


def test_sources_bounds_and_subset():
    assert validate_profile({"sources": []}, **KW)
    assert validate_profile({"sources": ["aitimes"] * 6}, **KW)
    assert validate_profile({"sources": ["ghost"]}, **KW)


def test_enums():
    assert validate_profile({"sources": ["aitimes"], "depth": "x"}, **KW)
    assert validate_profile({"sources": ["aitimes"], "lens": "x"}, **KW)
    assert validate_profile({"sources": ["aitimes"], "send_hour": 9}, **KW)
    assert validate_profile({"sources": ["aitimes"], "type": "stock"}, **KW)


def test_send_hour_nonint():
    assert validate_profile({"sources": ["aitimes"], "send_hour": "abc"}, **KW)


def test_timezone_invalid_rejected():
    err = validate_profile({"sources": ["aitimes"], "timezone": "garbage"}, **KW)
    assert err, "잘못된 timezone 은 에러를 반환해야 한다"


def test_timezone_valid_passes():
    assert validate_profile({"sources": ["aitimes"], "timezone": "Asia/Seoul"}, **KW) is None


def test_timezone_nonstring_rejected():
    assert validate_profile({"sources": ["aitimes"], "timezone": 123}, **KW)


def test_limit_param_allows_six_when_raised():
    kw = dict(KW, catalog_keys=("a", "b", "c", "d", "e", "f"))
    six = {"sources": ["a", "b", "c", "d", "e", "f"], "send_hour": 7}
    assert validate_profile(six, **kw) == "출처를 1~5개 선택하세요."  # 기본 5 유지
    assert validate_profile(six, max_sources=6, **kw) is None


def test_limit_message_reflects_actual_limit():
    kw = dict(KW, catalog_keys=tuple("abcdefg"))
    seven = {"sources": list("abcdefg"), "send_hour": 7}
    assert validate_profile(seven, max_sources=6, **kw) == "출처를 1~6개 선택하세요."
