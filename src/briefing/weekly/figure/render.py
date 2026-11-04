"""HTML → PNG 렌더(Chromium · playwright) + 레이아웃 · 글자 보고서, 그리고 그 보고서의 lint.

플러그인 `scripts/render.py` · `scripts/lint.py`(0.1.0) 를 함수로 옮긴 것. playwright 는 지연 import — 없으면 `FigureUnavailable`.
"""
from __future__ import annotations

import colorsys
import pathlib
import re

REPORT_JS = r"""() => {
  const vw = window.innerWidth, vh = window.innerHeight;
  const lum = (c) => { const m = c && c.match(/\d+(\.\d+)?/g); if (!m) return null;
    const [r,g,b] = m.slice(0,3).map(Number).map(v => { v /= 255; return v <= 0.03928 ? v/12.92 : Math.pow((v+0.055)/1.055, 2.4); });
    return 0.2126*r + 0.7152*g + 0.0722*b; };
  const runs = [];
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let n;
  while ((n = walker.nextNode())) {
    const t = n.nodeValue.replace(/\s+/g, ' ').trim(); if (!t) continue;
    const el = n.parentElement; if (!el) continue;
    const tag = el.tagName.toLowerCase(); if (['script','style','title','noscript'].includes(tag)) continue;
    const cs = getComputedStyle(el);
    const isSvg = el.namespaceURI === 'http://www.w3.org/2000/svg';
    const color = isSvg ? cs.fill : cs.color;
    let roles = []; for (let a = el; a && a !== document.body; a = a.parentElement) { const c = a.getAttribute && a.getAttribute('class'); if (c) roles.push(c); }
    const b = el.getBoundingClientRect();
    runs.push({ text: t, chars: t.replace(/\s/g, '').length, fontPx: parseFloat(cs.fontSize),
                color, lum: lum(color), bold: parseInt(cs.fontWeight) >= 600, roles: roles.join(' '),
                width: Math.round(b.width), right: Math.round(b.right) });
  }
  const shapeColors = {};
  const clear = (c) => !c || c === 'none' || c === 'transparent' || /rgba\(\d+, \d+, \d+, 0\)/.test(c);
  for (const e of document.body.querySelectorAll('*')) {
    const b = e.getBoundingClientRect(); if (b.width === 0 && b.height === 0) continue;
    const cs = getComputedStyle(e); const isSvg = e.namespaceURI === 'http://www.w3.org/2000/svg';
    const cols = isSvg ? [cs.fill, cs.stroke] : [cs.backgroundColor, cs.borderTopColor];
    if (!isSvg && cs.borderTopWidth === '0px') cols.pop();
    for (const c of cols) { if (clear(c)) continue; shapeColors[c] = (shapeColors[c] || 0) + 1; }
  }
  let maxBottom = 0, maxRight = 0;
  for (const e of document.body.querySelectorAll('*')) {
    const b = e.getBoundingClientRect(); if (b.width === 0 && b.height === 0) continue;
    maxBottom = Math.max(maxBottom, b.bottom); maxRight = Math.max(maxRight, b.right);
  }
  return { viewport: { w: vw, h: vh }, maxBottom: Math.round(maxBottom), maxRight: Math.round(maxRight),
           overflow: maxBottom > vh + 0.5 || maxRight > vw + 0.5, runs, shapeColors,
           totalChars: runs.reduce((a, r) => a + r.chars, 0) };
}"""


class FigureUnavailable(RuntimeError):
    """렌더 환경(playwright · Chromium)이 없다 — 그림을 건너뛴다."""


def render_png(html_path: str, png_path: str, *, width: int = 1200, height: int = 800, scale: int = 1) -> dict:
    try:
        from playwright.sync_api import sync_playwright  # lazy — 컨테이너에는 없다
    except ImportError as e:
        raise FigureUnavailable(f"playwright 없음: {e}") from e
    try:
        with sync_playwright() as p:
            b = p.chromium.launch()
            pg = b.new_page(viewport={"width": width, "height": height}, device_scale_factor=scale)
            pg.goto(pathlib.Path(html_path).resolve().as_uri())
            pg.wait_for_timeout(600)
            rep = pg.evaluate(REPORT_JS)
            pg.screenshot(path=png_path, clip={"x": 0, "y": 0, "width": width, "height": height})
            b.close()
    except Exception as e:  # noqa: BLE001 — 브라우저 실행 실패(Chromium 미설치 등)도 "환경 없음"
        raise FigureUnavailable(f"렌더 실패: {type(e).__name__}: {e}") from e
    return rep


def _rgb(c: str):
    m = re.findall(r"\d+(?:\.\d+)?", c or "")
    return tuple(float(x) for x in m[:3]) if len(m) >= 3 else None


def _hue_bucket(c: str):
    v = _rgb(c)
    if not v:
        return None
    h, lum, s = colorsys.rgb_to_hls(*(x / 255 for x in v))
    if s < 0.25 or lum > 0.92 or lum < 0.08:
        return None
    return int(h * 12)


def lint_report(rep: dict, *, source_html: str = "", budget: int = 400, min_font: float = 16, small: float = 20,
                light: float = 0.30) -> list[tuple[str, str, str]]:
    """(판정, 검사, 상세). 플러그인 lint.py 와 같은 규칙: 넘침 · 글자 예산 · 최소 크기 · 작은 글자 색 · 강조색 1 · hex 금지 + 칸 넘침."""
    rows: list[tuple[str, str, str]] = []
    scale = 1080 / rep["viewport"]["w"]
    runs = rep["runs"]
    rows.append(("PASS" if not rep["overflow"] else "FAIL", "overflow",
                 f"maxBottom {rep['maxBottom']}/{rep['viewport']['h']}, maxRight {rep['maxRight']}/{rep['viewport']['w']}"))
    footer = ("source", "caption", "s-text-3")
    body = sum(r["chars"] for r in runs if not any(k in r.get("roles", "") for k in footer))
    rows.append(("PASS" if body <= budget else "FAIL", "text budget", f"{body} body chars (budget {budget})"))
    tiny = [r for r in runs if r["fontPx"] * scale < min_font]
    rows.append(("PASS" if not tiny else "FAIL", "min font",
                 f"smallest {min(r['fontPx'] for r in runs) * scale:.1f}px at 1080" + (f"; too small: {[r['text'][:18] for r in tiny[:4]]}" if tiny else "")))
    light_runs = [r for r in runs if r["fontPx"] * scale <= small and (r["lum"] or 0) > light and (r["lum"] or 0) <= 0.95]
    rows.append(("PASS" if not light_runs else "FAIL", "small text color",
                 "all small text near-black" if not light_runs else f"light small text: {[(r['text'][:18], r['color']) for r in light_runs[:4]]}"))
    hues: dict[int, set[str]] = {}
    for c in [r["color"] for r in runs] + list(rep.get("shapeColors", {}).keys()):
        hb = _hue_bucket(c)
        if hb is not None:
            hues.setdefault(hb, set()).add(c)
    rows.append(("PASS" if len(hues) <= 1 else "FAIL", "one accent", f"{len(hues)} saturated hue families"))
    if source_html:
        body_src = re.sub(r"<style.*?</style>", "", source_html, flags=re.S)
        hexes = sorted(set(re.findall(r"#[0-9A-Fa-f]{6}\b", body_src)))
        rows.append(("PASS" if not hexes else "FAIL", "no literal hex", "colors from tokens.css" if not hexes else f"literal: {hexes[:6]}"))
    # 칸 넘침: SVG 상자 글자(20px 제목)가 140px 를 넘으면 상자 밖으로 나간다 — 보고서의 폭으로 잡는다
    wide = [r for r in runs if "s-text" in r.get("roles", "") and r.get("width", 0) > 136 and r["fontPx"] >= 20]
    rows.append(("PASS" if not wide else "FAIL", "box fit", "box titles fit 140px" if not wide else f"wider than box: {[r['text'] for r in wide[:4]]}"))
    return rows
