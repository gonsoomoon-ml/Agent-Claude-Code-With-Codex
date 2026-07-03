"""gateway — handler dispatch(→기존 함수 호출) + client result 파싱. (MCP 라운드트립·Cognito 토큰은 e2e.)"""
import json
from types import SimpleNamespace

import pytest

from briefing.gateway import gateway_handler as h
from briefing.core.retrieval import gateway_client as gc
from briefing.core.retrieval.sources import FetchedArticle, Source
from briefing.core.stores.source_store import FrozenSource


def _ctx(tool):   # AgentCore 규약: TARGET___tool
    return SimpleNamespace(client_context=SimpleNamespace(custom={"bedrockAgentCoreToolName": f"T___{tool}"}))


def test_handler_fetch_article(monkeypatch):     # → 기존 _default_fetch 호출
    art = FetchedArticle("aitimes", "u", "t", "본문", "2026-06-27")
    monkeypatch.setattr(h, "_CATALOG", {"aitimes": Source("aitimes", "AI", "x", "rss", "ko")})
    monkeypatch.setattr(h, "_default_fetch", lambda _s, _w: [art])
    out = h.lambda_handler({"source_key": "aitimes", "window_hours": 0}, _ctx("fetch_article"))
    assert out["articles"][0] == {"source_key": "aitimes", "url": "u", "title": "t",
                                  "raw_text": "본문", "published_at": "2026-06-27"}


def test_handler_get_source(monkeypatch):        # → 기존 store.get_source
    fs = FrozenSource("sid", "u", "t", "텍스트", "2026-06-27", "AI")
    monkeypatch.setattr(h, "_store", lambda: SimpleNamespace(get_source=lambda _i: fs))
    out = h.lambda_handler({"source_id": "sid"}, _ctx("get_source"))
    assert out["source_id"] == "sid" and out["text"] == "텍스트" and out["media"] == "AI"


def test_handler_discover_feed(monkeypatch):     # → 기존 discover_feed
    monkeypatch.setattr(h.src, "discover_feed", lambda _u: "https://feed")
    assert h.lambda_handler({"url": "https://site"}, _ctx("discover_feed")) == {"feed": "https://feed"}


def test_handler_unknown_fail_closed():          # 화이트리스트 외 → 예외(fail-closed)
    with pytest.raises(ValueError):
        h.lambda_handler({}, _ctx("nope"))


def test_client_articles_structured():           # MCP result envelope: structuredContent
    res = SimpleNamespace(structuredContent={"articles": [
        {"source_key": "k", "url": "u", "title": "t", "raw_text": "x", "published_at": "d"}]})
    assert gc._articles(res)[0]["url"] == "u"


def test_client_articles_content_text():         # 폴백: content[0].text(JSON)
    payload = {"articles": [{"source_key": "k", "url": "u", "title": "t", "raw_text": "x", "published_at": "d"}]}
    res = SimpleNamespace(structuredContent=None, content=[SimpleNamespace(text=json.dumps(payload))])
    assert gc._articles(res)[0]["title"] == "t"
