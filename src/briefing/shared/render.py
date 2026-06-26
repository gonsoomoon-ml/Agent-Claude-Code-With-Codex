"""render — PUBLISH 카드 → 사용자 이메일(Smart Brevity) + 신뢰 칩(verdict chip).

- **decision == "PUBLISH" 카드만** 이메일에 — QUARANTINE 카드는 *사용자 이메일이 아니라* 사람-검토 큐로(별도).
- PUBLISH 카드엔 BLOCKED claim 이 없다(루프가 BLOCKED → QUARANTINE 으로 보냄) → 칩은 VERIFIED/DEMOTED 만.
- DEMOTED 는 '(미확인)' 라벨로 *남김*(조용한 드롭 금지 = show your work). DEPTH(user.depth)로 밀도 조절.
"""
from __future__ import annotations

from collections.abc import Sequence

from .config import Settings, UserConfig
from .gate import GatedCard


def render_email(cards: Sequence[GatedCard], user: UserConfig, settings: Settings) -> str:
    """PUBLISH 카드만 → HTML 이메일 (user.depth 로 밀도; QUARANTINE 제외 — 사람 검토).

    TODO: `decision == "PUBLISH"` 필터 · Smart Brevity 템플릿 · verdict 칩(VERIFIED/DEMOTED) · DEPTH 분기 · 차분 톤.
    TODO: QUARANTINE 행선지(사람-검토 큐/알림)는 *별도* · 0건 발행 시 폴백(빈 메일 금지).
    """
    raise NotImplementedError("email render — 구현 예정")
