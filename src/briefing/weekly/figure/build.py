"""그림 트랙 오케스트레이션 — 기사 md → 스펙(작성자) → 검증(한도 · 숫자 근거) → HTML → PNG → lint, 되돌리기 ≤ max_rounds.

작성자 호출은 데일리 `_run_author`(clean dir · Bedrock env) 재사용. 렌더는 DI(`renderer`) — 테스트는 fake. playwright 가 없는 환경은
`FigureUnavailable` → status "skipped"(기사 생성은 막지 않는다). 컨테이너는 2026-11-07 (d) 부터 playwright + Chromium + Noto CJK 를 싣는다.
"""
from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path

from ...core.authoring import author as _author
from .. import lint as _lint
from .render import FigureUnavailable, lint_report, render_png
from .scheme_a import Spec, fill_scheme_a, parse_spec, spec_numbers, validate

_TEMPLATES = Path(__file__).resolve().parent / "templates"
_PROMPT = Path(__file__).resolve().parent / "prompts" / "figure_system.md"


@dataclass
class FigureResult:
    status: str                       # ready | failed | skipped
    png: str = ""
    html: str = ""
    spec_json: str = ""
    items: list = field(default_factory=list)   # (판정, 검사, 상세) — run 로그
    rounds: int = 0
    note: str = ""

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)


def build_figure_system_prompt() -> str:
    return _PROMPT.read_text(encoding="utf-8")


def build_figure_user_prompt(md: str) -> str:
    return "기사:\n\n" + md + "\n\n위 기사의 그림 스펙을 JSON 으로만 답하라."


def build_figure_revise_prompt(spec: Spec, errs: list[str]) -> str:
    return ("이전 스펙(JSON):\n" + spec.to_json() + "\n\n다음이 걸렸다. 걸린 것만 고치고 같은 JSON 형식으로 전체를 다시 답하라.\n"
            + "\n".join(f"- {e}" for e in errs))


def _fmt(v: float) -> str:
    return str(int(v)) if v == int(v) else str(v)


def check_spec(spec: Spec, md: str) -> list[str]:
    """한도 · 빈 칸 · 강조 칸(validate) + 숫자 근거(기사 본문 숫자 ∪ ② 합 · 차 — lint 7b 와 같은 집합)."""
    errs = validate(spec)
    stray = sorted(spec_numbers(spec) - _lint.allowed_figure_numbers(md))
    if stray:
        errs.append(f"기사에 없는 숫자 {[_fmt(v) for v in stray]} — ② 의 숫자나 그 합 · 차만")
    return errs


def make_figure(md: str, settings, *, out_dir: Path, model_id: str = "", effort: str | None = None, run_author=None,
                recorder=None, renderer=render_png, max_rounds: int = 2, timeout_s: int | None = None) -> FigureResult:
    """기사 md → 그림 PNG(≤ max_rounds 되돌리기). `timeout_s` = 작성자 subprocess 상한(None = 데일리 360) — 주간 상한을 그대로 받는다(2026-11-07)."""
    run = run_author or _author._run_author
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for css in ("tokens.css", "base.css"):
        shutil.copyfile(_TEMPLATES / css, out_dir / css)
    html_path, png_path = out_dir / "figure.html", out_dir / "figure.png"
    system, user = build_figure_system_prompt(), build_figure_user_prompt(md)
    spec: Spec | None = None
    result = FigureResult("failed")
    for rnd in range(1, max_rounds + 2):
        result.rounds = rnd
        text = run(system, user, settings, model_id=model_id, effort=effort, recorder=recorder, prompt_via_stdin=True,
                   timeout_s=timeout_s)
        try:
            obj = _author._last_json_object(text)
            spec = parse_spec(obj if obj is not None else {})
            errs = check_spec(spec, md)
        except ValueError as e:
            errs = [f"스펙 형식: {e}"]
        if errs:
            result.items = [("FAIL", "spec", e) for e in errs]
            if spec is not None and rnd <= max_rounds:
                user = build_figure_revise_prompt(spec, errs)
                continue
            result.note = "스펙 검증 실패"
            return result
        result.spec_json = spec.to_json()
        html_path.write_text(fill_scheme_a(spec), encoding="utf-8")
        result.html = str(html_path)
        try:
            rep = renderer(str(html_path), str(png_path))
        except FigureUnavailable as e:
            return FigureResult("skipped", html=str(html_path), spec_json=result.spec_json, rounds=rnd, note=str(e)[:200])
        result.items = lint_report(rep, source_html=html_path.read_text(encoding="utf-8"))
        fails = [f"{name}: {detail}" for v, name, detail in result.items if v == "FAIL"]
        if not fails:
            result.status, result.png = "ready", str(png_path)
            return result
        if rnd <= max_rounds:
            user = build_figure_revise_prompt(spec, fails)
            continue
        result.note = "렌더 lint 실패: " + "; ".join(fails)[:300]
        return result
    return result
