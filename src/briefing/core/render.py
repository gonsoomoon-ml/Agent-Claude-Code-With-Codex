"""render — PUBLISH 카드 → "검증 명세서(Verified Dispatch)" 이메일.

디자인(`design/ux/email-ux-mockup.md`):
- 카드 = **요약(검증 대상) → 점선 → 사실들을 엮으면(해석, 시각 구분) → 검증줄**. depth 로 밀도(title-only/summary/full).
- 검증줄 = **"다른 AI 에이전트가 사실 N건 검증"** (decorrelation 을 평이하게) + `<details>` 근거. 개별 claim 텍스트는 비노출(불변식).
- 분야(Area) 밴드 = **카드별 주제 라벨**(`card_areas`, 공용 `areas.AREAS` 6칸·순서, 2026-10-24 결정) — 보이는 카드 전부에
  라벨이 있을 때만 그린다(1장 칸 허용·빈 칸 숨김·칸 안은 입력 순서=카탈로그 순·번호 칸별 리셋). 없거나 불완전하면
  **평평**(핵심 3 있으면 단일 밴드 `요약 N건`, 없으면 밴드 머리 없음) — 메일 모양은 이 둘뿐, 발행처 밴드는 없다.
- 출처 집계 줄 = `출처 · {category} {n} · …`(카탈로그 순, 0 생략, 핵심 3·⚠ 포함) — `source_categories` 는 이제 이 줄 전용.
- PUBLISH 카드 + QUARANTINE 카드(⚠ 확인 못 함 표시, N5) · 0건이면 폴백. 순수 함수(LLM·AWS 불필요), 이메일 클라이언트용 인라인 CSS.
  격리 카드도 싣는 이유(2026-10-18 사용자 결정): 법률·금융·보안이 아닌 비중요 브리핑이라 빼는 쪽이 손해다
  (30일 감사: 숫자 검사가 막은 claim 64건 중 틀린 것 0건). 대신 검증된 카드처럼 보이면 안 된다 — 검증줄이 밝힌다.
"""
from __future__ import annotations

import datetime
import html
from collections.abc import Mapping, Sequence
from urllib.parse import urlparse

from .config import Settings, UserConfig
from .gate import GatedCard
from .lenses import lens_label
from .areas import AREAS
from .retrieval import sources as src
from .retrieval.headlines import Headline
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


def briefing_date(run_date: str, sent_at: datetime.datetime | None, tz: str) -> str:
    """메일 머리 날짜 — sent_at(발송 시각)을 받는 사람 시간대(tz)로 바꾼 날짜. sent_at 이 없으면 run_date.

    왜: run_date 는 발송 기록·중복 방지의 UTC 날짜 키다. 05:00 KST 발송은 전날 20:00 UTC 라 run_date 를 그대로
    찍으면 하루 전 날짜가 나간다(2026-10-18 일요일 메일에 "10월 17일 (토)"). naive datetime 은 UTC 로 본다.
    """
    if sent_at is None:
        return format_briefing_date(run_date)
    from zoneinfo import ZoneInfo   # lazy — render 의 다른 경로엔 불필요
    if sent_at.tzinfo is None:
        sent_at = sent_at.replace(tzinfo=datetime.timezone.utc)
    return format_briefing_date(sent_at.astimezone(ZoneInfo(tz or "Asia/Seoul")).date().isoformat())


def _domain(url: str) -> str:
    """url → 발행처 도메인 reference (예: 'aitimes.com'). www. 접두 제거."""
    try:
        net = urlparse(url).netloc.lower()
    except ValueError:
        return ""
    return net[4:] if net.startswith("www.") else net


def _source_line(store: SourceStore | None, source_id: str) -> str:
    """📰 도메인 · 발행일 · 원문 → (mono · meta색). store 없거나 미발견이면 빈 문자열.

    원제목은 **h2(카드 제목)** 로 노출된다(사실층 앵커=기사 원제목) — 출처줄엔 provenance(도메인·날짜·원문 링크)만.
    (예전엔 원제목을 출처줄에 말줄임으로 병기했으나, 제목=기사 원제목 아키텍처로 h2 로 승격 → 중복·2줄 스캔 제거.)
    """
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
    meta = " · ".join(p for p in (
        f"📰 {html.escape(domain)}" if domain else "",
        date,
        link,
    ) if p)
    return f'<p style="{_MONO};font-size:12px;color:{_META};margin:2px 0 8px">{meta}</p>'


def _trust_line(card: GatedCard) -> str:
    """검증줄 — 펼침 없는 정직한 한 줄(ii). 확인 N + (미확인 M) + (제외 K) 집계만.

    아침 스캔용 glance 신호 — per-claim 감사는 안 넣는다(대부분 안 펼침 + 모닝 calm).
    더 깊이는 카드의 '원문 →' 링크 / 주간 'Withheld-and-Why' 다이제스트(후속)로. 개별 claim 텍스트 비노출.
    """
    n = {k: sum(1 for v in card.verdicts if v.verdict == k) for k in ("VERIFIED", "DEMOTED", "BLOCKED")}
    if card.decision == "QUARANTINE":
        # 격리 카드(N5) — '✓ … 검증' 문구를 붙이지 않는다(검증된 카드처럼 보이면 안 된다).
        # 확인 못 한 사실 = BLOCKED + DEMOTED — 둘 다 원문에서 확인되지 않았다.
        bits = [f"⚠ 요약의 사실 {n['BLOCKED'] + n['DEMOTED']}건을 원문에서 확인하지 못함"]
        if n["VERIFIED"]:
            bits.append(f"확인 {n['VERIFIED']}건")
        return f'<p style="font-size:12px;color:{_AMBER};margin:8px 0 0">{" · ".join(bits)}</p>'
    # "요약의" = 검증 범위 정직화(card-layering §5) — 배지는 요약(사실층)만 커버, 해석(관점)은 라벨로 구분.
    bits = [f"✓ 다른 AI 에이전트가 요약의 사실 {n['VERIFIED']}건 검증" if n["VERIFIED"] else "✓ 검증 완료"]
    if n["DEMOTED"]:
        bits.append(f"미확인 {n['DEMOTED']}건")
    if n["BLOCKED"]:
        bits.append(f"제외 {n['BLOCKED']}건")  # F4 이전 캐시 카드(PUBLISH + BLOCKED 잔존)용 — 새 카드는 BLOCKED 가 남으면 QUARANTINE(⚠)
    color = _AMBER if (n["DEMOTED"] or n["BLOCKED"]) else _OK
    return f'<p style="font-size:12px;color:{color};margin:8px 0 0">{" · ".join(bits)}</p>'


def _card_html(card: GatedCard, store: SourceStore | None, *, depth: str, lens: str, rank: int) -> str:
    """카드 1개 — 원제목(순위·h2=기사 제목) · 출처줄 · [요약 · 원문 사실] · [점선 + 사실들을 엮으면(해석)] · 검증줄. depth 로 밀도."""
    c = card.card
    rank_html = f'<span style="{_MONO};color:{_CORAL};font-weight:700">{rank:02d}</span>  ' if rank else ""
    parts = [
        f'<h2 style="font-size:19px;margin:18px 0 2px">{rank_html}{html.escape(c.headline)}</h2>',
        _source_line(store, c.source_id),
    ]
    # 요약(검증 대상) — 모든 depth 노출 (mockup §4: title-only 도 요약은 보인다)
    # 2층화: 요약 라벨에서 lens 제거(공통 사실층) — 개인화 라벨은 해석 블록으로 재정박(UX 채택 조건).
    parts.append(f'<p style="{_MONO};font-size:12px;color:{_META};margin:8px 0 2px">요약 · 원문 사실</p>')
    parts.append(f'<p style="margin:0">{html.escape(c.summary)}</p>')
    if depth != "title-only" and c.why_it_matters:  # summary·full → 해석(title-only 만 생략, 시각 구분)
        # 라벨 = "사실들을 엮으면"(2026-07-28). 이전 "나에게 왜 중요한가"는 **지킬 수 없는 약속**이었다:
        # 해석층이 독자에 대해 아는 것은 lens 하나뿐이고(캐시 키가 (source,lens) 코호트 공유라
        # 개인 정보가 들어갈 수 없다), 그래서 산출의 75%가 일반론이었다(2026-07-28 감사, n=40).
        # 새 라벨은 위 "요약 · 원문 사실"과 쌍을 이룬다 — 위는 사실을 나열, 아래는 그 사실을 엮는다.
        # lens 는 남긴다: 어떤 관계를 고를지를 정하고, 제품의 핵심 사용자 대면 기능이다.
        why_lbl = f"사실들을 엮으면 · {html.escape(lens)} 관점" if lens else "사실들을 엮으면"
        parts.append(f'<div style="border-top:1px dotted {_RULE};margin:8px 0"></div>')
        parts.append(
            f'<p style="font-size:12px;color:{_META};margin:0 0 2px">'
            f'{why_lbl} <span>(해석)</span></p>'
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


def _valid_headlines(headlines: Sequence[Headline]) -> list[Headline]:
    """http(s) 링크만 — 칸과 부제 개수가 같은 목록을 센다(javascript: 등은 버림)."""
    return [h for h in headlines if urlparse(h.url).scheme in ("http", "https")]


def _headlines_html(headlines: Sequence[Headline]) -> str:
    """헤드라인 칸 — 제목·링크 전용 소스(본문 미수집). 메일 맨 위(오늘의 핵심 3 위), 검증 카드와 상자로 구분한다.

    원제목을 그대로 싣는다(재작성·요약 없음). http(s) 가 아닌 링크는 버린다(javascript: 등).
    매체가 하나면 칸 제목에 한 번만 쓰고, 여럿일 때만 줄마다 붙인다. 모든 줄에 분야가 있으면 AREAS 순서의
    소제목으로 나누고(빈 분야 숨김, 분야 안은 선별 순서), 하나라도 없으면 소제목 없이 한 목록. 지역(국내/해외)은 표시하지 않는다.
    """
    ok = _valid_headlines(headlines)
    if not ok:
        return ""
    media = list(dict.fromkeys(h.media for h in ok))
    per_row = len(media) > 1

    def _ul(rows: Sequence[Headline]) -> str:
        items = "".join(
            f'<li style="margin:3px 0"><a href="{html.escape(h.url, quote=True)}" style="color:{_INK}">'
            f"{html.escape(h.title)}</a>"
            + (f' <span style="{_MONO};font-size:11px;color:{_META}">{html.escape(h.media)}</span>' if per_row else "")
            + "</li>"
            for h in rows
        )
        return f'<ul style="margin:4px 0 0;padding-left:18px;font-size:13px;line-height:1.5">{items}</ul>'

    if all(h.area in AREAS for h in ok):   # 분야 순서 고정(공용 6칸) — 빈 분야는 소제목째 숨김
        body = ""
        for area in AREAS:
            rows = [h for h in ok if h.area == area]
            if rows:
                body += (f'<p style="font-size:12px;font-weight:700;color:{_META};margin:8px 0 0">'
                         f"{html.escape(area)} {len(rows)}</p>" + _ul(rows))
    else:
        body = _ul(ok)
    label = f"{html.escape(media[0])} " if not per_row else ""
    return (
        f'<div style="border:1px solid {_RULE};border-radius:8px;padding:8px 12px;margin:12px 0 4px">'
        f'<p style="font-weight:700;font-size:14px;margin:0">◇ {label}헤드라인 '
        f'<span style="{_MONO};font-weight:400;color:{_META};font-size:12px">'
        f"{len(ok)}건 · 요약·검증 없음 — 제목과 원문 링크만</span></p>{body}</div>"
    )


def _tally_line(shown: Sequence[GatedCard], cats: Mapping[str, str]) -> str:
    """출처 집계 줄 — `출처 · Amazon (AWS) 7 · Anthropic 6 · …`. 발행처 블록이 사라진 자리를 한 줄로(2026-10-24 결정 2-B).

    대상 = 보이는 카드 전부(핵심 3·⚠ 포함). 순서 = 카탈로그의 category 첫 등장 순서(= 섹션 순서), 0 은 생략,
    카탈로그에 없는 category(구 카드·테스트 fixture)는 생략. 전부 모르면 ""(줄 자체 생략). 결정론 — 라벨 실패 날에도 그린다.
    """
    counts: dict[str, int] = {}
    for g in shown:
        if ct := cats.get(g.card.source_id, ""):
            counts[ct] = counts.get(ct, 0) + 1
    order = list(dict.fromkeys(x.category for x in src.CATALOG))
    bits = [f"{html.escape(ct)} {counts[ct]}" for ct in order if ct in counts]
    return f"출처 · {' · '.join(bits)}" if bits else ""


def render_email(
    cards: Sequence[GatedCard],
    user: UserConfig,
    settings: Settings,
    store: SourceStore | None = None,
    *,
    source_categories: Mapping[str, str] | None = None,
    today: str | None = None,
    headlines: Sequence[Headline] = (),
    top_picks: Sequence[str] = (),
    card_areas: Mapping[str, str] | None = None,
) -> str:
    """PUBLISH 카드 + QUARANTINE 카드(⚠ 확인 못 함 표시) → 검증 명세서 HTML 이메일.

    source_categories: source_id → 카탈로그 category — **출처 집계 줄 전용**(밴드 키 아님, 2026-10-24).
    card_areas: source_id → 분야(areas.AREAS). 보이는 카드 **전부**에 유효한 분야가 있을 때만 분야 밴드(AREAS 순,
      빈 칸 숨김, 1장 칸 허용, 칸 안은 입력 순서 유지, 번호 칸별 리셋). 없거나 한 장이라도 빠지면 평평 폴백 —
      핵심 3 이 있으면 나머지를 단일 밴드 `요약 N건`(전역 번호)으로, 없으면 밴드 머리 없이. 발행처 밴드로는 돌아가지 않는다.
    today: 헤더 날짜(없으면 생략). 0건이면 폴백.
    headlines: 제목·링크 전용 소스의 헤드라인 — 맨 위 별도 상자(아침에 먼저 훑는 칸, 핵심 3 위). 카드가 0건이면 싣지 않는다(헤드라인만으론 브리핑 아님).
    top_picks: 오늘의 핵심 3 으로 올릴 카드의 source_id(순서 = 판정 순서). 맨 앞 칸에 싣고 원래 분야 밴드에서는 뺀다
      (중복 없음). 모르는 id 는 무시. 핵심 칸이 있으면 나머지는 분야가 하나여도 밴드로 구분한다.
    """
    # 검증 카드 + 격리 카드(⚠ 표시, N5) — 순서는 파이프라인이 준 그대로(분야·핵심 3 규칙은 아래에서 같게 적용)
    shown = [c for c in cards if c.decision in ("PUBLISH", "QUARANTINE")]
    lens = getattr(user, "lens", "") or ""
    lens = lens_label(lens) if lens else ""   # 표시 = 영문 이름(engineer → Engineer); 키는 프로필 그대로
    depth = getattr(user, "depth", "full") or "full"

    # ── 분야 밴드 가능 여부: 보이는 카드 전부에 유효한 주제 라벨(all-or-nothing — 일부만 묶으면 나머지가 섞여 보인다) ──
    areas = card_areas or {}
    areas_ok = bool(shown) and all(areas.get(g.card.source_id) in AREAS for g in shown)
    tally = _tally_line(shown, source_categories or {})

    # ── 헤더(인장 · 날짜; user.id 비노출) ──
    title = "오늘의 브리핑" + (f" · {html.escape(today)}" if today else "")
    heads_html = _headlines_html(headlines) if shown else ""
    # 인장 = 검증 범위(요약) + 누가(요약을 만들지 않은 다른 AI). 요약이 있는 것은 카드뿐이라 헤드라인 칸(요약·검증
    # 없음)이 위에 있어도 범위가 저절로 맞고, 해석까지 원문 대조한 것처럼 읽히지 않는다(검증줄 "요약의 사실 N건"과 같은 범위).
    seal_text = "✓ 요약은 다른 AI 에이전트가 원문 대조"
    seal = (
        f'<span style="{_MONO};font-size:12px;color:{_OK};border:1px solid {_RULE};'
        f'border-radius:6px;padding:2px 8px;white-space:nowrap">{seal_text}</span>'
    )
    header = (
        '<div style="display:flex;flex-wrap:wrap;gap:4px 10px;'
        'justify-content:space-between;align-items:baseline">'
        f'<h1 style="font-size:22px;margin:0">{title}</h1>{seal}</div>'
    )
    if not shown:
        return (
            _WRAP + header
            + '<p style="margin:14px 0">오늘은 전할 새 소식이 없습니다.</p></div>'
        )

    # 부제 = 콘텐츠(개수·관점)만, 메일 순서대로 헤드라인 → 요약 — 검증 문구는 인장·카드 검증줄·푸터가 소유(중복 제거).
    # "요약 N건"(≠ "카드 N장": 카드는 내부 용어) — 인장 "요약은…"·카드 라벨 "요약 · 원문 사실"과 같은 말.
    # 분야 수는 뺐다(2026-10-18): 헤드라인 칸의 분야(AI Agents…)와 뜻이 겹치고, 핵심 3 으로 밴드 수와 어긋난다.
    # "관점 해석"(≠ 관점 요약) — 2층화 후 lens 가 소유하는 것은 해석이므로 카피도 그렇게 말한다.
    n_heads = len(_valid_headlines(headlines)) if heads_html else 0
    bits = ([f"헤드라인 {n_heads}건"] if n_heads else []) + [f"요약 {len(shown)}건"] \
        + ([f"{html.escape(lens)} 관점 해석"] if lens else [])
    subtitle = f'<p style="{_MONO};font-size:12px;color:{_META};margin:4px 0 0">{" · ".join(bits)}</p>'
    if tally:   # 출처 집계 줄 — 부제 바로 아래, 같은 모노 스타일(발행처 블록 대신 "한눈 개수")
        subtitle += f'<p style="{_MONO};font-size:12px;color:{_META};margin:2px 0 0">{tally}</p>'
    coral_rule = f'<div style="border-top:2px solid {_CORAL};margin:10px 0 4px"></div>'

    def _cards(members: Sequence[GatedCard]) -> str:
        return "\n".join(_card_html(g, store, depth=depth, lens=lens, rank=i) for i, g in enumerate(members, 1))

    # ── 오늘의 핵심 3: 판정 순서대로 맨 앞 칸, 원래 밴드에서는 뺀다. 부제("요약 N건")는 발행 카드 전체 기준(핵심 포함) ──
    by_sid: dict[str, GatedCard] = {}
    for g in shown:
        if g.decision == "PUBLISH":   # 핵심 3 은 검증된 카드만(N5) — 격리 카드는 id 가 와도 원래 자리에 남는다
            by_sid.setdefault(g.card.source_id, g)
    top = [by_sid[sid] for sid in dict.fromkeys(top_picks) if sid in by_sid]
    top_ids = {g.card.source_id for g in top}
    rest = [g for g in shown if g.card.source_id not in top_ids]
    top_html = (_band("오늘의 핵심", len(top)) + "\n" + _cards(top)) if top else ""

    # 밴드 = 남은 카드의 분야(AREAS 순서) — 카드가 전부 핵심으로 올라간 분야는 0건 밴드를 그리지 않는다. 칸 안 순서는
    # 입력 순서 그대로(파이프라인이 카탈로그 순으로 준다 — 공식 채널 먼저·보도 뒤·AWS 맨 위). 정렬하지 않는다.
    if areas_ok:
        body = "\n".join(
            _band(a, len(members)) + "\n" + _cards(members)
            for a in AREAS
            if (members := [g for g in rest if areas[g.card.source_id] == a])
        )
    elif top:   # 폴백 + 핵심 3: 나머지를 한 덩어리로("요약" = 부제·인장의 어휘; "소식"은 헤드라인과 겹쳐 모호 — 2026-10-18)
        body = _band("요약", len(rest)) + "\n" + _cards(rest)
    else:       # 폴백 + 핵심 없음: 밴드 머리 없이 평평(전역 번호)
        body = _cards(rest)

    heads_note = (" 헤드라인 칸은 요약·검증 없이 제목과 원문 링크만 옮긴 것입니다." if heads_html else "")
    send_hour = getattr(user, "send_hour", 7)
    footer = (
        f'<div style="border-top:2px solid {_RULE};margin:22px 0 0;padding-top:10px;'
        f'font-size:12px;color:{_META}">'
        f'<p style="margin:0 0 6px">이 브리핑은 어떻게 만드나요? — AI 에이전트가 원문 기사를 '
        "요약하면, 요약을 만들지 않은 다른 AI 에이전트가 그 요약을 원문과 대조해 확인하고, "
        f"확인된 사실을 근거로 {html.escape(lens)} 관점의 해석을 덧붙입니다. "
        f"원문에서 확인하지 못한 사실이 있는 요약에는 ⚠ 표시를 붙입니다.{heads_note}</p>"
        f'<p style="margin:0">다음 브리핑 내일 {int(send_hour):02d}:00 · 관점 바꾸기 · 구독 해지</p></div>'
    )
    # 순서: 헤드라인 칸 → 오늘의 핵심 3 → 분야 밴드(AREAS 순) 또는 평평(2026-10-24 결정; 발행처 섹션은 2026-10-24 까지)
    return _WRAP + header + subtitle + coral_rule + heads_html + top_html + body + footer + "</div>"
