"""weekly.run — build(정상 · 재작성 · 격리 · 씨앗 없음 · 실패 · 중복) · 금요일 대기 · send(발송 · 중복 거부 · 격리 제목 · 실패 통지 ·
dry-run) · pull. 로컬 backend + fake(author · certify · http · send), 네트워크 0."""
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from briefing.core.authoring.author import Claim, DraftCard
from briefing.core.gate import GatedCard
from briefing.core.stores.cache import LocalCardCache
from briefing.core.stores.ledger import LocalLedger
from briefing.core.stores.source_store import SourceStore
from briefing.core.verification.certifier import CertVerdict
from briefing.weekly import gate as gate_mod
from briefing.weekly import run as run_mod
from briefing.weekly.issues import LocalIssueStore
from briefing.weekly.run import WeeklySettings, _wait_for_friday, build, load_weekly_settings, pull, send

U, D = "admin-1", "2026-11-07"
WS = WeeklySettings(admin_user_id=U, author_model_id="m-w", author_effort="medium", select_model_id="m-s", max_revisions=2)
MD = ("# 추천, 사람은 얼마나 따르나\n2026-10-31 ~ 11-06 · 이번 주 글: Anthropic · Google · AWS\n\n**실험 한 줄.** 동전.\n\n"
      "## ① 어떤 문제인가\n장면.\n\n## ② 이번 주 근거\n**Anthropic, 글.** 분석가 50명이 분석했다.\n\n**엮으면.** 동전으로.\n\n"
      "## ③ 실험 (제안)\n- 과제\n- 내 시스템에 대입: 그대로.\n\n## ④ 이번 주 역량으로 바꿔 끼우면\n- 모델 언급 없음.\n\n출처\n- https://x/1\n")
WRITE_JSON = json.dumps({"md": MD, "cites": [{"text": "분석가 50명이 분석했다.", "card": 1, "claims": ["C1"]}]}, ensure_ascii=False)
SELECT_JSON = json.dumps({"seed": 1, "support": [2], "aws_line": 3, "mechanism": "m", "experiment": "e",
                          "candidates": [{"card": 1, "area": "Applied AI", "mechanism": True, "aws_path": True, "note": "n"}],
                          "not_chosen": [{"card": 2, "why": "w"}], "reason": "r"})


class _Settings:
    backend, region, ses_sender, author_model_id, author_effort = "local", "us-east-1", "s@x", "m-d", "low"


class _User:
    recipient = "admin@example.test"


def _gated(source_id, claims):
    draft = DraftCard(source_id=source_id, headline="h", summary="요약", why_it_matters="왜",
                      claims=tuple(Claim(f"C{i}", t, "arithmetic") for i, t in enumerate(claims, 1)))
    return GatedCard(draft, tuple(CertVerdict(c.id, "VERIFIED", "") for c in draft.claims), "PUBLISH", 1)


@pytest.fixture
def env(tmp_path, monkeypatch):
    """로컬 stores 에 한 주 카드 3장(Anthropic · Google · AWS) + 금요일 행. lint 는 PASS 로 고정(규칙은 lint 테스트가 본다)."""
    store = SourceStore(str(tmp_path / "src"))
    cache = LocalCardCache(str(tmp_path / "cache"))
    ledger = LocalLedger(str(tmp_path / "ledger"))
    ids = []
    for n, (media, url) in enumerate([("Anthropic Research", "https://www.anthropic.com/a"),
                                      ("Google Developers Blog", "https://developers.googleblog.com/b"),
                                      ("AWS ML Blog", "https://aws.amazon.com/blogs/c")], 1):
        fs = store.freeze(url=url, title=f"T{n}", raw_text=f"본문 {n}", fetched_at="f", media=media)
        cache.put(f"k{n}", _gated(fs.source_id, ("분석가 50명", "86%")))
        ledger.append("2026-11-03", U, fs.source_id, f"k{n}", "PUBLISH", f"H{n}")
        ids.append(fs.source_id)
    ledger.append("2026-11-06", U, "fri", "k-fri", "QUARANTINE", "금요일 행")
    monkeypatch.setattr(gate_mod._lint, "lint", lambda md: [("PASS", "1", "ok")])
    issues = LocalIssueStore(str(tmp_path / "issues"))
    return dict(store=store, card_cache=cache, ledger=ledger, issue_store=issues, ids=ids)


def _author(responses):
    calls = []

    def fake(system, user, settings, **kw):
        calls.append({"system": system[:40], "user": user, "kw": kw})
        r = responses[min(len(calls) - 1, len(responses) - 1)]
        if isinstance(r, Exception):
            raise r
        return r
    fake.calls = calls
    return fake


def _kw(env, author):
    return dict(store=env["store"], card_cache=env["card_cache"], ledger=env["ledger"], issue_store=env["issue_store"],
                run_author=author, certify_fn=lambda cid, e: CertVerdict(cid, "VERIFIED", "ok"),
                refetch=lambda u: "", repo_http=lambda u: (0, {}), profiles=lambda: set(), sleep=lambda s: None)


def test_build_ready_happy_path(env):
    author = _author([SELECT_JSON, WRITE_JSON])
    r = build(D, _Settings(), WS, **_kw(env, author))
    assert r["status"] == "ready" and r["attempts"] == 1 and r["seed"] == 1 and r["cards"] == 3
    item = env["issue_store"].get(D)
    assert item["issue_md"] == MD and "추천, 사람은 얼마나 따르나" in item["email_html"] and "&#9888;" not in item["email_html"]
    assert json.loads(item["gate_json"])["status"] == "PASS" and json.loads(item["seed_json"])["support"] == [2]
    assert json.loads(item["cites_json"])[0]["card"] == 1 and "카드 3장" in item["notes"]
    assert [c["kw"]["model_id"] for c in author.calls] == ["m-s", "m-w"] and "### 카드 #1 (씨앗)" in author.calls[1]["user"]


def test_build_revises_on_fail_then_passes(env, monkeypatch):
    seq = iter([[("FAIL", "9", "용어: 전염")], [("PASS", "1", "ok")]])
    monkeypatch.setattr(gate_mod._lint, "lint", lambda md: next(seq))
    author = _author([SELECT_JSON, WRITE_JSON, WRITE_JSON])
    r = build(D, _Settings(), WS, **_kw(env, author))
    assert r["status"] == "ready" and r["attempts"] == 2 and len(author.calls) == 3
    assert "이전 초안(JSON)" in author.calls[2]["user"] and "- 용어: 전염" in author.calls[2]["user"]
    assert env["issue_store"].get(D)["attempts"] == "2"


def test_build_quarantines_after_max_revisions(env, monkeypatch):
    monkeypatch.setattr(gate_mod._lint, "lint", lambda md: [("FAIL", "1", "본문 3,500자")])
    ws = WeeklySettings(**{**WS.__dict__, "max_revisions": 1})
    author = _author([SELECT_JSON, WRITE_JSON])
    r = build(D, _Settings(), ws, **_kw(env, author))
    assert r["status"] == "quarantined" and r["attempts"] == 2 and len(author.calls) == 3
    html = env["issue_store"].get(D)["email_html"]
    assert "&#9888; 검사 실패 — 격리" in html and "본문 3,500자" in html


def test_build_none_seed_skips_author_and_gate(env):
    author = _author([json.dumps({"seed": None, "candidates": [], "not_chosen": [{"card": 1, "why": "제품 소식"}], "reason": "없음"})])
    r = build(D, _Settings(), WS, **_kw(env, author))
    assert r["status"] == "ready" and r["none"] and len(author.calls) == 1
    item = env["issue_store"].get(D)
    assert item["issue_md"].startswith("# 이번 주 아이디어 없음") and "게이트 생략" in item["gate_json"]


def test_build_records_failed_stage(env):
    author = _author([SELECT_JSON, RuntimeError("claude -p rc=1")])
    r = build(D, _Settings(), WS, **_kw(env, author))
    assert r["status"] == "failed" and r["stage"] == "write"
    assert env["issue_store"].get(D)["error"].startswith("write: RuntimeError: claude -p rc=1")
    # failed 는 다시 만들 수 있다
    assert build(D, _Settings(), WS, **_kw(env, _author([SELECT_JSON, WRITE_JSON])))["status"] == "ready"


def test_build_skips_when_in_progress_or_sent(env):
    env["issue_store"].transition(D, "building")
    assert build(D, _Settings(), WS, **_kw(env, _author([])))["status"] == "skipped"


def test_wait_for_friday(tmp_path):
    ledger = LocalLedger(str(tmp_path))
    ledger.append("2026-11-05", U, "s", "k", "PUBLISH", "목")
    notes, slept = [], []
    before = datetime(2026, 11, 6, 21, 10, tzinfo=timezone.utc)     # 06:10 KST — 마감 전

    def sleep(s):
        slept.append(s)
        ledger.append("2026-11-06", U, "s2", "k", "PUBLISH", "금")     # 한 번 기다리면 금요일 행이 생긴다
    assert _wait_for_friday(ledger, U, D, "06:40", now=lambda: before, sleep=sleep, notes=notes) and slept == [300] and notes == []
    ledger2 = LocalLedger(str(tmp_path / "2"))
    after = datetime(2026, 11, 6, 21, 41, tzinfo=timezone.utc)      # 06:41 KST — 마감 지남
    assert not _wait_for_friday(ledger2, U, D, "06:40", now=lambda: after, sleep=sleep, notes=notes)
    assert slept == [300] and "금요일 run_date 원장 행 없음" in notes[0]


class _SentLog:
    def __init__(self):
        self.rows = []

    def mark_sent(self, user_id, run_date, *, record=None):
        self.rows.append((user_id, run_date, record))


def _ready(env, status="ready"):
    s = env["issue_store"]
    s.transition(D, "building")
    s.transition(D, status, issue_md=MD, email_html="<html>본문</html>", cost_usd="0.1234")
    return s


def test_send_then_duplicate_refused(env):
    s, sent, log = _ready(env), [], _SentLog()

    def send_fn(to, subject, html):
        sent.append((to, subject, html))
        return "mid-1"
    r = send(D, _Settings(), WS, issue_store=s, send_fn=send_fn, sent_log=log, load_user_fn=lambda u, st: _User())
    assert r["status"] == "sent" and r["message_id"] == "mid-1" and r["to"] == "admin@example.test"
    assert sent[0][1] == "[현장 실험] 추천, 사람은 얼마나 따르나" and s.get(D)["status"] == "sent"
    assert log.rows[0][0] == "weekly#admin-1" and log.rows[0][2]["cost_usd"] == "0.1234"
    r2 = send(D, _Settings(), WS, issue_store=s, send_fn=send_fn, load_user_fn=lambda u, st: _User())
    assert r2["status"] == "skipped" and len(sent) == 1


def test_send_quarantined_marks_subject_and_dry_run_sends_nothing(env):
    s, sent = _ready(env, "quarantined"), []
    r = send(D, _Settings(), WS, issue_store=s, send_fn=lambda *a: sent.append(a) or "x", dry_run=True,
             load_user_fn=lambda u, st: _User())
    assert r["status"] == "dry-run" and r["subject"].endswith(" — 격리(검사 실패)") and sent == [] and s.get(D)["status"] == "quarantined"


def test_send_failure_notice_and_send_error(env):
    s, sent = env["issue_store"], []

    def send_fn(to, subject, html):
        sent.append((subject, html))
        return "mid-n"
    r = send(D, _Settings(), WS, issue_store=s, send_fn=send_fn, load_user_fn=lambda u, st: _User())   # 호 없음
    assert r["status"] == "notified_failure" and sent[0][0] == f"[현장 실험] 생성 실패 {D}" and "build 가 돌지 않음" in sent[0][1]
    s.transition(D, "building")
    s.transition(D, "failed", error="write: boom")
    send(D, _Settings(), WS, issue_store=s, send_fn=send_fn, load_user_fn=lambda u, st: _User())
    assert "write: boom" in sent[1][1] and s.get(D)["status"] == "failed"          # 통지는 상태를 바꾸지 않는다
    s.transition(D, "building")
    s.transition(D, "ready", issue_md=MD, email_html="<p/>")

    def boom(*a):
        raise RuntimeError("SES down")
    with pytest.raises(RuntimeError):
        send(D, _Settings(), WS, issue_store=s, send_fn=boom, load_user_fn=lambda u, st: _User())
    assert s.get(D)["status"] == "send_failed" and "SES down" in s.get(D)["error"]


def test_pull_writes_issue_and_log(env, tmp_path):
    author = _author([SELECT_JSON, WRITE_JSON])
    build(D, _Settings(), WS, **_kw(env, author))
    r = pull(D, issue_store=env["issue_store"], out_dir=tmp_path / "out")
    assert Path(r["md"]).read_text(encoding="utf-8") == MD
    log = Path(r["log"]).read_text(encoding="utf-8")
    assert "## 씨앗" in log and "- #2 — w" in log and "## 게이트: PASS" in log and "cite" in log and "상태: ready" in log


def test_load_weekly_settings_env_first(monkeypatch):
    for k in ("WEEKLY_ADMIN_USER_ID", "WEEKLY_AUTHOR_MODEL_ID", "WEEKLY_SELECT_MODEL_ID", "WEEKLY_STRICT", "WEEKLY_MAX_REVISIONS"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("WEEKLY_ADMIN_USER_ID", "u1")
    ws = load_weekly_settings(_Settings())
    assert (ws.admin_user_id, ws.author_model_id, ws.select_model_id, ws.strict, ws.max_revisions) == ("u1", "m-d", "m-d", True, 2)
    monkeypatch.setenv("WEEKLY_AUTHOR_MODEL_ID", "opus")
    monkeypatch.setenv("WEEKLY_STRICT", "0")
    ws = load_weekly_settings(_Settings())
    assert ws.author_model_id == "opus" and ws.select_model_id == "opus" and not ws.strict
    with pytest.raises(ValueError):
        build(D, _Settings(), WeeklySettings("", "m", "", "m"), store=None, card_cache=None, ledger=None, issue_store=None)
    assert run_mod.KST.key == "Asia/Seoul"
