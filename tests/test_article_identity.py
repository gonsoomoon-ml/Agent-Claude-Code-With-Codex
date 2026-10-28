"""article_identity — 기사 신원 키(해시·URL·매체+제목). 2026-10 중복 발송 감사의 실제 사례로 고정한다."""
from briefing.core.article_identity import cite_key, identity_keys, match_kind, title_key, url_key

_MLDRIFT = "ML Drift: Next-Gen GPU AI/ML Inference at the Edge"
_AWSKR = "Strands Agents와 Amazon Bedrock AgentCore을 이용한 발전설비진단 구현하기"


def test_url_key_strips_scheme_www_fragment_trailing_slash():
    assert url_key("https://www.Anthropic.com/news/foo/#top") == "anthropic.com/news/foo"
    assert url_key("http://anthropic.com/news/foo") == "anthropic.com/news/foo"


def test_url_key_keeps_query_article_id():
    """AI Times 는 쿼리 idxno 가 기사 ID — 지우면 전 기사가 한 키로 뭉친다(감사 함정)."""
    a = url_key("https://www.aitimes.com/news/articleView.html?idxno=216103")
    b = url_key("https://www.aitimes.com/news/articleView.html?idxno=216105")
    assert a == "aitimes.com/news/articleView.html?idxno=216103"
    assert a != b


def test_url_key_keeps_path_case():
    k = url_key("https://www.anthropic.com/engineering/AI-resistant-technical-evaluations")
    assert k.endswith("/AI-resistant-technical-evaluations")


def test_url_key_empty_or_relative_is_no_key():
    assert url_key("") == ""
    assert url_key("/news/foo") == ""
    assert url_key("u1") == ""


def test_title_key_normalizes_case_space_punct():
    assert title_key(_MLDRIFT) == title_key("ml drift — next gen gpu ai ml inference at the edge")


def test_title_key_short_generic_title_has_no_key():
    assert title_key("Release notes") == ""
    assert title_key("제목") == ""


def test_title_key_korean():
    assert title_key(_AWSKR) != ""
    assert title_key(_AWSKR) == title_key(_AWSKR.replace(" ", "  "))


def test_identity_keys_prefixes_and_media_scope():
    k = identity_keys(source_id="abc", url="https://x.com/a", title="A long enough article title", media="X Blog")
    assert {s.split(":", 1)[0] for s in k} == {"sid", "url", "title"}
    other = identity_keys(source_id="def", url="https://y.com/b", title="A long enough article title", media="Y Blog")
    assert match_kind(other, k) == ""          # 다른 매체의 같은 제목은 별개 기사


def test_match_kind_url_when_hash_differs():
    """ML Drift(10-08→10-09): 원문 한 문단 수정 → 새 해시, URL 은 같다."""
    prior = identity_keys(source_id="7a8e72", url="https://developers.googleblog.com/ml-drift/",
                          title=_MLDRIFT, media="Google Developers Blog")
    today = identity_keys(source_id="974be6", url="https://developers.googleblog.com/ml-drift",
                          title=_MLDRIFT, media="Google Developers Blog")
    assert match_kind(today, prior) == "url"


def test_match_kind_title_when_slug_changes():
    """AWS KR(09-22→09-23): slug 오타 수정(arae→narae) → URL·해시 둘 다 변경, 제목만 같다."""
    prior = identity_keys(source_id="af78", url="https://aws.amazon.com/ko/blogs/tech/arae-energy/",
                          title=_AWSKR, media="AWS Korea Tech Blog")
    today = identity_keys(source_id="d58a", url="https://aws.amazon.com/ko/blogs/tech/narae-energy/",
                          title=_AWSKR, media="AWS Korea Tech Blog")
    assert match_kind(today, prior) == "title"


def test_match_kind_reports_sid_first():
    k = identity_keys(source_id="s1", url="https://x.com/a", title="A long enough article title", media="X")
    assert match_kind(k, k) == "sid"


# --- 인용 키(cite_key) — 재보도 dedup(2026-10-28): 언어 경로를 지워 번역판 링크도 같은 키로 ---

def test_cite_key_strips_locale_segment():
    assert cite_key("https://claude.com/de/resources/articles/x") == "claude.com/resources/articles/x"
    assert cite_key("https://aws.amazon.com/ko/blogs/tech/y/") == "aws.amazon.com/blogs/tech/y"
    assert cite_key("https://example.com/zh-cn/a") == "example.com/a"
    assert cite_key("https://example.com/es-419/a") == "example.com/a"


def test_cite_key_keeps_non_locale_two_letter_segment():
    assert cite_key("https://blog.example.com/ai/post") == "blog.example.com/ai/post"


def test_cite_key_keeps_query_and_empty():
    assert cite_key("https://www.aitimes.com/news/articleView.html?idxno=1") == "aitimes.com/news/articleView.html?idxno=1"
    assert cite_key("/relative") == ""


def test_published_keys_fills_url_index(tmp_path):
    from briefing.core.article_identity import published_keys
    from briefing.core.stores.ledger import LocalLedger
    from briefing.core.stores.source_store import SourceStore
    store, led = SourceStore(str(tmp_path / "s")), LocalLedger(str(tmp_path / "l"))
    fs = store.freeze(url="https://claude.com/resources/articles/a", title="Title long enough here",
                      raw_text="본문", fetched_at="2026-10-22", media="Claude Blog")
    led.append("2026-10-22", "u", fs.source_id, "k", "PUBLISH", "H")
    led.append("2026-10-22", "u", "gone", "k", "PUBLISH", "H")            # 원본 없음 → 색인 없음
    idx: dict = {}
    published_keys(led, store, "u", "2026-10-25", 90, {}, url_index=idx)
    assert idx == {"claude.com/resources/articles/a": fs.source_id}


def test_cite_key_keeps_english_word_segments():
    """언어 코드이면서 흔한 영어 경로(uk·id·it·ar…)는 지우지 않는다 — 다른 글끼리 키가 겹쳐 잘못 빠지는 것보다
    번역판 링크 하나를 못 잇는 쪽(B 유지)이 낫다(최종 리뷰 2026-10-28). 대소문자는 구분하지 않는다."""
    assert cite_key("https://www.theguardian.com/uk/technology/x") == "theguardian.com/uk/technology/x"
    assert cite_key("https://site.com/id/12345") == "site.com/id/12345"
    assert cite_key("https://site.com/it/works") == "site.com/it/works"
    assert cite_key("https://example.com/ar/glasses") == "example.com/ar/glasses"
    assert cite_key("https://claude.com/DE/x") == "claude.com/x"
