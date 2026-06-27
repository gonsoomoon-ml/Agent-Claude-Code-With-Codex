"""source_store — content-addressed source-of-record (결정론 신뢰 핵심)."""
import unicodedata

from briefing.shared.stores.source_store import SourceStore, content_id, media_from_url, normalize


def test_normalize_crlf_and_trailing_ws():
    assert normalize("a\r\nb\r\n") == "a\nb"
    assert normalize("  x  \n  y  ") == "x\n  y"  # 줄말미공백 정리 + 전체 양끝 strip


def test_normalize_nfc_unifies():
    nfd = unicodedata.normalize("NFD", "가나")  # 자모 분리형
    assert normalize(nfd) == "가나"
    assert content_id(normalize(nfd)) == content_id(normalize("가나"))  # 같은 source_id


def test_content_id_is_sha256_hex():
    cid = content_id("hello")
    assert len(cid) == 64 and all(c in "0123456789abcdef" for c in cid)


def test_freeze_idempotent_collision_returns_first(tmp_path):
    s = SourceStore(str(tmp_path))
    a = s.freeze(url="https://A", title="A", raw_text="같은 내용", fetched_at="t1")
    b = s.freeze(url="https://B", title="B", raw_text="같은 내용", fetched_at="t2")  # 다른 url, 같은 텍스트
    g = s.get_source(a.source_id)
    assert a.source_id == b.source_id   # content-addressed
    assert a == b == g                  # 반환 == 저장 == get_source
    assert b.url == "https://A"          # 충돌 시 *최초* 메타데이터가 정본


def test_media_explicit_and_derived(tmp_path):
    s = SourceStore(str(tmp_path))
    explicit = s.freeze(url="https://www.aitimes.com/x", title="t", raw_text="명시", fetched_at="t", media="AI Times")
    assert explicit.media == "AI Times"                       # catalog 정본명 우선
    derived = s.freeze(url="https://www.aitimes.com/y", title="t", raw_text="유도", fetched_at="t")
    assert derived.media == "aitimes.com"                      # 미제공 → url 도메인(www 제거)
    assert media_from_url("https://www.aitimes.com/z?a=1") == "aitimes.com"
