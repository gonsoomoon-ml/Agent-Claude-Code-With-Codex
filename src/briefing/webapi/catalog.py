"""build_catalog — CATALOG·LENS_LIBRARY → 프론트 폼용 JSON.

category 미존재(H2 전) 시 단일 '전체' 그룹 폴백 — getattr 로 frozen Source 에 미래 필드를
forward-compat 소비(도착 시 코드 변경 0). 원 url/kind/fragile 은 UI 에 노출하지 않는다 — 단
파생 homepage(https://host)만 노출(XML 엔드포인트 안 샘).
"""
from __future__ import annotations

from urllib.parse import urlparse

from ..core.lenses import LENS_LIBRARY
from ..core.retrieval.sources import CATALOG

SEND_HOURS = (6, 7, 8)              # KST 발송 시각 옵션(폼 라디오)
DEPTHS = ("title-only", "summary", "full")
MAX_SOURCES = 5                    # 출처 선택 상한
_FALLBACK_CATEGORY = "전체"         # Source.category 미존재 시(H2, LANE-A)


def _homepage(url: str) -> str | None:
    """fetch/feed URL 에서 사람이 볼 홈페이지 파생 — https://<hostname>. RSS XML 경로는 버린다(호스트만)."""
    host = urlparse(url).hostname
    return f"https://{host}" if host else None


def build_catalog() -> dict:
    groups: dict[str, list[dict]] = {}
    order: list[str] = []          # 카탈로그 순서 보존(결정론)
    for s in CATALOG:
        cat = getattr(s, "category", "") or _FALLBACK_CATEGORY
        if cat not in groups:
            groups[cat] = []
            order.append(cat)
        d = {"key": s.key, "name": s.name, "lang": s.lang}
        hp = _homepage(s.url)
        if hp:
            d["homepage"] = hp
        groups[cat].append(d)
    return {
        "categories": [{"name": c, "sources": groups[c]} for c in order],
        "lenses": [{"key": ln.key, "name": ln.name} for ln in LENS_LIBRARY],
        "depths": list(DEPTHS),
        "send_hours": list(SEND_HOURS),
        "max_sources": MAX_SOURCES,
    }
