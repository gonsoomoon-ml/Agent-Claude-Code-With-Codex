"""weekly.render — 제목 분리 · 제목줄 · 그림(pre) 스타일 · 맨 URL 앵커 · 인라인 스타일(합성 md, 네트워크 0)."""
from briefing.weekly.render import email_subject, render_email, split_title

MD = """# 추천, 사람은 얼마나 따르나
2026-10-24 ~ 10-30 · 이번 주 글: Anthropic

**실험 한 줄.** 동전으로 정한다.

## ① 어떤 문제인가
판단 지점에서 `에이전트` 가 정한다.
```
질문 -> 갈림길
 +-- 에이전트: "4주" <추천>
```

## ③ 실험 (제안)
- 시작점(코드):
  - [anthropics/claude-agent-sdk-python](https://github.com/anthropics/claude-agent-sdk-python) — examples

출처
- https://www.anthropic.com/research/agents-judgment-calls
"""


def test_split_title_and_subject():
    title, rest = split_title(MD)
    assert title == "추천, 사람은 얼마나 따르나" and rest.startswith("2026-10-24")
    assert email_subject(title) == "[현장 실험] 추천, 사람은 얼마나 따르나"


def test_render_email_structure_and_inline_styles():
    html = render_email(MD)
    assert "<title>추천, 사람은 얼마나 따르나</title>" in html and "Field Experiment · 현장 실험" in html
    # 그림: 고정폭 · 줄바꿈 없음 · 블록 안 code 는 일반 code 스타일을 받지 않는다 · <> 는 이스케이프
    assert "white-space:pre" in html and "&lt;추천&gt;" in html
    pre = html.split("<pre", 1)[1].split("</pre>", 1)[0]
    assert "background:#ece8df;padding:1px 4px" not in pre
    assert 'background:#ece8df;padding:1px 4px;border-radius:3px">에이전트</code>' in html   # 인라인 code
    # 출처의 맨 URL 은 앵커가 되고, 모든 링크 · 목록 · 소제목에 인라인 스타일
    assert 'href="https://www.anthropic.com/research/agents-judgment-calls"' in html
    assert "<a href" not in html and "<ul>" not in html and "<li>" not in html and "<h2>" not in html
    assert "③④는 제안입니다" in html


def test_footer_override_is_escaped():
    assert "a &lt;b&gt;" in render_email(MD, footer="a <b>")
