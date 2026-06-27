"""_debug — DEBUG=1 파이프라인 추적 (capture↔render 분리 + redaction 패턴).

off(기본) 시 모든 emitter 가 즉시 return → **zero overhead**. Strands 무의존 → 모든 레이어(gate·subprocess·supervisor) 공용.
출력은 **stderr**(stdout 의 이메일/JSON 오염 방지). 켜기: `DEBUG=1 uv run ...`.
색 의미: cyan=호출/입력 · magenta=envelope 박스 · yellow=verdict · green=PUBLISH · red=BLOCK/QUARANTINE · dim=timing.
"""
from __future__ import annotations

import os
import sys

_C = {
    "cyan": "\033[36m", "magenta": "\033[35m", "yellow": "\033[33m",
    "green": "\033[32m", "red": "\033[31m", "dim": "\033[2m", "reset": "\033[0m",
}


def is_debug() -> bool:
    """DEBUG env 가 truthy(1/true/yes/on) 면 디버그 on. (모든 emitter 의 첫 줄 가드.)"""
    return os.environ.get("DEBUG", "").strip().lower() in ("1", "true", "yes", "on")


def truncate(text: object, limit: int = 400) -> str:
    s = "" if text is None else str(text)
    return s if len(s) <= limit else f"{s[:limit]}…(+{len(s) - limit} chars)"


def dprint(label: str, body: object = "", color: str = "cyan") -> None:
    """한 줄 추적: `[DEBUG <label>] <body>` (stderr)."""
    if not is_debug():
        return
    c, r = _C.get(color, ""), _C["reset"]
    print(f"{c}[DEBUG {label}]{r} {truncate(body)}", file=sys.stderr, flush=True)


def dprint_box(top_label: str, lines: list[str], color: str = "magenta") -> None:
    """다중 라인 박스: `┏━━ label ━━ … ┗━━` (stderr)."""
    if not is_debug():
        return
    c, r = _C.get(color, ""), _C["reset"]
    print(f"{c}┏━━ {top_label} ━━{r}", file=sys.stderr)
    for line in lines:
        print(f"{c}┃{r} {truncate(line, 200)}", file=sys.stderr)
    print(f"{c}┗━━{r}", file=sys.stderr, flush=True)


def mask(secret: object, keep: int = 4) -> str:
    """비밀/식별값 마스킹 — 끝 keep 자 + 길이만(전체 노출 금지)."""
    s = str(secret or "")
    return f"…{s[-keep:]} (len={len(s)})" if len(s) > keep else "***"


def redact_envelope(envelope: object) -> list[str]:
    """certifier envelope → 디버그 라인들 (정확히 4필드, source_excerpt 는 truncate).

    ★ narration/lens/skill 류 *부재* 를 눈으로 확인하는 용도 — certifier 가 무엇을 보는지 그대로 보여줌.
    """
    return [
        f"source_excerpt: {truncate(getattr(envelope, 'source_excerpt', ''), 160)}",
        f"claim_text: {getattr(envelope, 'claim_text', '')}",
        f"claim_type: {getattr(envelope, 'claim_type', '')}",
        f"schema: {getattr(envelope, 'schema', '')}",
    ]
