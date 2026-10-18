"""실험용 요약 AI(author) 러너 — 운영 `_run_author` 와 같은 명령을, 운영 컨테이너와 같은 조건에서 실행한다.

운영 컨테이너에는 사용자 설정·플러그인이 없다. 호스트에서 그대로 돌리면 사용자 플러그인 훅·도구가 실려
조건이 달라지므로(2026-10-16 프로브: 입력 70,289 토큰), 호출마다 빈 HOME(+컨테이너와 같은 `.claude.json`)과
허용 목록 env 만 쓴다. 조건(Arm)은 모델·CLI 버전·effort 만 바꾸고, 지시(프롬프트)는 운영 함수로 그대로 만든다.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from briefing.core.authoring.author import (
    DraftCard,
    _build_revise_prompt,
    _parse_card_json,
    _to_draft_card,
    build_system_prompt,
    build_user_prompt,
)
from briefing.core.lenses import resolve_lens

from .common import EXP_ROOT

# Task 1 프로브 A: env(CLAUDE_CODE_EFFORT_LEVEL)가 -p 에서 적용됨(low→thinking 0, high→380) — 운영 코드 무변경.
EFFORT_VIA = "env"
# 요약 지시의 '오늘 날짜' — 조건마다 실행일이 달라지면 지시가 달라져 비교가 흔들린다. 모든 실행에 같은 날짜를 준다.
EVAL_TODAY = "2026-10-17"

_CLAUDE_CONFIG = Path(__file__).resolve().parents[2] / "src" / "briefing" / "runtime" / "container" / "claude_config.json"


# S1 초안 A — 리서치(01-research/author-summarization-research.md §5 초안 A) 문구 그대로.
_S1_DRAFT_A = (Path(__file__).with_name("s1_draft_a.md")).read_text(encoding="utf-8")


@dataclass(frozen=True)
class Arm:
    key: str
    model_id: str
    cli_version: str
    effort: str | None
    # 지시문 추가 규칙(S1) — '논조·귀속 보존' 절 바로 다음에 넣는다. 빈 값 = 운영 지시문 그대로. rules_name 은 실행 기록용 이름.
    rules_patch: str = ""
    rules_name: str = ""


ARMS: dict[str, Arm] = {
    "A0": Arm("A0", "global.anthropic.claude-sonnet-5", "2.1.195", None),
    "A1": Arm("A1", "global.anthropic.claude-sonnet-5", "2.1.301", None),
    "A2": Arm("A2", "global.anthropic.claude-sonnet-5-5", "2.1.301", "medium"),
    "A3": Arm("A3", "global.anthropic.claude-sonnet-5-5", "2.1.301", "high"),
    "A4": Arm("A4", "global.anthropic.claude-opus-5-5", "2.1.301", "medium"),
    "A5": Arm("A5", "global.anthropic.claude-haiku-5-5", "2.1.301", "medium"),
    # S1(2026-10-18): 초안 A('같은 확신도') 한 가지만 다른 쌍 — U8 ② 운영 예정 구성(A2)과 같은 모델·CLI·effort.
    # 10-17 의 A2 를 대조군으로 쓰지 않는 이유: 그 뒤 F1(절단 경고)이 들어와 잘린 원문(기사 1/3)의 지시가 달라졌다.
    "S1C": Arm("S1C", "global.anthropic.claude-sonnet-5-5", "2.1.301", "medium"),
    "S1A": Arm("S1A", "global.anthropic.claude-sonnet-5-5", "2.1.301", "medium", _S1_DRAFT_A, "s1_draft_a"),
}


_RULES_ANCHOR = "## 논조·귀속 보존"


def insert_rules(system_prompt: str, patch: str) -> str:
    """추가 규칙을 '논조·귀속 보존' 절 바로 다음(다음 '## ' 절 앞)에 넣는다.

    넣을 자리가 없으면 ValueError — 초안 없이 돈 실험은 무의미하므로 조용히 빠뜨리지 않는다.
    """
    i = system_prompt.find(_RULES_ANCHOR)
    if i < 0:
        raise ValueError(f"지시문에 '{_RULES_ANCHOR}' 절이 없다 — 추가 규칙을 넣을 자리를 못 찾음")
    k = system_prompt.find("\n## ", i + len(_RULES_ANCHOR))
    k = len(system_prompt) if k < 0 else k + 1
    return system_prompt[:k] + patch.rstrip("\n") + "\n\n" + system_prompt[k:]


def system_prompt_for(arm: Arm, user) -> str:
    """조건의 system 지시문 = 운영 build_system_prompt(+ 조건의 추가 규칙)."""
    s = build_system_prompt(lens_guidance=resolve_lens(user.lens).guidance, skill_md=user.skill_md)
    return insert_rules(s, arm.rules_patch) if arm.rules_patch else s


@dataclass
class AuthorRun:
    kind: str                 # "draft" | "revise" — make_author_fns 가 채운다
    text: str
    cost_usd: float | None
    usage: dict
    stop_reason: str | None
    duration_ms: int
    returncode: int | None
    error: str | None


def _claude_bin(arm: Arm) -> Path:
    return EXP_ROOT / "bin" / f"claude-{arm.cli_version}" / "node_modules" / ".bin" / "claude"


def build_env(arm: Arm, *, home_dir: Path) -> dict[str, str]:
    """허용 목록 env — 세션의 API 키·Claude Code 플래그 등은 상속하지 않는다."""
    node = shutil.which("node")
    path = [str(_claude_bin(arm).parent)] + ([str(Path(node).parent)] if node else []) + ["/usr/local/bin", "/usr/bin", "/bin"]
    env = {
        "PATH": ":".join(path),
        "HOME": str(home_dir),
        "LANG": "C.UTF-8",
        "CLAUDE_CODE_USE_BEDROCK": "1",
        "ANTHROPIC_MODEL": arm.model_id,
        "AWS_REGION": "us-east-1",
        "AWS_SHARED_CREDENTIALS_FILE": str(Path.home() / ".aws" / "credentials"),
        "AWS_CONFIG_FILE": str(Path.home() / ".aws" / "config"),
        "ENABLE_TOOL_SEARCH": "false",
    }
    if arm.effort and EFFORT_VIA == "env":
        env["CLAUDE_CODE_EFFORT_LEVEL"] = arm.effort
    return env


def run_author(system_prompt: str, user_prompt: str, arm: Arm, *, timeout_s: int = 600) -> AuthorRun:
    """빈 HOME·빈 cwd·stdin 닫음으로 `claude -p --system-prompt … --output-format json` 1회 실행."""
    home = Path(tempfile.mkdtemp(prefix="ue-author-home-"))
    cwd = Path(tempfile.mkdtemp(prefix="ue-author-cwd-"))
    shutil.copy(_CLAUDE_CONFIG, home / ".claude.json")
    cmd = [str(_claude_bin(arm)), "-p", "--system-prompt", system_prompt, "--output-format", "json"]
    if arm.effort and EFFORT_VIA == "flag":
        cmd += ["--effort", arm.effort]
    t0 = time.monotonic()
    try:
        proc = subprocess.run(cmd + [user_prompt], cwd=cwd, env=build_env(arm, home_dir=home), capture_output=True,
                              text=True, timeout=timeout_s, stdin=subprocess.DEVNULL, check=False)
    except subprocess.TimeoutExpired:
        return AuthorRun("", "", None, {}, None, int((time.monotonic() - t0) * 1000), None, "timeout")
    finally:
        shutil.rmtree(home, ignore_errors=True)
        shutil.rmtree(cwd, ignore_errors=True)
    duration = int((time.monotonic() - t0) * 1000)
    try:
        env_obj = json.loads(proc.stdout)
    except ValueError:
        return AuthorRun("", proc.stdout, None, {}, None, duration, proc.returncode,
                         f"envelope 파싱 실패 rc={proc.returncode}: {proc.stderr.strip()[:200]}")
    error = None
    if proc.returncode != 0:
        error = f"rc={proc.returncode}: {proc.stderr.strip()[:200]}"
    elif env_obj.get("is_error"):
        error = f"is_error: {str(env_obj.get('result', ''))[:200]}"
    return AuthorRun("", str(env_obj.get("result", "")), env_obj.get("total_cost_usd"), env_obj.get("usage") or {},
                     env_obj.get("stop_reason") or env_obj.get("subtype"), duration, proc.returncode, error)


def make_author_fns(
    arm: Arm, *, log: list[AuthorRun], timeout_s: int = 600, runner=run_author
) -> tuple[Callable[..., DraftCard], Callable[..., DraftCard]]:
    """`gate.produce_card` 에 주입할 (draft_fn, revise_fn) — 운영 `draft_card`·`revise_claims` 와 같은 시그니처."""

    def _call(kind: str, system_prompt: str, user_prompt: str) -> str:
        run = runner(system_prompt, user_prompt, arm, timeout_s=timeout_s)
        run.kind = kind
        log.append(run)
        if run.error:
            raise RuntimeError(run.error)
        return run.text

    def _system(user) -> str:
        return system_prompt_for(arm, user)

    def draft_fn(source, user, settings) -> DraftCard:
        text = _call("draft", _system(user), build_user_prompt(source, today=EVAL_TODAY))
        return _to_draft_card(source.source_id, source.title, _parse_card_json(text))

    def revise_fn(source, user, settings, *, prior, failed_ids) -> DraftCard:
        text = _call("revise", _system(user), _build_revise_prompt(source, prior, failed_ids, today=EVAL_TODAY))
        return _to_draft_card(source.source_id, source.title, _parse_card_json(text))

    return draft_fn, revise_fn
