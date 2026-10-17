"""업그레이드 비교 실험 — 공통 유틸 테스트(JSONL 기록·재개 키·소스 종류 분류)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from upgrade_eval import common  # noqa: E402


def test_jsonl_roundtrip_and_resume_keys(tmp_path):
    p = tmp_path / "r.jsonl"
    common.append_jsonl(p, {"model": "m", "pass": 1, "claim": "c1", "v": "가"})
    common.append_jsonl(p, {"model": "m", "pass": 2, "claim": "c1"})
    assert common.read_jsonl(p)[0]["v"] == "가"
    assert common.done_keys(p, ("model", "pass", "claim")) == {("m", 1, "c1"), ("m", 2, "c1")}
    assert common.read_jsonl(tmp_path / "missing.jsonl") == []


def test_done_keys_fills_missing_fields_with_none(tmp_path):
    p = tmp_path / "r.jsonl"
    common.append_jsonl(p, {"model": "m"})
    assert common.done_keys(p, ("model", "pass")) == {("m", None)}


def test_source_kind_and_lang():
    k = common.source_kind
    assert k("https://www.aitimes.com/news/articleView.html?idxno=1") == "뉴스"
    assert k("https://the-decoder.com/x/") == "뉴스"
    assert k("https://discuss.pytorch.kr/t/x/1") == "커뮤니티"
    assert k("https://www.anthropic.com/engineering/x") == "기술·연구"
    assert k("https://research.google/blog/x/") == "기술·연구"
    assert k("https://developers.googleblog.com/x/") == "기술·연구"
    assert k("https://aws.amazon.com/blogs/machine-learning/x/") == "기술·연구"
    assert k("https://aws.amazon.com/ko/blogs/tech/x/") == "기술·연구"
    assert k("https://www.anthropic.com/news/x") == "기업 발표"
    assert k("https://claude.com/blog/x") == "기업 발표"
    assert k("https://blog.google/technology/ai/x/") == "기업 발표"
    assert k("https://deepmind.google/discover/blog/x/") == "기업 발표"
    assert k("https://example.com/x") == "미상"
    assert common.source_lang("https://aws.amazon.com/ko/blogs/tech/x/") == "ko"
    assert common.source_lang("https://www.aitimes.com/news/x") == "ko"
    assert common.source_lang("https://discuss.pytorch.kr/t/x/1") == "ko"
    assert common.source_lang("https://the-decoder.com/x/") == "en"
