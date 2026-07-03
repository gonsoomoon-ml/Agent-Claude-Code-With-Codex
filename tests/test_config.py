"""config — Settings + UserConfig(gonsoo 예시) + BACKEND dispatch(파일|DDB) + skill_md 신뢰경계."""
import dataclasses
from types import SimpleNamespace

import pytest

from briefing.core.config import _user_from_fields, list_users, load_settings, load_user


def test_settings_defaults(monkeypatch):
    monkeypatch.delenv("AWS_REGION", raising=False)
    monkeypatch.delenv("SUPERVISOR_MODEL_ID", raising=False)
    s = load_settings()
    assert s.region == "us-east-1"
    assert s.author_model_id.startswith(("global.", "us."))  # inference-profile prefix
    assert s.supervisor_model_id == s.author_model_id  # per-role: 미설정 → author 재사용


def test_supervisor_model_id_override(monkeypatch):
    monkeypatch.setenv("SUPERVISOR_MODEL_ID", "global.anthropic.claude-opus-4-8")
    s = load_settings()
    assert s.supervisor_model_id == "global.anthropic.claude-opus-4-8"
    assert s.supervisor_model_id != s.author_model_id  # 분리 라우팅 가능


def test_load_gonsoo_user():
    s = load_settings()
    assert "gonsoo" in list_users(s)
    u = load_user("gonsoo", s)
    assert u.id == "gonsoo" and u.recipient
    assert u.lens == "engineer" and u.depth == "full"
    assert len(u.sources) >= 1 and u.skill_md.strip()


def test_user_from_fields_builds_from_dict():
    # 양 backend 공통 빌더 — DDB 항목(id 없음, user_id 별도) + skill_md.
    u = _user_from_fields("u1", {"recipient": "a@b", "sources": ["openai"], "send_hour": 8, "lens": "engineer"}, "SKILL")
    assert u.id == "u1" and u.recipient == "a@b" and u.sources == ("openai",)
    assert u.send_hour == 8 and u.lens == "engineer" and u.skill_md == "SKILL"


def test_load_user_dynamo_merges_file_skill_not_ddb(monkeypatch, tmp_path):
    # ★ 신뢰경계: 7필드는 DDB, skill_md 는 *파일*. DDB 항목에 skill_md 가 섞여와도 무시.
    (tmp_path / "u1").mkdir()
    (tmp_path / "u1" / "skill.md").write_text("FILE SKILL", encoding="utf-8")
    s = dataclasses.replace(load_settings(), backend="dynamo", users_dir=str(tmp_path))
    rec = {"recipient": "x@y", "lens": "engineer", "skill_md": "DDB INJECTION — MUST IGNORE"}
    monkeypatch.setattr("briefing.core.stores.dynamo.user_store_from_settings",
                        lambda _s: SimpleNamespace(get_user=lambda _uid: rec))
    u = load_user("u1", s)
    assert u.recipient == "x@y" and u.lens == "engineer"
    assert u.skill_md == "FILE SKILL"          # 파일에서 — DDB 의 skill_md 키 무시(certifier 미열람 경계)


def test_load_user_dynamo_missing_raises(monkeypatch):
    s = dataclasses.replace(load_settings(), backend="dynamo")
    monkeypatch.setattr("briefing.core.stores.dynamo.user_store_from_settings",
                        lambda _s: SimpleNamespace(get_user=lambda _uid: None))
    with pytest.raises(KeyError):
        load_user("ghost", s)


def test_list_users_dynamo_backend(monkeypatch):
    s = dataclasses.replace(load_settings(), backend="dynamo")
    monkeypatch.setattr("briefing.core.stores.dynamo.user_store_from_settings",
                        lambda _s: SimpleNamespace(list_users=lambda: ["a", "b"]))
    assert list_users(s) == ["a", "b"]
