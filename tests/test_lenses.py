"""lenses — 라이브러리 로드/검증 + 폴백."""
import tempfile
from pathlib import Path

import pytest

from briefing.shared.lenses import LENS_LIBRARY, _load_lenses, resolve_lens


def test_library_has_default_and_roles():
    keys = [ln.key for ln in LENS_LIBRARY]
    assert "general" in keys and "engineer" in keys


def test_resolve_lens_fallback_to_general():
    assert resolve_lens("engineer").key == "engineer"
    assert resolve_lens("bogus").key == "general"  # 미상 → 폴백
    assert resolve_lens("").key == "general"


@pytest.mark.parametrize("bad", [
    "- {key: x, name: X, guidance: g}",  # 기본 'general' 없음
    "- {key: general, name: G}",         # guidance 누락
])
def test_lenses_validation_rejects(bad):
    p = Path(tempfile.mkdtemp()) / "l.yaml"
    p.write_text(bad, encoding="utf-8")
    with pytest.raises(ValueError):
        _load_lenses(p)
