"""주간 기사 md → 메일 HTML(라이트 테마 · 인라인 스타일). 1호(2026-10-31) 발송 렌더와 같은 출력.

데일리 `core/render.py` 와 다른 브랜드라 틀 · 색을 따로 둔다(README §2). 메일 클라이언트가 <style> 을
버리므로 스타일은 태그마다 인라인으로 넣는다.
"""
from __future__ import annotations

import html as _html
import re

import markdown

BRAND = "Field Experiment · 현장 실험"
SUBTITLE = "이번 주 프론티어 글을 내 시스템에서 재는 법"
# 푸터 문안 — 법적 검토(issues/2026-10-31.legal-review.md) 고칠 것 1 · 3(검증 범위 · AI 고지)이 승인되면 바뀐다.
FOOTER = "②의 사실은 데일리와 같은 원문 대조를 통과했고, ③④는 제안입니다. 저장소 링크는 발송 당일 확인했습니다."

_BARE_URL_ITEM = re.compile(r"^- (https?://\S+)$", re.M)   # 출처 목록의 맨 URL → 앵커
_H2 = '<h2 style="font-size:18px;margin:26px 0 8px;padding-top:6px;border-top:1px solid #e3dfd6">'
_PRE = ('<pre style="font-family:ui-monospace,Menlo,Consolas,D2Coding,monospace;font-size:13px;line-height:1.45;'
        'background:#ece8df;padding:12px 14px;border-radius:4px;white-space:pre;overflow-x:auto;margin:10px 0">'
        '<code style="font-family:inherit;background:none;padding:0">')
_CODE = '<code style="font-family:ui-monospace,Menlo,monospace;font-size:14px;background:#ece8df;padding:1px 4px;border-radius:3px">'


def split_title(md: str) -> tuple[str, str]:
    """첫 줄 `# 제목` → (제목, 나머지 본문 md)."""
    first, _, rest = md.partition("\n")
    return first.lstrip("# ").strip(), rest


def email_subject(title: str) -> str:
    return f"[현장 실험] {title}"


def render_email(md: str, *, footer: str = FOOTER, banner: str = "") -> str:
    """banner(옵션) = 머리 아래 경고 한 줄(격리 호를 관리자에게 보낼 때). 비면 1호 발송 HTML 과 바이트까지 같다."""
    title, body_md = split_title(md)
    warn = (f'<div style="background:#fbe9e7;border:1px solid #d9534f;color:#7a1f1f;padding:10px 12px;border-radius:4px;'
            f'font-size:13px;margin-bottom:16px">&#9888; {_html.escape(banner, quote=False)}</div>' if banner else "")
    body_md = _BARE_URL_ITEM.sub(r"- <\1>", body_md)
    body = markdown.markdown(body_md, extensions=["sane_lists", "fenced_code"])
    doc = f"""<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title></head>
<body style="margin:0;background:#f6f4ef;font-family:-apple-system,'Apple SD Gothic Neo','Noto Sans KR',Segoe UI,sans-serif;color:#1f1d1a;line-height:1.65">
<div style="max-width:680px;margin:0 auto;padding:28px 20px">
  <div style="border-bottom:3px solid #1f1d1a;padding-bottom:10px;margin-bottom:22px">
    <div style="font-size:13px;letter-spacing:.14em;text-transform:uppercase;color:#6b665e">{BRAND}</div>
    <div style="font-size:13px;color:#6b665e;margin-top:2px">{SUBTITLE}</div>
  </div>
  {warn}<h1 style="font-size:24px;line-height:1.3;margin:0 0 14px">{title}</h1>
  <div style="font-size:16px">{body}</div>
  <div style="border-top:1px solid #cfcac0;margin-top:28px;padding-top:12px;font-size:12px;color:#6b665e">{_html.escape(footer, quote=False)}</div>
</div></body></html>"""
    # 순서가 중요: 그림(<pre><code>)을 일반 <code> 보다 먼저 바꾼다(블록 안 code 는 스타일 초기화).
    doc = doc.replace("<h2>", _H2).replace("<pre><code>", _PRE).replace("<code>", _CODE)
    doc = doc.replace("<a href", '<a style="color:#8a4b1f" href')
    return doc.replace("<ul>", '<ul style="padding-left:20px;margin:6px 0">').replace("<li>", '<li style="margin:4px 0">')
