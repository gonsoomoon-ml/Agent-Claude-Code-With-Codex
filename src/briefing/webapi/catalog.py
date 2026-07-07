"""build_catalog — CATALOG·LENS_LIBRARY → 프론트 폼용 JSON.

category 미존재(H2 전) 시 단일 '전체' 그룹 폴백 — getattr 로 frozen Source 에 미래 필드를
forward-compat 소비(도착 시 코드 변경 0). 원 url/kind/fragile 은 UI 에 노출하지 않는다 — 단
사람이 볼 homepage 만 노출(피드/XML 엔드포인트 안 샘 — test_no_source_leaks_feed_or_xml_url 로 강제).
"""
from __future__ import annotations

from urllib.parse import urlparse

from ..core.lenses import LENS_LIBRARY
from ..core.retrieval.sources import CATALOG, Source

SEND_HOURS = (6, 7, 8)              # KST 발송 시각 옵션(폼 라디오)
DEPTHS = ("title-only", "summary", "full")
MAX_SOURCES = 5                    # 출처 선택 상한
_FALLBACK_CATEGORY = "전체"         # Source.category 미존재 시(H2, LANE-A)


def _homepage(s: Source) -> str | None:
    """사람이 볼 랜딩 URL. 우선순위: ① 명시적 homepage 오버라이드 → ② html 출처는 url 자체(랜딩 페이지)
    → ③ rss 출처는 호스트만(url 이 XML 피드라 경로 버림). ③은 피드 호스트가 회사 대문일 수 있어(aws-ml) ①로 보정."""
    if s.homepage:
        return s.homepage
    if s.kind in ("html", "auto"):
        return s.url                 # html 출처의 url = 리스팅/랜딩 페이지 = 그대로 사람용
    host = urlparse(s.url).hostname  # rss: url 은 피드 → 호스트만
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
        hp = _homepage(s)
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
