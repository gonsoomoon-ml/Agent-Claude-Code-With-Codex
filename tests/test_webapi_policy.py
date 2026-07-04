"""policy — role→능력 매핑 단위 테스트."""
from briefing.core.retrieval.sources import CATALOG
from briefing.webapi.policy import max_sources


def test_general_user_capped_at_5():
    assert max_sources(False) == 5


def test_admin_gets_whole_catalog():
    assert max_sources(True) == len(CATALOG)
    assert max_sources(True) > 0
