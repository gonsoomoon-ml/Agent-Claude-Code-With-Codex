"""scheme A 스펙 → HTML. 기하는 플러그인 `scheme-a-two-panel.html`(0.1.0) 의 좌표 그대로 — 상자 140×76, 3행 격자, 화살표 6개.

슬롯: tl · tr(1행) / ml · c · mr(2행, c = 가운데) / bl · br(3행). 화살표(고정 방향): tl->c · tr->c · ml->c · mr->c · c->bl · c->br.
칸 종류: white(사람 · 입구) · gray(기존 구성요소) · accent(새로 만드는 것 — 패널당 1~2개).
"""
from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass, field

SLOTS = ("tl", "tr", "ml", "c", "mr", "bl", "br")
_POS = {"tl": (10, 92), "tr": (390, 92), "ml": (10, 272), "c": (200, 272), "mr": (390, 272), "bl": (10, 452), "br": (390, 452)}
# (key, x1, y1, x2, y2, label x, label y, text-anchor)
ARROWS = (("tl-c", 120, 168, 225, 270, 140, 206, "end"), ("tr-c", 420, 168, 315, 270, 400, 206, "start"),
          ("ml-c", 150, 310, 198, 310, 175, 300, "middle"), ("mr-c", 390, 310, 342, 310, 366, 300, "middle"),
          ("c-bl", 225, 348, 120, 450, 140, 404, "end"), ("c-br", 315, 348, 420, 450, 400, 404, "start"))
ARROW_KEYS = tuple(a[0] for a in ARROWS)
_KIND_CLASS = {"white": "s-box", "gray": "s-box-gray", "accent": "s-box-accent"}
# 글자 한도(칸 140px · 20px 글꼴 ≈ 한글 7자 · 라틴 12자; 부제 18px ≈ 한글 8자) — 넘치면 스펙을 되돌린다(렌더 전에 잡는다)
LIMITS = {"title": 7, "sub": 8, "arrow": 4, "panel_title": 6, "panel_hint": 12, "page_title": 26, "page_hint": 30, "strip": 44, "caption": 44}


def width_units(s: str) -> float:
    """한글 1 · 라틴 0.55 로 센 폭(한글 글자 수 환산)."""
    return sum(1.0 if ord(ch) > 0x2E7F else 0.55 for ch in s)


@dataclass(frozen=True)
class Box:
    title: str
    sub: str
    kind: str = "gray"


@dataclass(frozen=True)
class Panel:
    title: str
    hint: str
    boxes: dict[str, Box]
    arrows: dict[str, str]


@dataclass(frozen=True)
class Spec:
    title: str
    hint: str
    left: Panel
    right: Panel
    strip: str
    caption: str
    raw: dict = field(default_factory=dict, compare=False)

    def to_json(self) -> str:
        return json.dumps(self.raw, ensure_ascii=False)

    def texts(self) -> list[str]:
        out = [self.title, self.hint, self.strip, self.caption]
        for p in (self.left, self.right):
            out += [p.title, p.hint, *p.arrows.values()]
            out += [b.title for b in p.boxes.values()] + [b.sub for b in p.boxes.values()]
        return out


def _panel(d: dict, side: str) -> Panel:
    boxes = {}
    for k in SLOTS:
        b = (d.get("boxes") or {}).get(k)
        if not isinstance(b, dict):
            raise ValueError(f"{side}.boxes.{k} 없음")
        kind = str(b.get("kind", "gray")).lower()
        if kind not in _KIND_CLASS:
            raise ValueError(f"{side}.boxes.{k}.kind={kind!r} (white|gray|accent)")
        boxes[k] = Box(str(b.get("t", "")).strip(), str(b.get("s", "")).strip(), kind)
    arrows = {k: str((d.get("arrows") or {}).get(k, "")).strip() for k in ARROW_KEYS}
    return Panel(str(d.get("title", "")).strip(), str(d.get("hint", "")).strip(), boxes, arrows)


def parse_spec(obj: dict) -> Spec:
    if not isinstance(obj, dict) or not isinstance(obj.get("left"), dict) or not isinstance(obj.get("right"), dict):
        raise ValueError("스펙에 left · right 패널이 없다")
    return Spec(str(obj.get("title", "")).strip(), str(obj.get("hint", "")).strip(), _panel(obj["left"], "left"),
                _panel(obj["right"], "right"), str(obj.get("strip", "")).strip(), str(obj.get("caption", "")).strip(), raw=obj)


def validate(spec: Spec) -> list[str]:
    """글자 한도 · 빈 칸 · 강조 칸 수. 위반 목록(작성자에게 돌려줄 말)."""
    errs = []
    for name, val, lim in (("title", spec.title, LIMITS["page_title"]), ("hint", spec.hint, LIMITS["page_hint"]),
                           ("strip", spec.strip, LIMITS["strip"]), ("caption", spec.caption, LIMITS["caption"])):
        if not val:
            errs.append(f"{name} 비어 있음")
        elif width_units(val) > lim:
            errs.append(f"{name} 너무 김({val!r}, 한글 {lim}자 한도)")
    for side, p in (("left", spec.left), ("right", spec.right)):
        if width_units(p.title) > LIMITS["panel_title"]:
            errs.append(f"{side}.title 너무 김({p.title!r})")
        if width_units(p.hint) > LIMITS["panel_hint"]:
            errs.append(f"{side}.hint 너무 김({p.hint!r})")
        accents = [k for k, b in p.boxes.items() if b.kind == "accent"]
        if not 1 <= len(accents) <= 2:
            errs.append(f"{side} 강조(accent) 칸 {len(accents)}개 (1~2)")
        for k, b in p.boxes.items():
            if not b.title:
                errs.append(f"{side}.boxes.{k}.t 비어 있음")
            if width_units(b.title) > LIMITS["title"]:
                errs.append(f"{side}.boxes.{k}.t 너무 김({b.title!r}, 한글 {LIMITS['title']}자 한도)")
            if width_units(b.sub) > LIMITS["sub"]:
                errs.append(f"{side}.boxes.{k}.s 너무 김({b.sub!r}, 한글 {LIMITS['sub']}자 한도)")
        for k, a in p.arrows.items():
            if width_units(a) > LIMITS["arrow"]:
                errs.append(f"{side}.arrows.{k} 너무 김({a!r}, 한글 {LIMITS['arrow']}자 한도)")
    return errs


_NUM = re.compile(r"\d+(?:,\d{3})*(?:\.\d+)?")


def spec_numbers(spec: Spec) -> set[float]:
    return {float(m.replace(",", "")) for t in spec.texts() for m in _NUM.findall(t)}


def _svg_panel(p: Panel, marker: str) -> str:
    e = html.escape
    out = ['<svg width="540" height="560" viewBox="0 0 540 560">',
           f'<defs><marker id="{marker}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">'
           f'<path d="M0,0 L10,5 L0,10 z" class="s-arrow"/></marker></defs>',
           '<rect x="0.5" y="0.5" width="539" height="559" rx="18" class="s-panel"/>',
           f'<text x="24" y="40" font-size="24" class="s-text bold">{e(p.title)}</text>',
           f'<text x="{24 + int(width_units(p.title) * 24) + 12}" y="40" font-size="18" class="s-text-2">{e(p.hint)}</text>']
    for k in SLOTS:
        b, (x, y) = p.boxes[k], _POS[k]
        cls = _KIND_CLASS[b.kind]
        tcls = "s-text-accent bold" if b.kind == "accent" else "s-text bold"
        out.append(f'<rect x="{x}" y="{y}" width="140" height="76" rx="12" class="{cls}"/>')
        out.append(f'<text x="{x + 70}" y="{y + 32}" font-size="20" text-anchor="middle" class="{tcls}">{e(b.title)}</text>')
        if b.sub:
            out.append(f'<text x="{x + 70}" y="{y + 58}" font-size="18" text-anchor="middle" class="s-text-2">{e(b.sub)}</text>')
    for key, x1, y1, x2, y2, lx, ly, anchor in ARROWS:
        out.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" class="s-line" marker-end="url(#{marker})"/>')
        if p.arrows.get(key):
            out.append(f'<text x="{lx}" y="{ly}" font-size="18" text-anchor="{anchor}" class="s-text-2">{e(p.arrows[key])}</text>')
    out.append("</svg>")
    return "\n    ".join(out)


def fill_scheme_a(spec: Spec) -> str:
    """스펙 → 완성 HTML(tokens.css · base.css 를 같은 폴더에서 읽는다)."""
    e = html.escape
    return f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>{e(spec.title)}</title>
<link rel="stylesheet" href="tokens.css">
<link rel="stylesheet" href="base.css">
<style>
  :root {{ --canvas-w: 1200px; --canvas-h: 800px; --pad-top: 34px; --pad-x: 48px; --pad-bottom: 26px;
          --fs-small: 19px; --fs-source: 18px; --fs-label: 20px; --fs-body: 25px; }}
  .panels {{ display: flex; gap: 24px; }}
  .title-row {{ display: flex; align-items: baseline; gap: 16px; }}
</style>
</head>
<body>
<div class="page">

<section data-band="title" class="title-row">
  <span class="section-title">{e(spec.title)}</span>
  <span class="section-src">{e(spec.hint)}</span>
</section>

<section data-band="panels" class="panels">
  {_svg_panel(spec.left, "aL")}

  {_svg_panel(spec.right, "aR")}
</section>

<section data-band="caption">
  <p class="strip">{e(spec.strip)}</p>
  <p class="caption">{e(spec.caption)}</p>
</section>

</div>
</body>
</html>
"""
