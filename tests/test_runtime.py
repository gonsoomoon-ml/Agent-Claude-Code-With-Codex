"""runtime 배포 어댑터(②)의 *순수·테스트가능* 단위 — AWS·CLI·네트워크 0.

검증 대상(결정론):
  - deploy_runtime.runtime_env  : 컨테이너 주입 env (DEBUG on/off forward 포함)
  - deploy_runtime._upsert_env_lines : 루트 .env writeback (idempotent — 재배포해도 중복 0)
  - invoke_runtime.parse_sse_event : SSE `data: {...}` 파싱(노이즈 견고)
  - _smoke.smoke_fns/smoke_users   : smoke invoke 가 *결정론으로 PUBLISH* (배포 plumbing 검증의 신뢰성)

AWS 호출(configure/launch/teardown)은 실 배포(done-when)로 검증 — 여기선 순수 로직만.
"""
from __future__ import annotations

from briefing.shared.config import Settings


def _settings(tmp_path, *, users_dir: str | None = None) -> Settings:
    return Settings(
        region="us-east-1",
        author_model_id="global.anthropic.claude-sonnet-4-6",
        supervisor_model_id="global.anthropic.claude-sonnet-4-6",
        ses_sender="briefing@example.com",
        source_store_path=str(tmp_path / "store"),
        users_dir=users_dir or str(tmp_path / "nousers"),
    )


# ───────────────────────── runtime_env (DEBUG on/off forward) ─────────────────────────

def test_runtime_env_includes_container_core_keys(tmp_path, monkeypatch):
    from briefing.runtime.deploy_runtime import runtime_env

    monkeypatch.delenv("DEBUG", raising=False)
    env = runtime_env(_settings(tmp_path))
    # 컨테이너는 .env 를 안 읽음 → launch(env_vars=...) 로 주입되는 핵심 키들
    assert env["AWS_REGION"] == "us-east-1"
    assert env["AUTHOR_MODEL_ID"] == "global.anthropic.claude-sonnet-4-6"
    assert env["SES_SENDER"] == "briefing@example.com"
    assert env["CLAUDE_CODE_USE_BEDROCK"] == "1"   # author=claude -p 를 Bedrock 로 라우팅
    assert env["ENABLE_TOOL_SEARCH"] == "false"


def test_runtime_env_forwards_debug_on(tmp_path, monkeypatch):
    from briefing.runtime.deploy_runtime import runtime_env

    monkeypatch.setenv("DEBUG", "1")
    assert runtime_env(_settings(tmp_path))["DEBUG"] == "1"   # 호스트 DEBUG → 컨테이너 is_debug() on


def test_runtime_env_debug_off_forwards_empty(tmp_path, monkeypatch):
    from briefing.runtime.deploy_runtime import runtime_env

    monkeypatch.delenv("DEBUG", raising=False)
    # 미설정 시 빈 문자열 forward → 컨테이너 is_debug()==False (zero overhead)
    assert runtime_env(_settings(tmp_path))["DEBUG"] == ""


def test_runtime_env_overrides_store_path_for_container():
    """컨테이너는 비-root 유저(uid 1000) → /app 하위 상대경로(./.data) 쓰기 불가(Errno 13).

    실 invoke 가 PermissionError 로 잡아낸 회귀 — host 경로와 무관하게 *writable 절대경로* 주입.
    """
    from briefing.runtime.deploy_runtime import CONTAINER_STORE_PATH, runtime_env

    s = Settings(
        region="us-east-1", author_model_id="m", supervisor_model_id="m",
        ses_sender="x@y.com", source_store_path="./.data/source_store", users_dir="./users",
    )
    assert runtime_env(s)["SOURCE_STORE_PATH"] == CONTAINER_STORE_PATH
    assert CONTAINER_STORE_PATH.startswith("/tmp/")   # ephemeral writable (v1; ③ DB 백킹 후속)


# ───────────────────────── .env writeback (idempotent) ─────────────────────────

def test_upsert_env_lines_replaces_value_without_duplicating(tmp_path):
    from briefing.runtime.deploy_runtime import _upsert_env_lines

    base = "AWS_REGION=us-east-1\nSES_SENDER=x@y.com\n"
    once = _upsert_env_lines(base, {"BRIEFING_RUNTIME_ARN": "arn:1"}, section="# Briefing Runtime")
    twice = _upsert_env_lines(once, {"BRIEFING_RUNTIME_ARN": "arn:2"}, section="# Briefing Runtime")

    assert twice.count("BRIEFING_RUNTIME_ARN=") == 1     # 재배포해도 중복 라인 0
    assert "BRIEFING_RUNTIME_ARN=arn:2" in twice
    assert "arn:1" not in twice
    assert twice.count("# Briefing Runtime") == 1        # 섹션 마커도 중복 안 됨


def test_upsert_env_lines_preserves_unrelated_keys(tmp_path):
    from briefing.runtime.deploy_runtime import _upsert_env_lines

    base = "AWS_REGION=us-east-1\nSES_SENDER=x@y.com\n"
    out = _upsert_env_lines(base, {"BRIEFING_RUNTIME_ID": "rid-1"}, section="# Briefing Runtime")
    assert "AWS_REGION=us-east-1" in out and "SES_SENDER=x@y.com" in out


# ───────────────────────── SSE 파싱 ─────────────────────────

def test_parse_sse_event_parses_data_prefixed_json():
    from briefing.runtime.invoke_runtime import parse_sse_event

    ev = parse_sse_event(b'data: {"type": "user", "user": "gonsoo", "published": 1}')
    assert ev is not None and ev["user"] == "gonsoo" and ev["published"] == 1


def test_parse_sse_event_ignores_blank_and_nonjson():
    from briefing.runtime.invoke_runtime import parse_sse_event

    assert parse_sse_event(b"") is None
    assert parse_sse_event(b"\n") is None
    assert parse_sse_event(b"not json at all") is None


# ───────────────────────── smoke = 결정론 PUBLISH ─────────────────────────

def test_smoke_users_synthesizes_when_no_real_users(tmp_path):
    from briefing.runtime._smoke import smoke_users

    users = smoke_users(_settings(tmp_path))   # users_dir 없음 → 합성 사용자 1명
    assert len(users) == 1
    assert users[0].recipient                  # 비지 않은 수신자(렌더/발송 경로 통과용)


def test_smoke_invoke_publishes_deterministically(tmp_path):
    from briefing.runtime._smoke import smoke_fns, smoke_users
    from briefing.shared.pipeline import run_briefing
    from briefing.shared.source_store import SourceStore

    settings = _settings(tmp_path)
    store = SourceStore(settings.source_store_path)
    users = smoke_users(settings)

    out = run_briefing(settings, store, users, window_hours=24, **smoke_fns())

    assert out, "smoke invoke 가 사용자별 브리핑을 산출해야 함(per-user SSE 의 원천)"
    assert out[0].published >= 1               # fake 검증 = 전부 VERIFIED → PUBLISH
    assert out[0].quarantined == 0
