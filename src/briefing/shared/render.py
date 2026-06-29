"""render — PUBLISH 카드 → "검증 명세서(Verified Dispatch)" 이메일.

디자인(`design/email-ux-mockup.md`):
- 카드 = **요약(검증 대상) → 점선 → 나에게 왜 중요한가(해석, 시각 구분) → 검증줄**. depth 로 밀도(title-only/summary/full).
- 검증줄 = **"다른 AI 에이전트가 사실 N건 검증"** (decorrelation 을 평이하게) + `<details>` 근거. 개별 claim 텍스트는 비노출(불변식).
- 분야(Area) = 출처 카탈로그 category 로 그룹 — **분야 2개 이상일 때만 밴드**, 번호 분야별 리셋(`source_categories` 주입).
- decision == "PUBLISH" 카드만 · QUARANTINE 제외 · 0건이면 폴백. 순수 함수(LLM·AWS 불필요), 이메일 클라이언트용 인라인 CSS.
"""
from __future__ import annotations

import datetime
import html
from collections.abc import Mapping, Sequence
from urllib.parse import urlparse

from .config import Settings, UserConfig
from .gate import GatedCard
from .stores.source_store import SourceStore

# ── 검증 명세서 토큰 ──
_INK = "#1A0F0A"
_PAPER = "#FAF9F6"
_CORAL = "#FF6B47"
_RULE = "#E8E3DC"
_META = "#8C8178"
_AMBER = "#9A6A00"   # 미확인/보류 있을 때(worst-verdict)
_OK = "#0F6B4A"      # 전부 통과(차분한 evidence green)
_MONO = 'font-family:"SF Mono",Menlo,Consolas,monospace'

_WRAP = (
    '<div style="max-width:600px;margin:0 auto;padding:14px 18px;'
    f"background-color:{_PAPER};color:{_INK};color-scheme:light only;"
    'font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;line-height:1.6">'
)


_WEEKDAY_KO = ("월", "화", "수", "목", "금", "토", "일")  # date.weekday(): 월=0


def format_briefing_date(run_date: str) -> str:
    """ISO 날짜(YYYY-MM-DD[...]) → 'M월 D일 (요일)'. 빈값/파싱불가면 '' (헤더에서 날짜 생략)."""
    try:
        d = datetime.date.fromisoformat(run_date[:10])
    except (ValueError, TypeError):
        return ""
    return f"{d.month}월 {d.day}일 ({_WEEKDAY_KO[d.weekday()]})"


def _domain(url: str) -> str:
    """url → 발행처 도메인 reference (예: 'aitimes.com'). www. 접두 제거."""
    try:
        net = urlparse(url).netloc.lower()
    except ValueError:
        return ""
    return net[4:] if net.startswith("www.") else net


def _source_line(store: SourceStore | None, source_id: str) -> str:
    """📰 도메인 · 발행일 · 원문 → (mono · meta색). store 없거나 미발견이면 빈 문자열."""
    if store is None:
        return ""
    try:
        s = store.get_source(source_id)
    except (FileNotFoundError, ValueError, KeyError):  # 미스·손상·삭제경합 → 빈 줄(방어적)
        return ""
    domain = _domain(s.url)
    date = s.fetched_at[:10] if s.fetched_at else ""
    link = (
        f'<a href="{html.escape(s.url)}" style="color:{_CORAL};text-decoration:underline">원문 →</a>'
        if s.url else ""
    )
    meta = " · ".join(p for p in (f"📰 {html.escape(domain)}" if domain else "", date, link) if p)
    return f'<p style="{_MONO};font-size:12px;color:{_META};margin:2px 0 8px">{meta}</p>'


def _trust_line(card: GatedCard) -> str:
    """검증줄 — "다른 AI 에이전트가 사실 N건 검증" + `<details>` 근거. 개별 claim 텍스트 비노출."""
    n = {k: sum(1 for v in card.verdicts if v.verdict == k) for k in ("VERIFIED", "DEMOTED", "BLOCKED")}
    head = f"사실 {n['VERIFIED']}건 검증" if n["VERIFIED"] else "검증 완료"
    bits = [f"✓ 다른 AI 에이전트가 {head}"]
    if n["DEMOTED"]:
        bits.append(f"미확인 {n['DEMOTED']}건")
    if n["BLOCKED"]:
        bits.append(f"보류 {n['BLOCKED']}건")
    color = _AMBER if (n["DEMOTED"] or n["BLOCKED"]) else _OK
    body = "이 요약을 만든 AI 에이전트와 다른 AI 에이전트가, 요약 속 숫자·주장을 원문과 대조했어요."
    return (
        '<details style="margin:8px 0 0">'
        f'<summary style="font-size:12px;color:{color};cursor:pointer">{" · ".join(bits)} · 근거 보기</summary>'
        f'<p style="font-size:12px;color:{_META};margin:6px 0 0;padding-left:10px;'
        f'border-left:2px solid {_RULE}">{body}</p>'
        "</details>"
    )


def _card_html(card: GatedCard, store: SourceStore | None, *, depth: str, lens: str, rank: int) -> str:
    """카드 1개 — 헤드라인(순위) · 출처줄 · [요약 · 관점] · [점선 + 나에게 왜 중요한가(해석)] · 검증줄. depth 로 밀도."""
    c = card.card
    rank_html = f'<span style="{_MONO};color:{_CORAL};font-weight:700">{rank:02d}</span>  ' if rank else ""
    parts = [
        f'<h2 style="font-size:19px;margin:18px 0 2px">{rank_html}{html.escape(c.headline)}</h2>',
        _source_line(store, c.source_id),
    ]
    if depth != "title-only":  # summary·full → 요약(검증 대상) 노출
        lens_lbl = f"요약 · {html.escape(lens)} 관점" if lens else "요약"
        parts.append(f'<p style="{_MONO};font-size:12px;color:{_META};margin:8px 0 2px">{lens_lbl}</p>')
        parts.append(f'<p style="margin:0">{html.escape(c.summary)}</p>')
    if depth == "full" and c.why_it_matters:  # full → 해석(검증 대상 아님 → 시각 구분)
        parts.append(f'<div style="border-top:1px dotted {_RULE};margin:8px 0"></div>')
        parts.append(
            f'<p style="font-size:12px;color:{_META};margin:0 0 2px">'
            f'나에게 왜 중요한가 <span>(해석)</span></p>'
        )
        parts.append(
            f'<p style="margin:0;font-style:italic;color:#5A514A;'
            f'border-left:2px solid {_CORAL};padding-left:10px">{html.escape(c.why_it_matters)}</p>'
        )
    parts.append(_trust_line(card))
    return "\n".join(p for p in parts if p)


def _band(category: str, count: int) -> str:
    """분야(Area) 밴드 — 이름(700) + mono 건수."""
    return (
        f'<p style="font-weight:700;font-size:15px;margin:20px 0 0">◆ {html.escape(category)} '
        f'<span style="{_MONO};font-weight:400;color:{_META};font-size:12px">{count}건</span></p>'
        f'<div style="border-top:1px solid {_RULE};margin:4px 0 0"></div>'
    )


def render_email(
    cards: Sequence[GatedCard],
    user: UserConfig,
    settings: Settings,
    store: SourceStore | None = None,
    *,
    source_categories: Mapping[str, str] | None = None,
    today: str | None = None,
) -> str:
    """PUBLISH 카드만 → 검증 명세서 HTML 이메일.

    source_categories: source_id → 분야(category). 발행 카드가 **2개 이상 분야**에 걸치면 밴드로 그룹(번호 분야별 리셋),
    아니면 평평(전역 번호). today: 헤더 날짜(없으면 생략). 0건이면 폴백.
    """
    published = [c for c in cards if c.decision == "PUBLISH"]
    lens = getattr(user, "lens", "") or ""
    depth = getattr(user, "depth", "full") or "full"

    # ── 분야 그룹: 발행 카드의 distinct category(첫 등장 순서) ──
    cats = source_categories or {}
    distinct: list[str] = []
    for g in published:
        ct = cats.get(g.card.source_id, "")
        if ct and ct not in distinct:
            distinct.append(ct)
    grouped = len(distinct) >= 2

    # ── 헤더(인장 · 날짜; user.id 비노출) ──
    title = "오늘의 브리핑" + (f" · {html.escape(today)}" if today else "")
    seal = (
        f'<span style="{_MONO};font-size:12px;color:{_OK};border:1px solid {_RULE};'
        'border-radius:6px;padding:2px 8px">✓ 원문 대조 완료</span>'
    )
    header = (
        '<div style="display:flex;justify-content:space-between;align-items:baseline">'
        f'<h1 style="font-size:22px;margin:0">{title}</h1>{seal}</div>'
    )
    if not published:
        return (
            _WRAP + header
            + '<p style="margin:14px 0">오늘은 검증을 통과한 새 소식이 없습니다. '
            "(확인되지 않은 항목은 보내지 않았어요.)</p></div>"
        )

    area_prefix = f"{len(distinct)}개 분야 · " if grouped else ""
    subtitle = (
        f'<p style="{_MONO};font-size:12px;color:{_META};margin:4px 0 0">'
        f"{area_prefix}소식 {len(published)}개 · {html.escape(lens)} 관점 요약 · "
        "요약 후 다른 AI 에이전트가 원문 대조</p>"
    )
    coral_rule = f'<div style="border-top:2px solid {_CORAL};margin:10px 0 4px"></div>'

    if grouped:
        sections = []
        for ct in distinct:
            members = [g for g in published if cats.get(g.card.source_id, "") == ct]
            cards_html = "\n".join(
                _card_html(g, store, depth=depth, lens=lens, rank=i) for i, g in enumerate(members, 1)
            )
            sections.append(_band(ct, len(members)) + "\n" + cards_html)
        body = "\n".join(sections)
    else:
        body = "\n".join(
            _card_html(g, store, depth=depth, lens=lens, rank=i) for i, g in enumerate(published, 1)
        )

    send_hour = getattr(user, "send_hour", 7)
    footer = (
        f'<div style="border-top:2px solid {_RULE};margin:22px 0 0;padding-top:10px;'
        f'font-size:12px;color:{_META}">'
        f'<p style="margin:0 0 6px">이 브리핑은 어떻게 만드나요? — AI 에이전트가 원문 기사를 '
        f"{html.escape(lens)} 관점으로 요약하면, 요약을 만들지 않은 다른 AI 에이전트가 그 요약을 "
        "원문과 대조해 확인합니다. 확인되지 않은 내용은 보내지 않습니다.</p>"
        f'<p style="margin:0">다음 브리핑 내일 {int(send_hour):02d}:00 · 관점 바꾸기 · 구독 해지</p></div>'
    )
    return _WRAP + header + subtitle + coral_rule + body + footer + "</div>"
