"""author 봉투 비용 추출(`_extract_claude_cost`) + `_run_author` recorder 훅 테스트."""
from briefing.core.authoring.author import _extract_claude_cost
from briefing.core.authoring import author
from briefing.core.stores.usage import UsageRecorder


def test_extract_cost_from_envelope():
    assert _extract_claude_cost('{"result":"hi","total_cost_usd":0.0391}') == 0.0391


def test_extract_cost_missing_or_nonjson_is_zero():
    assert _extract_claude_cost('{"result":"hi"}') == 0.0
    assert _extract_claude_cost('plain text not json') == 0.0


def test_run_author_records_cost(monkeypatch):
    class _Proc:
        returncode = 0
        stdout = '{"result":"R","total_cost_usd":0.05}'
        stderr = ""
    monkeypatch.setattr(author.subprocess, "run", lambda *a, **k: _Proc())
    monkeypatch.setattr(author.shutil, "rmtree", lambda *a, **k: None)
    monkeypatch.setattr(author.tempfile, "mkdtemp", lambda *a, **k: "/tmp/x")
    rec = UsageRecorder()
    s = type("S", (), {"author_model_id": "m", "region": "r"})()
    out = author._run_author("sys", "usr", s, recorder=rec)
    assert out == "R"
    assert rec.total() == 0.05
