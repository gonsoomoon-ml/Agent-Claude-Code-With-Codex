"""curation — 출처별 fetch 실패는 skip+기록(non-silent) 후 나머지 계속 (source-level graceful degradation)."""
from briefing.shared.retrieval.curation import curate
from briefing.shared.stores.source_store import SourceStore
from briefing.shared.retrieval.sources import FetchedArticle, Source


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
