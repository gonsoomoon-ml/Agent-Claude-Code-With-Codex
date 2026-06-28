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
