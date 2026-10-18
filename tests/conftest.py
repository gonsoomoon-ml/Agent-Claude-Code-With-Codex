"""공용 픽스처 — 테스트는 네트워크 0.

robots 검사(retrieval/robots.py)는 요청마다 호스트의 robots.txt 를 읽는다. 테스트에서 그게 실제
네트워크로 나가지 않게, 기본은 "robots.txt 없음(4xx) = 전부 허용"으로 막아 둔다. robots 자체를
검사하는 테스트는 `robots._fetch` 를 다시 monkeypatch 해서 덮어쓴다.
"""
import pytest

from briefing.core.retrieval import robots


@pytest.fixture(autouse=True)
def _no_network_robots(monkeypatch):
    monkeypatch.setattr(robots, "_fetch", lambda _robots_url: "")
    robots._CACHE.clear()
    yield
    robots._CACHE.clear()
