"""webapi.build_catalog — 폼용 카탈로그 JSON(순수). CATALOG/LENS_LIBRARY 재사용 + category 폴백."""
from __future__ import annotations

from briefing.webapi.catalog import MAX_SOURCES, SEND_HOURS, build_catalog


def test_catalog_groups_under_jeonche_fallback_when_no_category():
    # Source 에 category 필드가 아직 없음(H2 전) → 단일 "전체" 그룹.
    cat = build_catalog()
    assert [g["name"] for g in cat["categories"]] == ["전체"]
    keys = [s["key"] for g in cat["categories"] for s in g["sources"]]
    assert "aitimes" in keys and "anthropic" in keys      # CATALOG 전부 노출
    assert len(keys) == len(set(keys))                     # 중복 0


def test_each_source_exposes_key_name_lang_only():
    src = build_catalog()["categories"][0]["sources"][0]
    assert set(src) == {"key", "name", "lang"}             # url/kind/fragile 은 UI 에 노출 안 함


def test_form_constraints_present():
    cat = build_catalog()
    assert cat["send_hours"] == [6, 7, 8] == list(SEND_HOURS)
    assert cat["max_sources"] == 5 == MAX_SOURCES
    assert set(cat["depths"]) == {"title-only", "summary", "full"}


def test_lenses_include_general():
    keys = [ln["key"] for ln in build_catalog()["lenses"]]
    assert "general" in keys
