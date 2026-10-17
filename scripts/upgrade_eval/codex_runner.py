"""실험용 codex(검증 AI) 러너 — 운영 `_run_codex` 와 같은 격리에 `--json` 만 더해 토큰 사용량을 기록한다.

운영 파서(`_last_json_object`)는 `--json` 의 이벤트 스트림에서 마지막 *이벤트*를 집어 깨지므로,
여기서는 이벤트를 읽어 최종 답(agent_message)과 usage(turn.completed)를 분리한다.
검증 프롬프트는 운영 `_build_codex_prompt(envelope)` 그대로 — envelope 4필드 외 아무것도 주지 않는다.
판정은 fail-closed: 실행·파싱 실패는 절대 VERIFIED 가 아니라 DEMOTED(codex-error)다.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from briefing.core.verification.certifier import (
    CertVerdict,
    Envelope,
    _build_codex_prompt,
    _last_json_object,
)

from .common import EXP_ROOT

_VERDICTS = ("VERIFIED", "DEMOTED", "BLOCKED")


@dataclass(frozen=True)
class CodexModel:
    name: str
    codex_version: str
    model: str

    @property
    def codex_bin(self) -> Path:
        return EXP_ROOT / "bin" / f"codex-{self.codex_version}" / "node_modules" / ".bin" / "codex"

    @property
    def codex_home(self) -> Path:
        return EXP_ROOT / "codex-home" / self.name


VERIFIERS: dict[str, CodexModel] = {
    "gpt-6-astra": CodexModel("gpt-6-astra", "0.163.0", "openai.gpt-6-astra"),
    "gpt-6-sol": CodexModel("gpt-6-sol", "0.163.0", "openai.gpt-6-sol"),
    "gpt-6.1-sol": CodexModel("gpt-6.1-sol", "0.163.0", "openai.gpt-6.1-sol"),
    "gpt-6-luna": CodexModel("gpt-6-luna", "0.163.0", "openai.gpt-6-luna"),
    "gpt-5.5": CodexModel("gpt-5.5", "0.142.2", "openai.gpt-5.5"),
}


@dataclass
class CodexRun:
    final_text: str | None
    usage: dict
    duration_ms: int
    returncode: int | None
    error: str | None


def parse_codex_jsonl(stdout: str) -> tuple[str | None, dict]:
    """`codex exec --json` 출력 → (마지막 agent_message 텍스트, 마지막 turn.completed usage). JSON 아닌 줄은 무시."""
    final, usage = None, {}
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        item = event.get("item")
        if event.get("type") == "item.completed" and isinstance(item, dict) and item.get("type") == "agent_message":
            final = item.get("text")
        elif event.get("type") == "turn.completed":
            usage = event.get("usage") or {}
    return final, usage


def build_codex_env(model: CodexModel, *, home_dir: Path) -> dict[str, str]:
    """허용 목록 env — 세션의 다른 변수(API 키·Claude Code 플래그)를 상속하지 않는다."""
    node = shutil.which("node")
    path = [str(model.codex_bin.parent)] + ([str(Path(node).parent)] if node else []) + ["/usr/local/bin", "/usr/bin", "/bin"]
    return {
        "PATH": ":".join(path),
        "HOME": str(home_dir),
        "LANG": "C.UTF-8",
        "CODEX_HOME": str(model.codex_home),
        "AWS_REGION": "us-east-1",
        "AWS_SHARED_CREDENTIALS_FILE": str(Path.home() / ".aws" / "credentials"),
        "AWS_CONFIG_FILE": str(Path.home() / ".aws" / "config"),
    }


def run_codex_json(prompt: str, model: CodexModel, *, timeout_s: int = 120) -> CodexRun:
    """빈 cwd·빈 HOME·stdin 닫음으로 `codex exec --skip-git-repo-check --json` 1회 실행."""
    home = Path(tempfile.mkdtemp(prefix="ue-codex-home-"))
    cwd = Path(tempfile.mkdtemp(prefix="ue-codex-cwd-"))
    t0 = time.monotonic()
    try:
        proc = subprocess.run(
            [str(model.codex_bin), "exec", "--skip-git-repo-check", "--json", prompt],
            cwd=cwd, env=build_codex_env(model, home_dir=home), capture_output=True, text=True,
            timeout=timeout_s, stdin=subprocess.DEVNULL, check=False,
        )
    except subprocess.TimeoutExpired:
        return CodexRun(None, {}, int((time.monotonic() - t0) * 1000), None, "timeout")
    finally:
        shutil.rmtree(home, ignore_errors=True)
        shutil.rmtree(cwd, ignore_errors=True)
    duration = int((time.monotonic() - t0) * 1000)
    final, usage = parse_codex_jsonl(proc.stdout)
    if proc.returncode != 0:
        return CodexRun(final, usage, duration, proc.returncode, f"rc={proc.returncode}: {proc.stderr.strip()[:200]}")
    return CodexRun(final, usage, duration, proc.returncode, None)


def certify_entailment_json(
    claim_id: str, envelope: Envelope, model: CodexModel, *, timeout_s: int = 120, runner=run_codex_json
) -> tuple[CertVerdict, CodexRun]:
    """함의 claim 1건 검증 — 운영 프롬프트 그대로, 판정은 fail-closed."""
    run = runner(_build_codex_prompt(envelope), model, timeout_s=timeout_s)
    if run.error or not run.final_text:
        return CertVerdict(claim_id, "DEMOTED", f"검증기 실행 실패(보수적 미확인): {run.error or '빈 응답'}", "codex-error"), run
    obj = _last_json_object(run.final_text)
    verdict = (obj or {}).get("verdict")
    if verdict not in _VERDICTS:
        return CertVerdict(claim_id, "DEMOTED", f"검증기 출력 파싱 불가(보수적 미확인): {run.final_text[:80]!r}", "codex-error"), run
    return CertVerdict(claim_id, verdict, str(obj.get("evidence", "")), f"codex:{model.name}"), run
