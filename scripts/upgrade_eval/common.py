"""실험 공통 유틸 — 실험 디렉토리, JSONL 기록·재개 키, 소스 종류·언어 분류.

원문·원시 출력은 저장소가 아니라 EXP_ROOT(기본 ~/upgrade-eval)에만 쌓는다(저작권·용량).
유료 호출은 재실행 때 중복되면 안 되므로, 모든 실행기는 done_keys 로 이미 끝난 키를 건너뛴다.
"""
from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlparse

EXP_ROOT = Path(os.environ.get("UPGRADE_EVAL_ROOT") or Path.home() / "upgrade-eval")
SEED = 20261017


def append_jsonl(path: Path, record: dict) -> None:
    """레코드 한 줄을 덧붙인다(부모 디렉토리 자동 생성, 한글은 그대로).
    앞선 실행이 쓰다 죽어 마지막 줄이 잘렸으면 새 줄에서 시작한다 — 잘린 줄에 이어 붙어 두 줄이 함께 깨지지 않게."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as f:
        f.seek(0, os.SEEK_END)
        if f.tell():
            f.seek(-1, os.SEEK_END)
            if f.read(1) != b"\n":
                f.write(b"\n")
        f.write((json.dumps(record, ensure_ascii=False) + "\n").encode("utf-8"))


def read_jsonl(path: Path) -> list[dict]:
    """파일이 없으면 빈 목록. 빈 줄은 건너뛴다. 깨진 줄(쓰다 죽은 실행)은 건너뛰고 몇 줄인지 stderr 로 알린다 —
    긴 유료 실행의 재개가 손으로 고치기 전까지 막히지 않게."""
    if not path.exists():
        return []
    out, bad = [], 0
    with path.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                out.append(json.loads(line))
            except ValueError:
                bad += 1
    if bad:
        print(f"warning: {path}: 깨진 줄 {bad}개 건너뜀", file=sys.stderr)
    return out


def done_keys(path: Path, fields: tuple[str, ...], *, where: Callable[[dict], bool] | None = None) -> set[tuple]:
    """이미 기록된 레코드의 키 튜플 집합 — 레코드에 없는 필드는 None. where 를 주면 그 조건을 만족하는 레코드만
    '끝남'으로 친다(예: 인프라 오류 레코드는 다시 돌리도록 뺀다)."""
    return {tuple(r.get(k) for k in fields) for r in read_jsonl(path) if where is None or where(r)}


def source_kind(url: str) -> str:
    """소스 종류(criteria-application-audit.md 의 측정 방법과 같은 규칙)."""
    parsed = urlparse(url)
    host, path = parsed.netloc.lower(), parsed.path.lower()
    if "aitimes" in host or "the-decoder" in host:
        return "뉴스"
    if "pytorch.kr" in host:
        return "커뮤니티"
    if "anthropic.com" in host and "/engineering" in path:
        return "기술·연구"
    if ("research.google" in host or "developers.googleblog" in host
            or "/blogs/machine-learning" in path or "/ko/blogs/tech" in path):
        return "기술·연구"
    if any(x in host for x in ("anthropic.com", "claude.com", "blog.google", "deepmind", "aws.amazon.com")):
        return "기업 발표"
    return "미상"


def source_lang(url: str) -> str:
    """원문 언어 — 한국어 소스(AI Times·PyTorch KR·AWS 한국 블로그)만 ko."""
    parsed = urlparse(url)
    if "aitimes" in parsed.netloc or "pytorch.kr" in parsed.netloc or "/ko/" in parsed.path:
        return "ko"
    return "en"
