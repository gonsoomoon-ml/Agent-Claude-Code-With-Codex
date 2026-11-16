"""harness_auth — 구독 로그인 자격증명 복원(SSM → 프로세스) · 되쓰기 · 올리기. 가짜 SSM 만 쓴다(AWS·codex 호출 0)."""
from __future__ import annotations

import dataclasses
import os
import stat
import subprocess

import pytest

from briefing.core.config import load_settings
from briefing.runtime import harness_auth as ha

_TOKEN = "tok-claude-secret"
_AUTH = '{"auth_mode":"chatgpt","tokens":{"refresh_token":"r1"}}'
_AUTH2 = '{"auth_mode":"chatgpt","tokens":{"refresh_token":"r2"}}'


class _FakeSSM:
    def __init__(self, fail_put: bool = False):
        self.params = {ha.PARAM_CLAUDE_TOKEN: f" {_TOKEN}\n", ha.PARAM_CODEX_AUTH: _AUTH}
        self.gets: list[str] = []
        self.puts: list[dict] = []
        self.fail_put = fail_put

    def get_parameter(self, Name, WithDecryption):
        assert WithDecryption is True
        self.gets.append(Name)
        return {"Parameter": {"Value": self.params[Name]}}

    def put_parameter(self, **kw):
        if self.fail_put:
            raise RuntimeError("ssm down")
        self.puts.append(kw)
        self.params[kw["Name"]] = kw["Value"]


class _NoSSM:
    """어떤 호출이든 실패 — 'SSM 을 건드리지 않는다'를 증명."""

    def __getattr__(self, name):
        raise AssertionError(f"SSM 호출 금지: {name}")


def _settings(author="bedrock", certifier="bedrock", judge="bedrock"):
    return dataclasses.replace(load_settings(), author_provider=author, certifier_provider=certifier,
                               judge_provider=judge)


@pytest.fixture
def home(monkeypatch, tmp_path):
    """깨끗한 CODEX_HOME · 토큰 env 없음 · 모듈 상태 초기화."""
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex"))
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    monkeypatch.setattr(ha, "_saved_sha", "")
    return tmp_path / "codex"


def _never():
    raise AssertionError("예열 호출 금지")


def test_bedrock_only_touches_nothing(home):
    """두 경로 모두 bedrock = SSM 호출 0 · env·파일 변화 0(스위치를 모르는 배포는 영향 0)."""
    ha.prepare(_settings(), client=_NoSSM(), warm_up=_never)
    assert ha.save(_settings(), client=_NoSSM()) is False
    assert "CLAUDE_CODE_OAUTH_TOKEN" not in os.environ and not home.exists()


def test_claude_token_goes_to_process_env_only(home):
    ssm = _FakeSSM()
    ha.prepare(_settings(author="subscription"), client=ssm, warm_up=_never)
    assert os.environ["CLAUDE_CODE_OAUTH_TOKEN"] == _TOKEN        # 앞뒤 공백·개행 제거
    assert ssm.gets == [ha.PARAM_CLAUDE_TOKEN] and not home.exists()


def test_judge_subscription_alone_also_needs_the_claude_token(home):
    """보조 판정만 구독이어도 같은 Claude 토큰을 꺼낸다(요약은 Bedrock 그대로) — codex 쪽은 건드리지 않는다."""
    ssm = _FakeSSM()
    assert ha.needs_claude_token(_settings(judge="subscription")) and not ha.needs_claude_token(_settings())
    ha.prepare(_settings(judge="subscription"), client=ssm, warm_up=_never)
    assert os.environ["CLAUDE_CODE_OAUTH_TOKEN"] == _TOKEN
    assert ssm.gets == [ha.PARAM_CLAUDE_TOKEN] and not home.exists()


def test_codex_auth_is_restored_private_then_warmed_up_once(home):
    ssm, warm = _FakeSSM(), []
    ha.prepare(_settings(certifier="subscription"), client=ssm, warm_up=lambda: warm.append(1))
    auth = home / "auth.json"
    assert auth.read_text() == _AUTH and stat.S_IMODE(auth.stat().st_mode) == 0o600
    assert warm == [1] and ssm.puts == []                          # 안 바뀌었으면 되쓰지 않는다
    assert "CLAUDE_CODE_OAUTH_TOKEN" not in os.environ and ssm.gets == [ha.PARAM_CODEX_AUTH]


def test_refresh_during_warm_up_is_saved_immediately(home):
    ssm = _FakeSSM()
    ha.prepare(_settings(certifier="subscription"), client=ssm,
               warm_up=lambda: (home / "auth.json").write_text(_AUTH2))
    assert [(p["Name"], p["Value"], p["Type"], p["Overwrite"]) for p in ssm.puts] == [
        (ha.PARAM_CODEX_AUTH, _AUTH2, "SecureString", True)]


def test_save_writes_back_only_when_the_file_changed(home):
    s, ssm = _settings(certifier="subscription"), _FakeSSM()
    ha.prepare(s, client=ssm, warm_up=lambda: None)
    assert ha.save(s, client=ssm) is False
    (home / "auth.json").write_text(_AUTH2)
    assert ha.save(s, client=ssm) is True and ssm.params[ha.PARAM_CODEX_AUTH] == _AUTH2
    assert ha.save(s, client=ssm) is False and len(ssm.puts) == 1


def test_save_failure_is_not_raised_and_is_retried(home):
    s, ssm = _settings(certifier="subscription"), _FakeSSM()
    ha.prepare(s, client=ssm, warm_up=lambda: None)
    (home / "auth.json").write_text(_AUTH2)
    ssm.fail_put = True
    assert ha.save(s, client=ssm) is False                        # 예외 없음 — 발송을 막지 않는다
    ssm.fail_put = False
    assert ha.save(s, client=ssm) is True and ssm.params[ha.PARAM_CODEX_AUTH] == _AUTH2


def test_unsaved_local_refresh_is_not_overwritten_by_restore(home):
    """같은 컨테이너의 앞 run 이 갱신된 파일을 저장하지 못했다 — SSM 의 옛 파일로 덮으면 로그인이 죽는다."""
    s, ssm = _settings(certifier="subscription"), _FakeSSM()
    ha.prepare(s, client=ssm, warm_up=lambda: None)
    (home / "auth.json").write_text(_AUTH2)
    ssm.fail_put = True
    ha.save(s, client=ssm)
    ssm.fail_put = False
    ha.prepare(s, client=ssm, warm_up=lambda: None)
    assert (home / "auth.json").read_text() == _AUTH2 and ssm.params[ha.PARAM_CODEX_AUTH] == _AUTH2


def test_save_without_prepare_never_uploads(home):
    """이 프로세스가 복원한 적 없는 로그인 파일(예: 로컬 로그인)은 SSM 의 원본을 덮지 않는다 — smoke 처럼 prepare 를 건너뛴 run."""
    home.mkdir(parents=True)
    (home / "auth.json").write_text(_AUTH2)
    ssm = _FakeSSM()   # 기록하는 가짜 — save 는 예외를 삼키므로 '호출하면 실패'하는 가짜로는 못 잡는다
    assert ha.save(_settings(certifier="subscription"), client=ssm) is False
    assert ssm.puts == [] and ssm.params[ha.PARAM_CODEX_AUTH] == _AUTH


def test_unreadable_parameter_stops_the_run(home):
    ssm = _FakeSSM()
    del ssm.params[ha.PARAM_CLAUDE_TOKEN]
    with pytest.raises(KeyError):
        ha.prepare(_settings(author="subscription"), client=ssm, warm_up=_never)


@pytest.mark.parametrize("outcome", ["rc1", "timeout", "missing"])
def test_warm_up_failure_does_not_raise(monkeypatch, home, outcome):
    """예열 실패 = 경고만. run 은 계속하고 검증이 fail-closed 로 처리한다."""
    seen = []

    def fake_run(argv, **kw):
        seen.append((argv, kw["cwd"], kw["stdin"]))
        if outcome == "timeout":
            raise subprocess.TimeoutExpired(argv, 1)
        if outcome == "missing":
            raise FileNotFoundError("codex")
        return subprocess.CompletedProcess(argv, 1, stdout="", stderr="401 Unauthorized")

    monkeypatch.setattr(ha.subprocess, "run", fake_run)
    ha._warm_up_codex()
    argv, cwd, stdin = seen[0]
    assert argv[:3] == ["codex", "exec", "--skip-git-repo-check"] and stdin is subprocess.DEVNULL
    assert not os.path.exists(cwd)                                 # 깨끗한 임시 폴더에서 돌리고 지운다


class _FakeSTS:
    def __init__(self, account):
        self.account = account

    def get_caller_identity(self):
        return {"Account": self.account}


def test_push_refuses_the_wrong_account(tmp_path, capsys):
    f = tmp_path / "tok"
    f.write_text(_TOKEN)
    rc = ha.main(["push", "--expect-account", "111111111111", "--claude-token-file", str(f)],
                 sts=_FakeSTS("222222222222"), client=_NoSSM())
    assert rc == 2 and _TOKEN not in capsys.readouterr().out


def test_push_uploads_given_files_without_printing_values(tmp_path, capsys):
    tok, auth = tmp_path / "tok", tmp_path / "auth.json"
    tok.write_text(_TOKEN + "\n")
    auth.write_text(_AUTH)
    ssm = _FakeSSM()
    rc = ha.main(["push", "--expect-account", "111111111111", "--claude-token-file", str(tok),
                  "--codex-auth-file", str(auth)], sts=_FakeSTS("111111111111"), client=ssm)
    out = capsys.readouterr().out
    assert rc == 0 and (ssm.params[ha.PARAM_CLAUDE_TOKEN], ssm.params[ha.PARAM_CODEX_AUTH]) == (_TOKEN, _AUTH)
    assert all(p["Type"] == "SecureString" for p in ssm.puts)
    assert _TOKEN not in out and "r1" not in out and ha.PARAM_CODEX_AUTH in out


def test_push_uploads_only_what_was_given(tmp_path):
    tok = tmp_path / "tok"
    tok.write_text(_TOKEN)
    ssm = _FakeSSM()
    assert ha.main(["push", "--expect-account", "1", "--claude-token-file", str(tok)],
                   sts=_FakeSTS("1"), client=ssm) == 0
    assert [p["Name"] for p in ssm.puts] == [ha.PARAM_CLAUDE_TOKEN]
