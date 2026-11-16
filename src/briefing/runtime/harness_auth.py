"""harness_auth — 구독 로그인(AUTHOR_PROVIDER/JUDGE_PROVIDER/CERTIFIER_PROVIDER=subscription)의 자격증명을 run 마다 꺼내고 되돌려 놓는다.

이미지에는 비밀값을 굽지 않는다 → SSM Parameter Store(SecureString)에 두고 run 시작 때 복원한다.
- Claude: 1년짜리 토큰 → 이 프로세스의 env `CLAUDE_CODE_OAUTH_TOKEN` 에만 둔다(파일 0). `author_env` 가 claude 로 넘긴다.
  요약(AUTHOR_PROVIDER)과 보조 판정(JUDGE_PROVIDER)이 같은 토큰을 쓴다 — 둘 중 하나라도 구독이면 꺼낸다.
- Codex : ChatGPT 로그인 파일 `$CODEX_HOME/auth.json`. codex 가 토큰을 갱신하면 이 파일을 고쳐 쓰고 옛 refresh token 은
  죽는다 → 바뀐 파일을 SSM 에 되써야 다음 run 이 로그인된 채로 시작한다(`save`). 갱신이 run 초반에 일어나도록
  예열 호출을 한 번 하고 바로 저장한다 — run 이 중간에 죽어도 갱신된 토큰을 잃지 않는다.
세 경로 모두 bedrock 이면 아무 일도 하지 않는다(SSM 호출 0).
올리기(로그인 뒤 1회): python -m briefing.runtime.harness_auth push --expect-account <id>
                        [--claude-token-file F] [--codex-auth-file F]
"""
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from ..core import _debug
from ..core.config import Settings, load_settings

PARAM_CLAUDE_TOKEN = "/briefing/harness/claude-oauth-token"
PARAM_CODEX_AUTH = "/briefing/harness/codex-auth-json"
_WARM_UP_TIMEOUT_S = 120
_saved_sha = ""     # SSM 과 같다고 마지막으로 확인한 auth.json 의 해시(이 프로세스 안에서만)


def _ssm(settings: Settings):
    import boto3
    return boto3.client("ssm", region_name=settings.region)


def _get(client, name: str) -> str:
    return client.get_parameter(Name=name, WithDecryption=True)["Parameter"]["Value"]


def _put(client, name: str, value: str) -> None:
    # Intelligent-Tiering = 4KB 이하면 표준(무료), 넘으면 고급(월 $0.05) — auth.json 이 4KB 언저리라 넘어도 저장이 실패하지 않게
    client.put_parameter(Name=name, Value=value, Type="SecureString", Overwrite=True, Tier="Intelligent-Tiering")


def codex_auth_path() -> Path:
    return Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex") / "auth.json"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else ""


def _write_private(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w", encoding="utf-8") as f:
        f.write(text)
    os.chmod(path, 0o600)


def _warm_up_codex() -> None:
    """codex 를 한 번 부른다 — 토큰 갱신이 필요하면 여기서 일어난다. 실패해도 run 은 계속(검증은 fail-closed)."""
    clean = tempfile.mkdtemp(prefix="codex-warm-")
    try:
        proc = subprocess.run(
            ["codex", "exec", "--skip-git-repo-check", "Reply with exactly: OK"],
            cwd=clean, capture_output=True, text=True, timeout=_WARM_UP_TIMEOUT_S,
            env={**os.environ}, stdin=subprocess.DEVNULL, check=False)
        if proc.returncode != 0:
            _debug.warn("harness_auth", f"codex 예열 실패 rc={proc.returncode}: {proc.stderr.strip()[-200:]}")
    except (OSError, subprocess.TimeoutExpired) as e:
        _debug.warn("harness_auth", f"codex 예열 실패 {type(e).__name__}: {e}")
    finally:
        shutil.rmtree(clean, ignore_errors=True)


def needs_claude_token(settings: Settings) -> bool:
    """Claude 구독 토큰이 필요한가 — 요약 또는 보조 판정이 구독 경로일 때(둘이 같은 토큰을 쓴다)."""
    return "subscription" in (settings.author_provider, settings.judge_provider)


def prepare(settings: Settings, *, client=None, warm_up=_warm_up_codex) -> None:
    """run 시작 때 1회. SSM 을 못 읽으면 예외 — 로그인 없이 run 을 시작하지 않는다."""
    global _saved_sha
    use_claude = needs_claude_token(settings)
    use_codex = settings.certifier_provider == "subscription"
    if not (use_claude or use_codex):
        return
    client = client or _ssm(settings)
    if use_claude:
        os.environ["CLAUDE_CODE_OAUTH_TOKEN"] = _get(client, PARAM_CLAUDE_TOKEN).strip()
    if use_codex:
        path = codex_auth_path()
        if _saved_sha and _sha(path) not in ("", _saved_sha):
            # 같은 컨테이너의 앞 run 이 갱신된 파일을 저장하지 못했다 → SSM 의 옛 파일로 덮으면 로그인이 죽는다
            _debug.warn("harness_auth", "저장 안 된 codex 로그인 파일이 있다 — 복원을 건너뛰고 이 파일을 저장한다")
        else:
            _write_private(path, _get(client, PARAM_CODEX_AUTH))
            _saved_sha = _sha(path)
        warm_up()
        save(settings, client=client)


def save(settings: Settings, *, client=None) -> bool:
    """codex 로그인 파일이 바뀌었으면 SSM 에 되쓴다(예열 직후 · run 끝). 저장했으면 True. 실패는 경고만 — 발송을 막지 않는다."""
    global _saved_sha
    if settings.certifier_provider != "subscription":
        return False
    path = codex_auth_path()
    sha = _sha(path)
    if not _saved_sha or not sha or sha == _saved_sha:   # 복원한 적 없는 파일은 올리지 않는다(prepare 를 거친 것만)
        return False
    try:
        _put(client or _ssm(settings), PARAM_CODEX_AUTH, path.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001 — 저장 실패가 발송을 막으면 안 된다. 다음 save 가 다시 시도한다
        _debug.warn("harness_auth",
                    f"★ codex 로그인 파일 저장 실패 — 다음 run 에 재로그인이 필요할 수 있다: {type(e).__name__}: {e}")
        return False
    _saved_sha = sha
    _debug.warn("harness_auth", "codex 로그인 파일이 갱신돼 SSM 에 저장했다")
    return True


def main(argv: list[str] | None = None, *, sts=None, client=None) -> int:
    p = argparse.ArgumentParser(description="로컬 로그인 자격증명을 SSM 에 올린다(값은 출력하지 않는다).")
    push = p.add_subparsers(dest="cmd", required=True).add_parser("push")
    push.add_argument("--expect-account", required=True, help="올릴 계정 id — 호출 계정과 다르면 중단")
    push.add_argument("--claude-token-file")
    push.add_argument("--codex-auth-file")
    args = p.parse_args(argv)
    settings = load_settings()
    if sts is None:
        import boto3
        sts = boto3.client("sts", region_name=settings.region)
    account = sts.get_caller_identity()["Account"]
    if account != args.expect_account:
        print(f"중단 — 호출 계정 {account} 이 --expect-account {args.expect_account} 와 다르다")
        return 2
    client = client or _ssm(settings)
    for name, file in ((PARAM_CLAUDE_TOKEN, args.claude_token_file), (PARAM_CODEX_AUTH, args.codex_auth_file)):
        if file:
            value = Path(file).expanduser().read_text(encoding="utf-8").strip()
            _put(client, name, value)
            print(f"올림: {name} · {len(value.encode())} bytes · account={account}")
    if args.codex_auth_file:
        print("★ 이제 SSM 의 사본이 원본이다 — 올린 로컬 codex 로그인 파일로 codex 를 다시 돌리지 않는다(토큰이 갱신되면 SSM 쪽이 죽는다)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
