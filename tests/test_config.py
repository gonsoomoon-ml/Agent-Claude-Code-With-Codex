"""config — Settings + UserConfig(gonsoo 예시)."""
from briefing.shared.config import list_users, load_settings, load_user


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
