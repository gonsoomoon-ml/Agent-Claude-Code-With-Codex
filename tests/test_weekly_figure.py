"""weekly.figure — 스펙 파싱 · 한도 · 숫자 근거 · HTML 채우기 · 렌더 lint · make_figure(되돌리기 · skipped · ready). fake author · fake renderer, 네트워크 · 브라우저 0."""
import json

import pytest

from briefing.weekly.figure import build as fb
from briefing.weekly.figure.render import FigureUnavailable, lint_report
from briefing.weekly.figure.scheme_a import ARROW_KEYS, SLOTS, fill_scheme_a, parse_spec, validate, width_units

MD = "# t\n## ② 이번 주 근거\n**A, 글.** 분석가 50명, 86% 일치.\n\n**엮으면.** x\n\n## ③ 실험 (제안)\n- 과제: 동료 10명.\n"


def _spec(**over):
    boxes = {k: {"t": "상자" + k, "s": "두 단어", "kind": "accent" if k == "c" else "gray"} for k in SLOTS}
    boxes["tl"]["kind"] = "white"
    right = {k: {"t": "Bedrock", "s": "inference", "kind": "accent" if k == "c" else "gray"} for k in SLOTS}
    obj = {"title": "그림 제목", "hint": "왼쪽은 개념, 오른쪽은 구성", "left": {"title": "개념도", "hint": "기술 용어 없이", "boxes": boxes,
           "arrows": {k: "라벨" for k in ARROW_KEYS}}, "right": {"title": "시스템도", "hint": "실제 구성요소", "boxes": right,
           "arrows": {k: "log" for k in ARROW_KEYS}}, "strip": "같은 자리 같은 구성요소 · 빨간 상자가 새것", "caption": "생략: 캐시"}
    obj.update(over)
    return obj


def test_parse_validate_and_fill():
    spec = parse_spec(_spec())
    assert validate(spec) == [] and width_units("한글abc") == 2 + 3 * 0.55
    html = fill_scheme_a(spec)
    assert html.count("<svg") == 2 and html.count("<rect") == 2 * 8 and html.count("<line") == 12 and "s-box-accent" in html
    body = html.split("<body>")[1].replace("#aL", "").replace("#aR", "")
    assert "tokens.css" in html and "#" not in body                      # 리터럴 hex 없음(색은 tokens.css 의 역할 클래스)
    bad = _spec()
    bad["left"]["boxes"]["c"]["t"] = "아주아주아주긴제목"
    bad["left"]["boxes"]["tl"]["kind"] = "accent"
    bad["left"]["boxes"]["ml"]["kind"] = "accent"
    errs = validate(parse_spec(bad))
    assert any("c.t 너무 김" in e for e in errs) and any("강조(accent) 칸 3개" in e for e in errs)
    with pytest.raises(ValueError):
        parse_spec({"left": {}})
    with pytest.raises(ValueError):
        parse_spec({"left": {"boxes": {}}, "right": {"boxes": {}}})


def test_check_spec_numbers_grounded():
    ok = _spec()
    ok["left"]["boxes"]["bl"]["s"] = "86% 대 50%"
    assert fb.check_spec(parse_spec(ok), MD) == []
    ok["left"]["boxes"]["bl"]["s"] = "36%p 차이"          # 86 - 50
    assert fb.check_spec(parse_spec(ok), MD) == []
    ok["left"]["boxes"]["bl"]["s"] = "표본 123"
    assert any("123" in e for e in fb.check_spec(parse_spec(ok), MD))


def _report(**over):
    runs = [{"text": "제목", "chars": 2, "fontPx": 32, "color": "rgb(26, 23, 21)", "lum": 0.01, "roles": "section-title", "width": 60},
            {"text": "Bedrock", "chars": 7, "fontPx": 20, "color": "rgb(232, 74, 46)", "lum": 0.3, "roles": "s-text-accent bold", "width": 80},
            {"text": "생략", "chars": 2, "fontPx": 19, "color": "rgb(51, 46, 42)", "lum": 0.03, "roles": "caption", "width": 40}]
    rep = {"viewport": {"w": 1200, "h": 800}, "maxBottom": 790, "maxRight": 1150, "overflow": False, "runs": runs,
           "shapeColors": {"rgb(232, 74, 46)": 2, "rgb(253, 227, 217)": 1}, "totalChars": 11}
    rep.update(over)
    return rep


def test_lint_report_rules():
    rows = {n: v for v, n, _ in lint_report(_report(), source_html="<style>#ffffff</style><p>x</p>")}
    assert rows == {"overflow": "PASS", "text budget": "PASS", "min font": "PASS", "small text color": "PASS",
                    "one accent": "PASS", "no literal hex": "PASS", "box fit": "PASS"}
    bad = _report(overflow=True, maxBottom=900)
    bad["runs"].append({"text": "작은", "chars": 2, "fontPx": 12, "color": "rgb(160, 160, 160)", "lum": 0.5, "roles": "notes", "width": 10})
    bad["runs"].append({"text": "아주 긴 상자 제목", "chars": 8, "fontPx": 20, "color": "rgb(26,23,21)", "lum": 0.01, "roles": "s-text bold", "width": 170})
    bad["shapeColors"]["rgb(30, 120, 220)"] = 1
    rows = {n: v for v, n, _ in lint_report(bad, source_html="<p style='color:#123456'>x</p>")}
    assert rows == {"overflow": "FAIL", "text budget": "PASS", "min font": "FAIL", "small text color": "FAIL",
                    "one accent": "FAIL", "no literal hex": "FAIL", "box fit": "FAIL"}


def test_make_figure_revises_then_ready(tmp_path):
    bad = _spec()
    bad["left"]["boxes"]["bl"]["s"] = "표본 123"
    responses, seen = [json.dumps(bad), json.dumps(_spec())], []

    def author(system, user, settings, **kw):
        seen.append(user)
        return responses[len(seen) - 1]
    renders = []

    def renderer(html, png):
        renders.append(html)
        open(png, "wb").write(b"png")
        return _report()
    r = fb.make_figure(MD, None, out_dir=tmp_path / "fig", run_author=author, renderer=renderer)
    assert r.status == "ready" and r.rounds == 2 and r.png.endswith("figure.png") and len(renders) == 1
    assert "이전 스펙(JSON)" in seen[1] and "123" in seen[1] and (tmp_path / "fig" / "tokens.css").exists()
    assert json.loads(r.to_json())["items"][0][0] == "PASS" and "그림 제목" in r.spec_json


def test_make_figure_skipped_without_browser_and_failed_after_rounds(tmp_path):
    def boom(html, png):
        raise FigureUnavailable("playwright 없음")
    r = fb.make_figure(MD, None, out_dir=tmp_path / "a", run_author=lambda *a, **k: json.dumps(_spec()), renderer=boom)
    assert r.status == "skipped" and "playwright" in r.note and r.html.endswith("figure.html") and r.png == ""
    bad = _spec()
    bad["strip"] = ""
    r2 = fb.make_figure(MD, None, out_dir=tmp_path / "b", run_author=lambda *a, **k: json.dumps(bad), renderer=boom, max_rounds=1)
    assert r2.status == "failed" and r2.rounds == 2 and r2.items[0][1] == "spec" and "strip" in r2.items[0][2]
    r3 = fb.make_figure(MD, None, out_dir=tmp_path / "c", run_author=lambda *a, **k: "not json", renderer=boom)
    assert r3.status == "failed" and "스펙 형식" in r3.items[0][2]
