"""curation — 출처별 fetch 실패는 skip+기록(non-silent) 후 나머지 계속 (source-level graceful degradation)."""
from briefing.shared.retrieval.curation import curate
from briefing.shared.stores.source_store import SourceStore
from briefing.shared.retrieval.sources import FetchedArticle, Source


def _src(key, fragile=False):
    return Source(key=key, name=key.upper(), url=f"https://{key}", kind="rss", lang="en", fragile=fragile)


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
