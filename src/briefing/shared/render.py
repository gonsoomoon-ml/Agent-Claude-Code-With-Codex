"""render — PUBLISH 카드 → 사용자 이메일(Smart Brevity) + 신뢰 칩(verdict chip).

- **decision == "PUBLISH" 카드만** 이메일에 — QUARANTINE 카드는 사람-검토 큐(별도, 표본 감사).
- graceful degradation: PUBLISH 카드에 BLOCKED claim 이 *있을 수 있음* → render 가 그 claim 을 **드롭** + '보류' 표시(칩은 VERIFIED/DEMOTED).
- DEMOTED 는 '(미확인)' 라벨로 *남김*(조용한 드롭 금지 = show your work). DEPTH(user.depth)로 밀도 조절.

순수 함수(LLM·AWS 불필요) — 단위 테스트 가능.
"""
from __future__ import annotations

import html
from collections.abc import Sequence

from .certifier import CertVerdict
from .config import Settings, UserConfig
from .gate import GatedCard

_CHIP = {
    "VERIFIED": '<span style="color:#0a0">✓ 검증됨</span>',
    "DEMOTED": '<span style="color:#a60">⚠ (미확인)</span>',
}


def _chip(v: CertVerdict) -> str:
    return _CHIP.get(v.verdict, "")


def _card_html(card: GatedCard, *, depth: str) -> str:
    c = card.card
    by_id = {v.claim_id: v for v in card.verdicts}
    parts = [f"<h2>{html.escape(c.headline)}</h2>"]
    parts.append(f'<p><strong>왜 중요한가:</strong> {html.escape(c.why_it_matters)}</p>')
    if depth != "brief":
        parts.append(f"<p>{html.escape(c.summary)}</p>")
        items = []
        dropped = 0
        for cl in c.claims:
            v = by_id.get(cl.id)
            if v is not None and v.verdict == "BLOCKED":
                dropped += 1  # graceful degradation: 미검증 claim 은 발행에서 드롭(fail-closed)
                continue
            items.append(f"<li>{html.escape(cl.text)} {_chip(v) if v else ''}</li>")
        if items:
            parts.append("<ul>" + "".join(items) + "</ul>")
        if dropped:
            parts.append(f'<p style="color:#888"><em>※ 미확인 {dropped}개 항목은 보류했습니다.</em></p>')
    return "\n".join(parts)


def render_email(cards: Sequence[GatedCard], user: UserConfig, settings: Settings) -> str:
    """PUBLISH 카드만 → HTML 이메일 (user.depth 로 밀도; QUARANTINE 제외 — 사람 검토).

    0건 발행 시 빈 메일 금지 — 폴백 문구. QUARANTINE 행선지(사람 검토 큐)는 *별도*(여기서 제외만).
    """
    published = [c for c in cards if c.decision == "PUBLISH"]
    header = f"<h1>오늘의 브리핑 — {html.escape(user.id)}</h1>"
    if not published:
        return header + "<p>오늘은 검증을 통과한 새 항목이 없습니다. (보류 항목은 사람 검토 큐로 이동했습니다.)</p>"
    body = "\n<hr>\n".join(_card_html(c, depth=user.depth) for c in published)
    return header + "\n" + body
