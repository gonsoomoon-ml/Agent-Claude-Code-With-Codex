"""policy — role→능력 매핑의 단일 지점 (판별=claims · 능력=여기 · 집행=route 3분리).

향후 관리 능력(사용자 조회·강제 재발송 등)은 이 파일에 함수 하나씩 추가된다.
role 은 webapi 밖으로 나가지 않는다 — core/gate/certifier 는 role 의 존재를 모른다(스펙 §4).
"""
from __future__ import annotations

from ..core.retrieval.sources import CATALOG
from .catalog import MAX_SOURCES


def max_sources(is_admin: bool) -> int:
    """출처 선택 상한. admin 의 '무제한' = 카탈로그 전체 — 실행 시간·비용의 자연 상한."""
    return len(CATALOG) if is_admin else MAX_SOURCES
