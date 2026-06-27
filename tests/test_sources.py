"""sources — CATALOG 로드/검증 + per-user 선택."""
import tempfile
from pathlib import Path

import pytest

from briefing.shared.sources import CATALOG, _load_catalog, catalog_keys, fetch_set, resolve_sources


def test_catalog_loaded_from_yaml():
    assert len(CATALOG) >= 5
    assert "aitimes" in catalog_keys() and "anthropic" in catalog_keys()


def test_resolve_sources_empty_is_all():
    assert resolve_sources([]) == list(CATALOG)


def test_resolve_sources_subset_and_unknown_dropped():
    assert [s.key for s in resolve_sources(["openai", "badkey"])] == ["openai"]


def test_fetch_set_union_and_empty_is_all():
    assert {s.key for s in fetch_set([["openai"], ["aitimes", "openai"]])} == {"openai", "aitimes"}
    assert {s.key for s in fetch_set([[]])} == set(catalog_keys())  # 빈 선택 = 전체


def _yaml(text: str) -> Path:
    p = Path(tempfile.mkdtemp()) / "c.yaml"
    p.write_text(text, encoding="utf-8")
    return p


@pytest.mark.parametrize("bad", [
    "- {key: x, name: X, url: u, kind: BOGUS, lang: en}",  # 잘못된 kind
    "- {key: x, name: X, url: u, kind: rss, lang: en}\n- {key: x, name: Y, url: v, kind: rss, lang: en}",  # 중복 key
    "- {name: X, url: u, kind: rss, lang: en}",  # 필수 key 누락
    "[]",  # 빈
])
def test_catalog_validation_rejects(bad):
    with pytest.raises(ValueError):
        _load_catalog(_yaml(bad))
