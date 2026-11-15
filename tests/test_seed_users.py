"""scripts/seed_users 의 수신 주소 결정 — 순수 단위(AWS 0).

저장소가 공개라 수신 주소를 추적 파일(users/<id>/profile.yaml)에 쓰지 않는다(2026-11-14 결정 15).
주소는 gitignore 된 `.env` 의 `SEED_RECIPIENTS=<id>=<email>[,<id>=<email>]` 에만 둔다.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))


def test_parse_recipient_overrides_reads_id_email_pairs():
    from seed_users import parse_recipient_overrides

    assert parse_recipient_overrides("gonsoo=a@example.com, cw-x = b@example.com") == {
        "gonsoo": "a@example.com", "cw-x": "b@example.com"}


def test_parse_recipient_overrides_empty_setting_is_no_overrides():
    from seed_users import parse_recipient_overrides

    assert parse_recipient_overrides("") == {} and parse_recipient_overrides("  ") == {}


def test_parse_recipient_overrides_rejects_an_entry_without_an_address():
    """형식이 틀린 항목을 조용히 버리면 그 사용자는 yaml 의 낡은 주소로 시드된다 — 크게 실패시킨다."""
    from seed_users import parse_recipient_overrides

    with pytest.raises(ValueError, match="SEED_RECIPIENTS"):
        parse_recipient_overrides("gonsoo")
    with pytest.raises(ValueError, match="SEED_RECIPIENTS"):
        parse_recipient_overrides("gonsoo=")


def test_resolve_recipient_env_setting_wins_over_the_tracked_file():
    from seed_users import resolve_recipient

    assert resolve_recipient("gonsoo", "old@example.com", {"gonsoo": "new@example.com"}) == "new@example.com"


def test_resolve_recipient_falls_back_to_the_file_value():
    from seed_users import resolve_recipient

    assert resolve_recipient("cw-x", "x@example.com", {"gonsoo": "new@example.com"}) == "x@example.com"


def test_resolve_recipient_refuses_to_seed_a_user_without_any_address():
    """빈 수신자 행은 발송 단계에서야 실패한다 — 시드에서 막는다."""
    from seed_users import resolve_recipient

    with pytest.raises(ValueError, match="gonsoo"):
        resolve_recipient("gonsoo", "", {})
