"""curation — 출처별 fetch 실패는 skip+기록(non-silent) 후 나머지 계속 (source-level graceful degradation)."""
import dataclasses

from briefing.core.retrieval.curation import curate
from briefing.core.stores.source_store import SourceStore
from briefing.core.retrieval.sources import FetchedArticle, Source


def _src(key, fragile=False, require_ai=False):
    return Source(key=key, name=key.upper(), url=f"https://{key}", kind="rss", lang="en",
                  fragile=fragile, require_ai=require_ai)


def test_curate_require_ai_drops_non_ai_articles(tmp_path):
    store = SourceStore(str(tmp_path))

    def fetch(_source, _w):
        return [
            FetchedArticle("aitimes", "u1", "딥시크, 추론 속도↑ 오픈소스 공개", "AI 모델", "2026-06-29T00:00:00Z"),
            FetchedArticle("aitimes", "u2", "여수세계섬박람회 현장 점검", "지역 행사", "2026-06-29T00:00:00Z"),
        ]

    by_key = curate(store, [_src("aitimes", require_ai=True)], fetch_article_fn=fetch)
    assert len(by_key["aitimes"]) == 1   # AI 기사만 통과(여수박람회 컷)


def test_curate_without_require_ai_keeps_all(tmp_path):
    store = SourceStore(str(tmp_path))

    def fetch(_source, _w):
        return [
            FetchedArticle("aitimes", "u1", "딥시크 오픈소스 공개", "AI", "2026-06-29T00:00:00Z"),
            FetchedArticle("aitimes", "u2", "여수세계섬박람회 점검", "행사", "2026-06-29T00:00:00Z"),
        ]

    by_key = curate(store, [_src("aitimes", require_ai=False)], fetch_article_fn=fetch)
    assert len(by_key["aitimes"]) == 2   # 필터 off(기본) → 둘 다 (byte-identical)


def test_curate_uses_injected_relevance_fn(tmp_path):
    """relevance_fn seam 주입 시 키워드 대신 그 판정을 쓴다(LLM-as-Judge 배선)."""
    store = SourceStore(str(tmp_path))

    def fetch(_source, _w):
        return [
            FetchedArticle("aitimes", "u1", "딥시크 오픈소스 공개", "AI 모델", "2026-06-29T00:00:00Z"),  # 키워드=keep
            FetchedArticle("aitimes", "u2", "여수세계섬박람회 점검", "지역 행사", "2026-06-29T00:00:00Z"),  # 키워드=drop
        ]

    # 키워드를 뒤집는 판정자: '여수'만 keep. curate 가 키워드가 아니라 이 함수를 쓴다는 증명.
    def only_yeosu(title, _text):
        return "여수" in title

    by_key = curate(store, [_src("aitimes", require_ai=True)], fetch_article_fn=fetch,
                    relevance_fn=only_yeosu)
    kept = by_key.get("aitimes", [])
    assert len(kept) == 1 and "여수" in kept[0].title    # 딥시크 컷·여수 통과 = seam 사용됨


def test_curate_relevance_fn_not_called_for_non_require_ai(tmp_path):
    """require_ai=False 소스엔 relevance_fn 미호출(호출되면 예외로 실패)."""
    store = SourceStore(str(tmp_path))

    def fetch(_source, _w):
        return [FetchedArticle("plain", "u", "제목", "본문", "2026-06-29T00:00:00Z")]

    def boom(_t, _x):
        raise AssertionError("require_ai=False 소스엔 relevance_fn 호출 금지")

    by_key = curate(store, [_src("plain", require_ai=False)], fetch_article_fn=fetch,
                    relevance_fn=boom)
    assert len(by_key["plain"]) == 1


def test_default_fetch_uses_source_window_override(monkeypatch):
    """window_hours 오버라이드 소스는 글로벌 윈도우 대신 자기 값으로 fetch(late-post 보정 W≥U+P)."""
    from briefing.core.retrieval import curation

    seen = {}

    def fake_html(source, *, window_hours, **_kw):
        seen["html"] = window_hours
        return []

    def fake_rss(source, *, window_hours, **_kw):
        seen["rss"] = window_hours
        return []

    monkeypatch.setattr(curation.src, "fetch_generic_html", fake_html)
    monkeypatch.setattr(curation.src, "fetch_clean_rss", fake_rss)

    html48 = Source(key="a", name="A", url="u", kind="html", lang="en", window_hours=48)
    rss_default = Source(key="b", name="B", url="u", kind="rss", lang="en")
    curation._default_fetch(html48, 24)        # 오버라이드 → 48
    curation._default_fetch(rss_default, 24)   # 미지정(0) → 글로벌 24
    assert seen == {"html": 48, "rss": 24}


def test_default_fetch_pool_widens_for_llm_select(monkeypatch):
    """select=llm 소스는 후보 풀(12)로 페치 — 캡 안에서 판정자가 고를 수 있게. 그 외는 캡 그대로."""
    from briefing.core.retrieval import curation

    seen = {}

    def fake_rss(source, *, window_hours, max_items=5, **_kw):
        seen[source.key] = max_items
        return []

    monkeypatch.setattr(curation.src, "fetch_clean_rss", fake_rss)
    curation._default_fetch(Source(key="sel", name="S", url="u", kind="rss", lang="ko",
                                   max_items=3, select="llm"), 24)
    curation._default_fetch(Source(key="cap", name="C", url="u", kind="rss", lang="ko",
                                   max_items=3), 24)
    curation._default_fetch(Source(key="plain", name="P", url="u", kind="rss", lang="ko"), 24)
    assert seen == {"sel": 12, "cap": 3, "plain": 5}


def test_curate_applies_injected_select_fn(tmp_path):
    """캡 초과 시 select_fn(LLM 판정자 자리)이 고른 기사만 freeze — 최신순 잘림 대체."""
    store = SourceStore(str(tmp_path))
    arts = [FetchedArticle("s", f"u{i}", f"제목{i}", f"본문{i}", "2026-06-29T00:00:00Z") for i in range(4)]

    def pick_last_two(cands, k):
        return list(cands)[-k:]   # 최신순과 정반대를 골라 seam 사용을 증명

    src_sel = _src("s")
    src_sel = dataclasses.replace(src_sel, max_items=2, select="llm")
    by_key = curate(store, [src_sel], fetch_article_fn=lambda *_: arts, select_fn=pick_last_two)
    titles = [fs.title for fs in by_key["s"]]
    assert titles == ["제목2", "제목3"]   # latest(제목0·1)가 아니라 판정자 선택


def test_curate_caps_with_latest_when_no_select(tmp_path, capsys, monkeypatch):
    """select 미지정 소스가 캡 초과로 들어오면 최신순 잘림(현행 동작) + non-silent dprint."""
    monkeypatch.setenv("DEBUG", "1")   # dprint 는 DEBUG 게이트 — 관측 검증용
    store = SourceStore(str(tmp_path))
    arts = [FetchedArticle("s", f"u{i}", f"제목{i}", f"본문{i}", "2026-06-29T00:00:00Z") for i in range(4)]
    src_cap = dataclasses.replace(_src("s"), max_items=2)
    by_key = curate(store, [src_cap], fetch_article_fn=lambda *_: arts)
    assert [fs.title for fs in by_key["s"]] == ["제목0", "제목1"]   # 최신순 첫 K
    assert "선별" in capsys.readouterr().err                        # 잘림이 이제 관측됨


def test_curate_skips_failing_source_and_continues(tmp_path, capsys):
    store = SourceStore(str(tmp_path))
    good, bad = _src("good"), _src("bad", fragile=True)

    def fetch(source, _w):
        if source.key == "bad":
            raise NotImplementedError("fragile — Browser Tool v1.5")   # fragile 출처 모사
        return [FetchedArticle(source.key, "u", "t", "본문 텍스트", "2026-06-27T00:00:00Z")]

    by_key = curate(store, [bad, good], fetch_article_fn=fetch)   # bad 먼저(실패) → good(성공)
    assert "good" in by_key and len(by_key["good"]) == 1          # 정상 출처는 살아남음
    assert "bad" not in by_key                                    # 실패 출처는 skip(크래시 아님)

    err = capsys.readouterr().err
    assert "WARN" in err and "bad" in err                        # ★ non-silent — 무엇이 빠졌나 기록됨


def test_curate_all_sources_failing_returns_empty(tmp_path, capsys):
    store = SourceStore(str(tmp_path))

    def boom(_source, _w):
        raise RuntimeError("network down")

    by_key = curate(store, [_src("a"), _src("b")], fetch_article_fn=boom)
    assert by_key == {}                                          # 전부 실패 → 빈 결과(예외 전파 아님)
    assert capsys.readouterr().err.count("[WARN curate skip]") == 2   # 두 출처 모두 경고 기록
