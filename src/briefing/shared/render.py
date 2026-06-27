"""render — PUBLISH 카드 → 사용자 이메일(원본 제목·출처 도메인·발행일·렌즈·요약).

- **decision == "PUBLISH" 카드만** — QUARANTINE 은 사람-검토 큐(별도, 표본 감사).
- 개별 claim 목록(검증 칩)은 *디버그용* — 사용자 이메일엔 **집계 trust 라인 한 줄**로만(검증 N건·미확인·보류).
- graceful degradation: BLOCKED 는 발행에서 빠지고 집계에 '보류 N건'으로 표시(show-your-work).
- 출처 메타(도메인·원본 제목·url·발행일)는 `store`(content-addressed)에서 조회 — 없으면 우아하게 생략.
순수 함수(LLM·AWS 불필요) — `store` 는 read-only lookup. 이메일 클라이언트용 *인라인* CSS.
"""
from __future__ import annotations

import html
from collections.abc import Sequence
from urllib.parse import urlparse

from .config import Settings, UserConfig
from .gate import GatedCard
from .source_store import SourceStore

_WRAP = (
    '<div style="max-width:680px;margin:0 auto;padding:8px 16px;'
    'font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#1a1a1a;line-height:1.6">'
)


def _domain(url: str) -> str:
    """url → 발행처 도메인 reference (예: 'aitimes.com'). www. 접두 제거."""
    try:
        net = urlparse(url).netloc.lower()
    except ValueError:
        return ""
    return net[4:] if net.startswith("www.") else net


def _source_line(store: SourceStore | None, source_id: str) -> str:
    """발행처 도메인 · 원본 제목(url 링크) · 발행일 — store 에서 조회. 없거나 미발견이면 빈 문자열."""
    if store is None:
        return ""
    try:
        s = store.get_source(source_id)
    except (FileNotFoundError, ValueError):
        return ""
    domain = _domain(s.url)
    title = html.escape(s.title or s.url or "원문")
    link = (
        f'<a href="{html.escape(s.url)}" style="color:#0066cc;text-decoration:none">{title}</a>'
        if s.url else title
    )
    date = s.fetched_at[:10] if s.fetched_at else ""
    parts = [f"<strong>{html.escape(domain)}</strong>" if domain else "", link, date]
    meta = " · ".join(p for p in parts if p)
    return f'<p style="font-size:13px;color:#777;margin:2px 0 10px">📰 {meta}</p>'


def _trust_line(card: GatedCard) -> str:
    """집계 trust 라인 — 개별 claim 대신 검증 N건·미확인·보류 요약(verify-before-publish 신호)."""
    n = {k: sum(1 for v in card.verdicts if v.verdict == k) for k in ("VERIFIED", "DEMOTED", "BLOCKED")}
    bits = []
    if n["VERIFIED"]:
        bits.append(f"사실 {n['VERIFIED']}건 독립 검증")
    if n["DEMOTED"]:
        bits.append(f"미확인 {n['DEMOTED']}건")
    if n["BLOCKED"]:
        bits.append(f"보류 {n['BLOCKED']}건")
    inner = " · ".join(bits) if bits else "검증 완료"
    return f'<p style="font-size:12px;color:#0a7a0a;margin:6px 0 0">✓ 검증 후 발행 — {inner}</p>'


def _card_html(card: GatedCard, store: SourceStore | None, *, depth: str) -> str:
    c = card.card
    parts = [
        f'<h2 style="font-size:19px;margin:20px 0 2px">{html.escape(c.headline)}</h2>',
        _source_line(store, c.source_id),
        f'<p style="margin:8px 0"><strong>왜 중요한가:</strong> {html.escape(c.why_it_matters)}</p>',
    ]
    if depth != "brief":
        parts.append(f'<p style="margin:8px 0;color:#333">{html.escape(c.summary)}</p>')
    parts.append(_trust_line(card))
    return "\n".join(p for p in parts if p)


def render_email(
    cards: Sequence[GatedCard], user: UserConfig, settings: Settings, store: SourceStore | None = None
) -> str:
    """PUBLISH 카드만 → HTML 이메일 (출처 reference·발행일·렌즈·요약; user.depth 로 밀도). 0건이면 폴백."""
    published = [c for c in cards if c.decision == "PUBLISH"]
    lens = getattr(user, "lens", "") or ""
    lens_badge = (
        f' <span style="font-size:13px;color:#0066cc;font-weight:400">· 🔍 {html.escape(lens)} 관점</span>'
        if lens else ""
    )
    header = (
        f'<h1 style="font-size:22px;border-bottom:2px solid #0066cc;padding-bottom:6px;margin:0 0 4px">'
        f"오늘의 브리핑 — {html.escape(user.id)}{lens_badge}</h1>"
    )
    if not published:
        return (
            _WRAP + header
            + "<p>오늘은 검증을 통과한 새 항목이 없습니다. (보류 항목은 사람 검토 큐로 이동했습니다.)</p></div>"
        )
    body = "\n".join(_card_html(c, store, depth=user.depth) for c in published)
    return _WRAP + header + "\n" + body + "</div>"
