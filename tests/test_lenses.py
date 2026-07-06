"""lenses — 라이브러리 로드/검증 + 폴백."""
import tempfile
from pathlib import Path

import pytest

from briefing.core.lenses import LENS_LIBRARY, _load_lenses, resolve_lens


def test_library_has_default_and_roles():
    keys = [ln.key for ln in LENS_LIBRARY]
    assert "general" in keys and "engineer" in keys
    assert "business" in keys and "researcher" in keys   # researcher 추가
    assert "agent-builder" in keys                        # 에이전트 빌더(card-layering §6 후속 ⓑ)
    assert "executive" not in keys                        # executive → business 통합


def test_agent_builder_lens_bounded_from_engineer():
    # 에이전트 빌더 = engineer 와 별개 페르소나 — guidance 가 에이전트 설계·운영 어휘를 명시해야 중복을 피함
    g = resolve_lens("agent-builder").guidance
    assert "에이전트" in g and ("오케스트레이션" in g or "도구" in g)


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
