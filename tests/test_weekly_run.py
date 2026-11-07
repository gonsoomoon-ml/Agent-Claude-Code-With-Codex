"""weekly.run — build(정상 · 재작성 · 격리 · 씨앗 없음 · 실패 · 중복) · 금요일 대기 · send(발송 · 중복 거부 · 격리 제목 · 실패 통지 ·
dry-run) · pull. 로컬 backend + fake(author · certify · http · send), 네트워크 0."""
import base64
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
from briefing.weekly.figure.build import FigureResult
from briefing.weekly.run import WeeklySettings, _wait_for_friday, build, build_raw_email, load_weekly_settings, pull, send

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
    for k in ("WEEKLY_ADMIN_USER_ID", "WEEKLY_AUTHOR_MODEL_ID", "WEEKLY_SELECT_MODEL_ID", "WEEKLY_STRICT", "WEEKLY_MAX_REVISIONS",
              "WEEKLY_CRITIQUE", "WEEKLY_FIGURE"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("WEEKLY_ADMIN_USER_ID", "u1")
    ws = load_weekly_settings(_Settings())
    assert (ws.admin_user_id, ws.author_model_id, ws.select_model_id, ws.strict, ws.max_revisions) == ("u1", "m-d", "m-d", True, 2)
    assert ws.critique and not ws.figure                              # env 기본: 비평 켬 · 그림 끔
    monkeypatch.setenv("WEEKLY_AUTHOR_MODEL_ID", "opus")
    monkeypatch.setenv("WEEKLY_STRICT", "0")
    ws = load_weekly_settings(_Settings())
    assert ws.author_model_id == "opus" and ws.select_model_id == "opus" and not ws.strict
    with pytest.raises(ValueError):
        build(D, _Settings(), WeeklySettings("", "m", "", "m"), store=None, card_cache=None, ledger=None, issue_store=None)
    assert run_mod.KST.key == "Asia/Seoul"


CRITIQUE_JSON = json.dumps({"issues": ["② 씨앗: 원문의 77% 사실이 빠졌다"]}, ensure_ascii=False)


def test_build_critique_pass_revises_before_gate(env, tmp_path):
    ws = WeeklySettings(**{**WS.__dict__, "critique": True})
    author = _author([SELECT_JSON, WRITE_JSON, CRITIQUE_JSON, WRITE_JSON])
    r = build(D, _Settings(), ws, **_kw(env, author))
    assert r["status"] == "ready" and r["attempts"] == 1 and len(author.calls) == 4
    assert "점검 항목" in author.calls[2]["system"] + "x" or "초안(JSON)" in author.calls[2]["user"]
    assert "이전 초안(JSON)" in author.calls[3]["user"] and "77%" in author.calls[3]["user"]
    assert "자기 비평 1건" in env["issue_store"].get(D)["notes"]
    author2 = _author([SELECT_JSON, WRITE_JSON, '{"issues": []}'])
    build(D, _Settings(), ws, **{**_kw(env, author2), "issue_store": LocalIssueStore(str(tmp_path / "issues2"))})   # 비평이 비면 revise 없이(호출 3회)
    assert len(author2.calls) == 3


def test_build_figure_track_and_inline_send(env, tmp_path, monkeypatch):
    monkeypatch.setenv("WEEKLY_ISSUES_PATH", str(tmp_path / "wi"))
    ws = WeeklySettings(**{**WS.__dict__, "figure": True})
    png = tmp_path / "fig.png"
    png.write_bytes(b"\x89PNG")
    seen = {}

    def figure_fn(md, settings, *, out_dir, **kw):
        seen["out_dir"] = str(out_dir)
        return FigureResult("ready", png=str(png), html="h", spec_json="{}", items=[("PASS", "overflow", "ok")], rounds=1)
    md_fig = MD.replace("- 과제\n", "- 과제\n- AWS 에서 돌리면: Bedrock.\n\n그림 2 — 구성\n```\n동료 -> 에이전트\n```\n")
    write_fig = json.dumps({"md": md_fig, "cites": [{"text": "분석가 50명이 분석했다.", "card": 1}]}, ensure_ascii=False)
    r = build(D, _Settings(), ws, **_kw(env, _author([SELECT_JSON, write_fig])), figure_fn=figure_fn)
    assert r["status"] == "ready" and r["figure"] == "ready" and seen["out_dir"].endswith(f"wi/fig/{D}")
    item = env["issue_store"].get(D)
    assert item["figure_png"] == str(png) and "그림 ready" in item["notes"] and item["banner"] == ""
    assert item["figure_png_b64"] == base64.b64encode(b"\x89PNG").decode("ascii")   # (d) PNG 는 표에 — send 는 다른 세션
    sent = []

    def send_fn(to, subject, html, inline=None):
        sent.append((html, inline))
        return "mid-f"
    dry = send(D, _Settings(), ws, issue_store=env["issue_store"], send_fn=send_fn, dry_run=True, load_user_fn=lambda u, st: _User())
    assert dry["inline_png_bytes"] == 4 and sent == []
    png.unlink()                                             # 07:00 send 세션엔 build 세션의 파일이 없다(1-B)
    r = send(D, _Settings(), ws, issue_store=env["issue_store"], send_fn=send_fn, load_user_fn=lambda u, st: _User())
    assert r["status"] == "sent" and sent[0][1] == [("fig2", b"\x89PNG", "image/png")] and "cid:fig2" in sent[0][0]
    assert "동료 -&gt; 에이전트" not in sent[0][0] and "그림 2 — 구성" in sent[0][0]      # ASCII 는 빠지고 캡션은 남는다


def test_send_without_section_three_figure_sends_no_attachment(env, tmp_path):
    """③ 에 그림 블록이 없으면(옛 호) PNG 가 있어도 붙이지 않는다 — 참조 없는 첨부 방지."""
    ws = WeeklySettings(**{**WS.__dict__, "figure": True})
    png = tmp_path / "fig.png"
    png.write_bytes(b"\x89PNG")
    build(D, _Settings(), ws, **_kw(env, _author([SELECT_JSON, WRITE_JSON])),
          figure_fn=lambda md, settings, **kw: FigureResult("ready", png=str(png)))
    sent = []
    r = send(D, _Settings(), ws, issue_store=env["issue_store"], send_fn=lambda to, s, h, inline=None: sent.append(inline) or "m",
             load_user_fn=lambda u, st: _User())
    assert r["status"] == "sent" and sent == [None]


def test_send_falls_back_to_figure_path_for_old_items(env, tmp_path):
    """b64 가 없는 옛 호 · 로컬 1-A 항목은 호스트 경로의 PNG 를 붙인다(폴백)."""
    ws = WeeklySettings(**{**WS.__dict__, "figure": True})
    png = tmp_path / "old.png"
    png.write_bytes(b"\x89OLD")
    md_fig = MD.replace("- 과제\n", "- 과제\n\n그림 2 — 구성\n```\na -> b\n```\n")
    st = env["issue_store"]
    st.transition(D, "building")
    st.transition(D, "ready", issue_md=md_fig, email_html=run_mod.render_email(md_fig), figure_status="ready", figure_png=str(png))
    sent = []
    r = send(D, _Settings(), ws, issue_store=st, send_fn=lambda to, s, h, inline=None: sent.append(inline) or "m",
             load_user_fn=lambda u, st: _User())
    assert r["status"] == "sent" and sent == [[("fig2", b"\x89OLD", "image/png")]]


def test_build_skips_b64_over_item_limit_but_keeps_article(env, tmp_path):
    """DDB 항목 400KB 를 넘길 PNG 는 b64 를 생략한다(notes 에만) — 그림이 기사를 막지 않는다."""
    ws = WeeklySettings(**{**WS.__dict__, "figure": True})
    png = tmp_path / "big.png"
    png.write_bytes(b"\x89PNG" * 100_000)                     # 400KB → b64 ≈ 533KB
    r = build(D, _Settings(), ws, **_kw(env, _author([SELECT_JSON, WRITE_JSON])),
              figure_fn=lambda md, settings, **kw: FigureResult("ready", png=str(png)))
    item = env["issue_store"].get(D)
    assert r["status"] == "ready" and "figure_png_b64" not in item and item["figure_png"] == str(png)
    assert "그림 b64 생략" in item["notes"]


def test_build_passes_author_timeout_to_figure(env):
    ws = WeeklySettings(**{**WS.__dict__, "figure": True, "author_timeout_s": 1200})
    seen = {}

    def figure_fn(md, settings, **kw):
        seen.update(kw)
        return FigureResult("skipped", note="no browser")
    build(D, _Settings(), ws, **_kw(env, _author([SELECT_JSON, WRITE_JSON])), figure_fn=figure_fn)
    assert seen["timeout_s"] == 1200 and seen["effort"] == "medium"


def test_figure_dir_falls_back_to_tmp_when_store_path_not_writable(tmp_path, monkeypatch):
    """컨테이너의 CWD(/app)는 root 소유라 `.data` 를 못 만든다(11-07 클라우드 build: 그림 실패 PermissionError) → 임시 폴더로.
    PNG 는 어차피 표(b64)로 넘어가므로 폴더는 어디든 된다."""
    ro = tmp_path / "ro"
    ro.mkdir()
    ro.chmod(0o500)
    try:
        monkeypatch.setenv("WEEKLY_ISSUES_PATH", str(ro / "weekly_issues"))
        d = run_mod.figure_dir(D)
        assert not str(d).startswith(str(ro)) and d.name == D and d.parent.name != "fig" and d.parent.is_dir()
        monkeypatch.setenv("WEEKLY_ISSUES_PATH", str(tmp_path / "wi"))
        assert run_mod.figure_dir(D) == tmp_path / "wi" / "fig" / D       # 쓸 수 있으면 종전 자리 그대로
    finally:
        ro.chmod(0o700)


def test_build_figure_failure_does_not_block(env):
    ws = WeeklySettings(**{**WS.__dict__, "figure": True})

    def boom(md, settings, **kw):
        raise RuntimeError("chromium")
    r = build(D, _Settings(), ws, **_kw(env, _author([SELECT_JSON, WRITE_JSON])), figure_fn=boom)
    assert r["status"] == "ready" and r["figure"] == "" and "그림 실패: RuntimeError" in env["issue_store"].get(D)["notes"]


def test_build_raw_email_mime():
    raw = build_raw_email("Field Experiment <s@x>", "a@b", "제목", "<p>본문 <img src=\"cid:fig2\"></p>", [("fig2", b"\x89PNG", "image/png")])
    text = raw.decode("utf-8", errors="ignore")
    assert "multipart/related" in text and "Content-ID: <fig2>" in text and "Content-Disposition: inline" in text and "image/png" in text
    assert "From: Field Experiment <s@x>" in text and "To: a@b" in text


def test_build_skips_revise_when_only_unfixable_failures(env, monkeypatch, tmp_path):
    """certifier 미가용(codex-error)만 남으면 재작성을 돌리지 않고 바로 격리(2026-11-04: 2회 × $0.9 헛돎 실측)."""
    monkeypatch.setattr(gate_mod._lint, "lint", lambda md: [("PASS", "1", "ok")])
    author = _author([SELECT_JSON, WRITE_JSON])
    unavailable = lambda cid, e: CertVerdict(cid, "DEMOTED", "certifier 미가용(보수적 미확인): codex exec rc=1", "codex-error")  # noqa: E731
    r = build(D, _Settings(), WS, **{**_kw(env, author), "certify_fn": unavailable})
    assert r["status"] == "quarantined" and r["attempts"] == 1 and len(author.calls) == 2   # select · write 만
    item = env["issue_store"].get(D)
    assert "재작성 생략" in item["notes"] and "certifier 미가용" in item["banner"]
    # 산술 경로: 값 대조가 막고 codex 2차 판정이 오류 → certify() 는 BLOCKED · model "deterministic" 으로 감싼다(근거에 미가용 문구)
    wrapped = lambda cid, e: CertVerdict(cid, "BLOCKED", "원문에 없는 수치 · codex DEMOTED: certifier 미가용(보수적 미확인): rc=1", "deterministic")  # noqa: E731
    author2 = _author([SELECT_JSON, WRITE_JSON])
    r2 = build(D, _Settings(), WS, **{**_kw(env, author2), "certify_fn": wrapped, "issue_store": LocalIssueStore(str(tmp_path / "issues2"))})
    assert r2["status"] == "quarantined" and r2["attempts"] == 1 and len(author2.calls) == 2


# ───────────────────────── 런타임 분기(1-B) — KST 발행일 · mode 라우팅 ─────────────────────────

def test_issue_date_kst_crosses_utc_midnight():
    """06:00 KST 토요일 = 21:00 UTC 금요일 — 데일리처럼 UTC 날짜를 쓰면 금요일 호가 되어 엉뚱한 주를 읽는다."""
    from briefing.weekly.run import issue_date_kst
    assert issue_date_kst(datetime(2026, 11, 13, 21, 0, tzinfo=timezone.utc)) == "2026-11-14"
    assert issue_date_kst(datetime(2026, 11, 14, 14, 59, tzinfo=timezone.utc)) == "2026-11-14"
    assert issue_date_kst(datetime(2026, 11, 14, 15, 0, tzinfo=timezone.utc)) == "2026-11-15"


def test_run_cloud_routes_mode_and_dry_run(env, monkeypatch):
    """weekly_build → build(dry_run 무의미 · 표에만 쓴다), weekly_send → send(dry_run 전달); 날짜 = payload 또는 KST 오늘."""
    calls = []
    monkeypatch.setattr(run_mod, "build", lambda d, s, ws, **kw: calls.append(("build", d)) or {"status": "ready"})
    monkeypatch.setattr(run_mod, "send", lambda d, s, ws, **kw: calls.append(("send", d, kw.get("dry_run"))) or {"status": "dry-run"})
    kw = dict(stores=(env["store"], env["card_cache"], env["ledger"]), issue_store=env["issue_store"], sent_log=None,
              now=lambda: datetime(2026, 11, 13, 21, 0, tzinfo=timezone.utc))
    r1 = run_mod.run_cloud("weekly_build", {"dry_run": True}, _Settings(), WS, **kw)
    r2 = run_mod.run_cloud("weekly_send", {"issue_date": "2026-11-07", "dry_run": True}, _Settings(), WS, **kw)
    assert calls == [("build", "2026-11-14"), ("send", "2026-11-07", True)]
    assert r1["issue_date"] == "2026-11-14" and r2["issue_date"] == "2026-11-07" and r2["status"] == "dry-run"
    with pytest.raises(ValueError):
        run_mod.run_cloud("weekly_approve", {}, _Settings(), WS, **kw)


# ───────────────────────── 작성자 상한(WEEKLY_AUTHOR_TIMEOUT_S) · 호출 기록(calls_json) — 2026-11-07 클라우드 build 실패 ─────────────────────────

def test_load_weekly_settings_author_timeout(monkeypatch):
    monkeypatch.setenv("WEEKLY_ADMIN_USER_ID", "u1")
    monkeypatch.delenv("WEEKLY_AUTHOR_TIMEOUT_S", raising=False)
    assert load_weekly_settings(_Settings()).author_timeout_s == 0          # 0 = 데일리 author 기본(360)
    monkeypatch.setenv("WEEKLY_AUTHOR_TIMEOUT_S", "1200")
    assert load_weekly_settings(_Settings()).author_timeout_s == 1200


def test_build_passes_timeout_and_stores_calls(env):
    """select · write(· critique · revise)가 timeout_s 를 넘기고, 호출 기록이 ready 와 failed 양쪽 표 항목에 남는다."""
    from briefing.core.stores.usage import UsageRecorder
    ws = WeeklySettings(admin_user_id=U, author_model_id="m-w", author_effort="medium", select_model_id="m-s",
                        max_revisions=2, author_timeout_s=1200)
    author = _author([SELECT_JSON, WRITE_JSON])
    rec = UsageRecorder()
    rec.add(0.1, num_turns=2, duration_ms=5)
    r = build(D, _Settings(), ws, **_kw(env, author), recorder=rec)
    assert r["status"] == "ready"
    assert [c["kw"]["timeout_s"] for c in author.calls] == [1200, 1200]
    item = env["issue_store"].get(D)
    assert json.loads(item["calls_json"])[0] == {"cost_usd": 0.1, "num_turns": 2, "duration_ms": 5}
    # failed 경로(write 가 터짐)에도 그때까지의 호출 기록이 남는다
    env2 = {**env, "issue_store": LocalIssueStore(str(Path(env["issue_store"].root).parent / "issues2"))}
    rec2 = UsageRecorder()
    rec2.add(0.2, num_turns=1, duration_ms=50)
    r2 = build(D, _Settings(), ws, **_kw(env2, _author([SELECT_JSON, RuntimeError("timeout")])), recorder=rec2)
    assert r2["status"] == "failed" and r2["stage"] == "write"
    assert json.loads(env2["issue_store"].get(D)["calls_json"])[0]["num_turns"] == 1
