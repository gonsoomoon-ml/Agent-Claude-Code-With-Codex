"""webapi.build_catalog — 폼용 카탈로그 JSON(순수). CATALOG/LENS_LIBRARY 재사용 + category 그룹핑(폴백 포함)."""
from __future__ import annotations

from briefing.webapi.catalog import MAX_SOURCES, SEND_HOURS, build_catalog


def test_catalog_groups_by_category():
    # H2(LANE-A) 적용 → category 별 그룹(폴백 "전체" 아님). catalog_categories() 와 일치(데이터 주도).
    from briefing.core.retrieval.sources import catalog_categories

    cat = build_catalog()
    assert {g["name"] for g in cat["categories"]} == set(catalog_categories())
    keys = [s["key"] for g in cat["categories"] for s in g["sources"]]
    assert "aitimes" in keys and "anthropic" in keys      # CATALOG 전부 노출
    assert len(keys) == len(set(keys))                     # 중복 0


def test_each_source_exposes_expected_fields():
    src = build_catalog()["categories"][0]["sources"][0]
    assert set(src) == {"key", "name", "lang", "homepage"}   # 파생 homepage 노출, 원 url/kind/fragile 은 미노출


def test_homepage_rss_uses_hostname():
    # RSS 출처: url 이 XML 피드라 호스트명으로 파생(경로 없음)
    srcs = {s["key"]: s for g in build_catalog()["categories"] for s in g["sources"]}
    assert srcs["aitimes"]["homepage"] == "https://www.aitimes.com"    # aitimes.com/rss/allArticle.xml → root


def test_homepage_html_uses_source_url():
    # HTML 출처: url 이 곧 사람이 볼 랜딩 페이지 → 그대로 노출(발행처 경로 보존)
    srcs = {s["key"]: s for g in build_catalog()["categories"] for s in g["sources"]}
    assert srcs["anthropic"]["homepage"] == "https://www.anthropic.com/news"
    assert srcs["anthropic-eng"]["homepage"] == "https://www.anthropic.com/engineering"
    assert srcs["claude-blog"]["homepage"] == "https://claude.com/blog"
    # 두 anthropic 카드가 서로 다른 발행처로 링크(충돌 해소)
    assert srcs["anthropic"]["homepage"] != srcs["anthropic-eng"]["homepage"]


def test_homepage_explicit_override_wins():
    # aws-ml: RSS 피드 url 의 호스트(aws.amazon.com)는 회사 대문 → catalog 의 명시적 homepage 로 실제 블로그 지정
    srcs = {s["key"]: s for g in build_catalog()["categories"] for s in g["sources"]}
    assert srcs["aws-ml"]["homepage"] == "https://aws.amazon.com/blogs/machine-learning/"


def test_no_source_leaks_feed_or_xml_url():
    for g in build_catalog()["categories"]:
        for s in g["sources"]:
            assert ".xml" not in s["homepage"] and "/rss" not in s["homepage"] and "/feed" not in s["homepage"]


def test_form_constraints_present():
    cat = build_catalog()
    assert cat["send_hours"] == [6, 7, 8] == list(SEND_HOURS)
    assert cat["max_sources"] == 5 == MAX_SOURCES
    assert set(cat["depths"]) == {"title-only", "summary", "full"}


def test_lenses_include_general():
    keys = [ln["key"] for ln in build_catalog()["lenses"]]
    assert "general" in keys
