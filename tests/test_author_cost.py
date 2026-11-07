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
    s = type("S", (), {"author_model_id": "m", "author_effort": "", "region": "r"})()
    out = author._run_author("sys", "usr", s, recorder=rec)
    assert out == "R"
    assert rec.total() == 0.05


def _fake_run(seen, stdout='{"result":"R","total_cost_usd":0.05}'):
    class _Proc:
        returncode = 0
        stderr = ""
    _Proc.stdout = stdout

    def run(*a, **k):
        seen.append(k)
        return _Proc()
    return run


def _settings():
    return type("S", (), {"author_model_id": "m", "author_effort": "", "region": "r"})()


def test_run_author_timeout_s_overrides_default(monkeypatch):
    """주간(1-B, 2026-11-07): Opus 5.5 high 기사 작성이 데일리 상한 360s 를 넘겨 매주 failed — 호출자가 상한을 넘길 수 있어야 한다.
    기본(None)은 종전 360 그대로(데일리 무변경)."""
    seen = []
    monkeypatch.setattr(author.subprocess, "run", _fake_run(seen))
    monkeypatch.setattr(author.shutil, "rmtree", lambda *a, **k: None)
    monkeypatch.setattr(author.tempfile, "mkdtemp", lambda *a, **k: "/tmp/x")
    author._run_author("sys", "usr", _settings())
    author._run_author("sys", "usr", _settings(), timeout_s=1200)
    assert seen[0]["timeout"] == author._AUTHOR_TIMEOUT_S == 360
    assert seen[1]["timeout"] == 1200


def test_run_author_records_turns_and_duration(monkeypatch):
    """봉투의 num_turns 와 측정한 벽시계 ms 를 비용 옆에 남긴다 — 11-14 run 이 다턴 루프 크기를 말해 준다."""
    seen = []
    monkeypatch.setattr(author.subprocess, "run",
                        _fake_run(seen, '{"result":"R","total_cost_usd":0.05,"num_turns":11,"duration_ms":400123}'))
    monkeypatch.setattr(author.shutil, "rmtree", lambda *a, **k: None)
    monkeypatch.setattr(author.tempfile, "mkdtemp", lambda *a, **k: "/tmp/x")
    rec = UsageRecorder()
    author._run_author("sys", "usr", _settings(), recorder=rec)
    assert rec.total() == 0.05
    assert len(rec.calls) == 1 and rec.calls[0]["num_turns"] == 11 and rec.calls[0]["cost_usd"] == 0.05
    assert isinstance(rec.calls[0]["duration_ms"], int) and rec.calls[0]["duration_ms"] >= 0
