"""lenses — 요약 관점(lens) 라이브러리(lenses.yaml) + per-user 선택 해석.

설계:
- LENS_LIBRARY = lenses.yaml 의 vetted 관점 목록(general/executive/engineer/business/...). 로드 시 검증.
- per-user 선택 = profile.yaml `lens: <key>` → resolve_lens(); 미설정/미상이면 default(general)로 폴백.
- ★ lens 는 *편집 렌즈*(강조·어휘)만 — base 계약·검증을 못 바꿈. certifier 는 lens 미열람(불변식 #4).
- author 프롬프트 = base(author_system.md) + lens.guidance + user.skill_md.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class Lens:
    key: str
    name: str
    guidance: str   # author 프롬프트에 붙는 관점 조각(강조점·어휘)


_REQUIRED = ("key", "name", "guidance")
_LENSES_PATH = Path(__file__).parent / "lenses.yaml"
DEFAULT_LENS = "general"


def _load_lenses(path: Path = _LENSES_PATH) -> tuple[Lens, ...]:
    """lenses.yaml 로드 + 검증 → LENS_LIBRARY. 잘못되면 *시작 시 크래시*(silent failure 금지)."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list) or not raw:
        raise ValueError(f"lenses.yaml: 비어있거나 list 아님 ({path})")
    out: list[Lens] = []
    seen: set[str] = set()
    for i, e in enumerate(raw):
        if not isinstance(e, dict):
            raise ValueError(f"lenses[{i}]: 항목이 dict 아님")
        for f in _REQUIRED:
            if not e.get(f):
                raise ValueError(f"lenses[{i}]: 필수 필드 '{f}' 누락/빈값")
        if e["key"] in seen:
            raise ValueError(f"lenses[{i}]: 중복 key '{e['key']}'")
        seen.add(e["key"])
        out.append(Lens(key=e["key"], name=e["name"], guidance=e["guidance"]))
    if DEFAULT_LENS not in seen:
        raise ValueError(f"lenses.yaml: 기본 lens '{DEFAULT_LENS}' 필수")
    return tuple(out)


LENS_LIBRARY: tuple[Lens, ...] = _load_lenses()
_BY_KEY: dict[str, Lens] = {ln.key: ln for ln in LENS_LIBRARY}


def lens_keys() -> tuple[str, ...]:
    """UI/API 검증용 — 선택 가능한 lens 키."""
    return tuple(_BY_KEY)


def resolve_lens(key: str) -> Lens:
    """per-user lens 키 → Lens. 미설정/미상이면 default(general)로 폴백(편집 렌즈라 crash 대신 graceful)."""
    return _BY_KEY.get(key or DEFAULT_LENS, _BY_KEY[DEFAULT_LENS])
