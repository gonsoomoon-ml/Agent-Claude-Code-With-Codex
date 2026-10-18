"""공용 픽스처 — 테스트는 네트워크 0.

robots 검사(retrieval/robots.py)는 요청마다 호스트의 robots.txt 를 읽는다. 테스트에서 그게 실제
네트워크로 나가지 않게, 기본은 "robots.txt 없음(4xx) = 전부 허용"으로 막아 둔다. robots 자체를
검사하는 테스트는 `robots._fetch` 를 다시 monkeypatch 해서 덮어쓴다.

검증 AI(codex)도 마찬가지 — 숫자 검사가 막은 claim 은 codex 2차 판정을 부르므로(2026-10-18), 가짜를
안 끼운 테스트가 호스트에 깔린 codex 를 실제로 부를 수 있다. 기본은 부르는 순간 실패로 막아 둔다.
codex 동작을 검사하는 테스트는 `certifier._run_codex` 를 다시 monkeypatch 해서 덮어쓴다.
"""
import pytest

from briefing.core.retrieval import robots
from briefing.core.verification import certifier


@pytest.fixture(autouse=True)
def _no_network_robots(monkeypatch):
    monkeypatch.setattr(robots, "_fetch", lambda _robots_url: "")
    robots._CACHE.clear()
    yield
    robots._CACHE.clear()


@pytest.fixture(autouse=True)
def _no_real_codex(monkeypatch):
    # pytest.fail 은 BaseException 계열이라 certifier 의 fail-closed `except Exception` 에 삼켜지지 않는다.
    def _forbidden(prompt, **kw):
        pytest.fail("테스트가 실제 codex 를 부르려 했다 — certifier._run_codex 를 monkeypatch 할 것")
    monkeypatch.setattr(certifier, "_run_codex", _forbidden)
