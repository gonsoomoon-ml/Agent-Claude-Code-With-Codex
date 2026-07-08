# Admin 모니터링 대시보드 구현 플랜 (Phase 1)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 발송된 이메일마다 기사수·소요시간·발송시각·실비용을 durable 하게 계측하고, admin 이 로그인해 `GET /admin/emails` 로 조회하는 `/admin` 대시보드를 만든다.

**Architecture:** 세 조각 — ① `core/`·`scheduler/`·`stores/` 의 **role-blind 계측**(UsageRecorder 로 author 실비용 정확+certify 추정, 사용자별 타이머, 확장된 sent-log audit row), ② `webapi/admin.py` 의 **admin-gated 읽기 API**, ③ React `/admin` 테이블. role 은 계측에 안 들어가고 webapi 읽기 라우트에만 존재 → decorrelation 보존.

**Tech Stack:** Python 3.12 · UV · pytest · ruff · FastAPI(Mangum→HTTP API) · boto3 DynamoDB · React+Vite+vitest.

**스펙:** [`docs/superpowers/specs/2026-07-08-admin-monitoring-design.md`](../specs/2026-07-08-admin-monitoring-design.md)

## Global Constraints

- **테스트 기준선:** `uv run pytest` 208개(+3 skipped) 전부 green 유지. 새 필드/파라미터는 **기본값**으로 하위호환(기존 생성·호출 무변경).
- **린트:** `uv run ruff check src tests` clean.
- **신뢰 경계(비협상):** `is_admin`/role 은 `core/`·gate·certifier·pipeline·runtime payload·ledger 에 **절대** 넣지 않는다. role 은 `webapi` 읽기 라우트에서만. 계측은 전 사용자에 대해 role-blind.
- **certifier 최소 컨텍스트:** `certifier.py` 는 이번 작업에서 **수정하지 않는다** — certify 비용 추정은 gate.`verify_card`(claim_type 을 아는 곳)에서 계산.
- **DynamoDB Float 금지:** boto3 resource 는 `float` 를 거부(`Float types are not supported`) — `cost_usd` 는 반드시 `decimal.Decimal(str(x))` 로 저장, 읽을 때 `float()` 로 환원. `int`(published·duration_ms)는 그대로 OK.
- **frozen dataclass:** 새 필드는 기본값 필수(keyword 생성 하위호환).
- **언어:** docstring·주석 한국어 우선, 식별자·로그·CLI 는 영어.
- **clean-dir 격리:** author/certifier subprocess 는 clean dir(변경 없음).

---

### Task 1: UsageRecorder (비용 누적 sink)

**Files:**
- Create: `src/briefing/core/stores/usage.py`
- Test: `tests/test_usage_recorder.py`

**Interfaces:**
- Produces: `UsageRecorder` — `add(cost_usd: float) -> None`, `total() -> float`; 모듈 상수 `EST_CERTIFY_USD_PER_ENTAILMENT: float`.

- [ ] **Step 1: 실패 테스트 작성**

```python
# tests/test_usage_recorder.py
from briefing.core.stores.usage import UsageRecorder, EST_CERTIFY_USD_PER_ENTAILMENT


def test_recorder_accumulates_and_snapshots():
    r = UsageRecorder()
    assert r.total() == 0.0
    r.add(0.039)
    r.add(0.016)
    assert round(r.total(), 3) == 0.055


def test_est_certify_constant_is_positive():
    assert EST_CERTIFY_USD_PER_ENTAILMENT > 0
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_usage_recorder.py -v`
Expected: FAIL — `ModuleNotFoundError: briefing.core.stores.usage`

- [ ] **Step 3: 최소 구현**

```python
# src/briefing/core/stores/usage.py
"""usage — 브리핑 1회의 LLM 실비용 누적 sink(선택 주입, ledger/card_cache 와 동일 패턴).

author 는 `claude -p` 봉투의 total_cost_usd(정확)를, gate.verify_card 는 certify 추정치를
같은 recorder 에 add 한다. run_briefing 이 사용자 iteration 전후 델타를 스냅샷 → UserBriefing.cost_usd.
캐시히트(사실층 memo/cache)면 실제 LLM 콜이 없어 델타 0 → '실제 발생 비용'(스펙 C1).
"""
from __future__ import annotations

# certify 함의 1콜 추정 단가(v1) — cost 분석: GPT-5.5 $5/$30, ~4k in/~400 out ≈ $0.032.
# codex usage 정밀 파싱은 v1.1. author 는 봉투로 이미 정확하므로 추정 대상 아님.
EST_CERTIFY_USD_PER_ENTAILMENT = 0.032


class UsageRecorder:
    """run 1회의 비용 누적기. mutable — pure 테스트에서 미주입 시 계측 0(결정론 유지)."""

    def __init__(self) -> None:
        self._cost_usd = 0.0

    def add(self, cost_usd: float) -> None:
        self._cost_usd += cost_usd

    def total(self) -> float:
        return self._cost_usd
```

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest tests/test_usage_recorder.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: 커밋**

```bash
git add src/briefing/core/stores/usage.py tests/test_usage_recorder.py
git commit -m "feat(usage): UsageRecorder 비용 누적 sink + certify 추정 상수"
```

---

### Task 2: author 봉투 비용 추출 + recorder 훅

**Files:**
- Modify: `src/briefing/core/authoring/author.py` (`_extract_claude_result` 부근 L254; `_run_author` L215; `draft_card` L117; `revise_claims` L130; `draft_interpretation` L191)
- Test: `tests/test_author_cost.py`

**Interfaces:**
- Consumes: `UsageRecorder` (Task 1).
- Produces: `_extract_claude_cost(stdout: str) -> float`; `_run_author(..., *, recorder=None)`; `draft_card/revise_claims/draft_interpretation(..., *, recorder=None)`.

- [ ] **Step 1: 실패 테스트 작성**

```python
# tests/test_author_cost.py
from briefing.core.authoring.author import _extract_claude_cost


def test_extract_cost_from_envelope():
    assert _extract_claude_cost('{"result":"hi","total_cost_usd":0.0391}') == 0.0391


def test_extract_cost_missing_or_nonjson_is_zero():
    assert _extract_claude_cost('{"result":"hi"}') == 0.0
    assert _extract_claude_cost('plain text not json') == 0.0
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_author_cost.py -v`
Expected: FAIL — `ImportError: cannot import name '_extract_claude_cost'`

- [ ] **Step 3: 구현 — 비용 추출 함수 추가**

`author.py` 의 `_extract_claude_result` 바로 아래에 추가:

```python
def _extract_claude_cost(stdout: str) -> float:
    """`claude -p --output-format json` 봉투의 total_cost_usd(정확한 실비용). 봉투 아니면 0.0."""
    try:
        obj = json.loads(stdout)
    except (ValueError, TypeError):
        return 0.0
    if isinstance(obj, dict):
        v = obj.get("total_cost_usd")
        if isinstance(v, (int, float)):
            return float(v)
    return 0.0
```

- [ ] **Step 4: 구현 — `_run_author` 가 recorder 에 기록**

`_run_author` 시그니처를 `def _run_author(system_prompt: str, user_prompt: str, settings: Settings, *, recorder=None) -> str:` 로 바꾸고, `if proc.returncode != 0: raise ...` 다음 · `return _extract_claude_result(...)` 앞에 삽입:

```python
    if recorder is not None:
        recorder.add(_extract_claude_cost(proc.stdout))
    return _extract_claude_result(proc.stdout)
```

`draft_card`·`revise_claims`·`draft_interpretation` 3함수에 `*, recorder=None` 파라미터를 추가하고, 각자의 `_run_author(system_prompt, <user_prompt>, settings)` 호출을 `_run_author(system_prompt, <user_prompt>, settings, recorder=recorder)` 로 바꾼다. (예: `draft_card` 의 L126 → `text = _run_author(system_prompt, build_user_prompt(source), settings, recorder=recorder)`.)

- [ ] **Step 5: recorder 기록 테스트 추가**

```python
# tests/test_author_cost.py 에 추가
from unittest.mock import patch
from briefing.core.authoring import author
from briefing.core.stores.usage import UsageRecorder


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
```

- [ ] **Step 6: 통과 + 전체 회귀 확인**

Run: `uv run pytest tests/test_author_cost.py -v && uv run pytest -q`
Expected: 새 테스트 PASS, 기존 208 전부 PASS(회귀 0)

- [ ] **Step 7: 커밋**

```bash
git add src/briefing/core/authoring/author.py tests/test_author_cost.py
git commit -m "feat(author): claude -p 봉투 total_cost_usd 추출 + recorder 훅(옵션)"
```

---

### Task 3: gate 가 recorder 를 author/verify 로 배선 + certify 추정 기록

**Files:**
- Modify: `src/briefing/core/gate.py` (`produce_card` L86; `verify_card` L65; `interpret_card` L186; 상단 import)
- Test: `tests/test_gate_cost.py`

**Interfaces:**
- Consumes: `UsageRecorder`, `EST_CERTIFY_USD_PER_ENTAILMENT` (Task 1); author `recorder=` params (Task 2).
- Produces: `produce_card(..., *, recorder=None)`, `verify_card(card, store, *, recorder=None)`, `interpret_card(..., *, recorder=None)`.

- [ ] **Step 1: 실패 테스트 작성**

```python
# tests/test_gate_cost.py
from briefing.core.gate import verify_card
from briefing.core.stores.usage import UsageRecorder, EST_CERTIFY_USD_PER_ENTAILMENT
from briefing.core.authoring.author import Claim, DraftCard


class _Store:
    def get_source(self, sid):
        return type("FS", (), {"text": "원문 100 달러"})()


def _card():
    return DraftCard(source_id="s", headline="h", summary="", why_it_matters="",
                     claims=(Claim("C1", "함의 주장", "entailment"),
                             Claim("C2", "숫자 100", "arithmetic")))


def test_verify_card_records_certify_estimate_for_entailment_only(monkeypatch):
    import briefing.core.gate as gate
    monkeypatch.setattr(gate, "certify",
                        lambda cid, env: gate.CertVerdict(cid, "VERIFIED", "", "x"))
    rec = UsageRecorder()
    verify_card(_card(), _Store(), recorder=rec)
    # 1 entailment claim → 1 추정 콜, arithmetic 은 무료 → 미포함
    assert rec.total() == EST_CERTIFY_USD_PER_ENTAILMENT
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_gate_cost.py -v`
Expected: FAIL — `TypeError: verify_card() got an unexpected keyword argument 'recorder'`

- [ ] **Step 3: 구현 — import + verify_card**

`gate.py` 상단 import 에 추가:

```python
from functools import partial
from .stores.usage import EST_CERTIFY_USD_PER_ENTAILMENT
```

`verify_card` 시그니처를 `def verify_card(card: DraftCard, store: SourceStore, *, recorder=None) -> tuple[CertVerdict, ...]:` 로 바꾸고, `return tuple(verdicts)` 앞에 삽입:

```python
    if recorder is not None:
        n_entail = sum(1 for c in card.claims if c.claim_type == "entailment")
        recorder.add(n_entail * EST_CERTIFY_USD_PER_ENTAILMENT)
    return tuple(verdicts)
```

- [ ] **Step 4: 구현 — produce_card / interpret_card 배선**

`produce_card` 에 `*, ... , verify_fn=None, recorder=None` 로 파라미터 추가, DI 해소부(L106-108)를 아래로 교체(기본 실구현에만 recorder 를 partial 바인딩 — 주입된 fake 는 3-인자 그대로):

```python
    draft_fn = draft_fn or partial(author.draft_card, recorder=recorder)
    revise_fn = revise_fn or partial(author.revise_claims, recorder=recorder)
    verify_fn = verify_fn or (lambda c: verify_card(c, store, recorder=recorder))
```

`interpret_card` 에 `*, interp_fn=None, recorder=None` 추가, L203 을 교체:

```python
    interp_fn = interp_fn or partial(author.draft_interpretation, recorder=recorder)
```

- [ ] **Step 5: 통과 + 회귀 확인**

Run: `uv run pytest tests/test_gate_cost.py -v && uv run pytest -q`
Expected: 새 테스트 PASS, 기존 전부 PASS(회귀 0 — 주입 fake 경로는 recorder 무시)

- [ ] **Step 6: 커밋**

```bash
git add src/briefing/core/gate.py tests/test_gate_cost.py
git commit -m "feat(gate): recorder 를 author/verify 로 partial 배선 + certify 추정 기록(certifier 무수정)"
```

---

### Task 4: pipeline — UserBriefing carrier + 사용자별 비용/시간 스냅샷

**Files:**
- Modify: `src/briefing/core/pipeline.py` (`UserBriefing` L34; `run_briefing` L44; `_process` L104; 상단 import)
- Test: `tests/test_pipeline_metrics.py`

**Interfaces:**
- Consumes: `UsageRecorder` (Task 1); gate `recorder=` (Task 3).
- Produces: `UserBriefing.cost_usd: float`, `UserBriefing.duration_ms: int`; `run_briefing(..., recorder=None)`.

- [ ] **Step 1: 실패 테스트 작성**

```python
# tests/test_pipeline_metrics.py
from briefing.core.pipeline import UserBriefing


def test_userbriefing_has_cost_and_duration_defaults():
    b = UserBriefing(user_id="u", recipient="r", cards=(), email="", published=0, quarantined=0)
    assert b.cost_usd == 0.0
    assert b.duration_ms == 0
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_pipeline_metrics.py -v`
Expected: FAIL — `AttributeError: 'UserBriefing' object has no attribute 'cost_usd'`

- [ ] **Step 3: 구현 — carrier 필드 + import**

`pipeline.py` 상단에 추가:

```python
import time
from .stores.usage import UsageRecorder
```

`UserBriefing` 에 필드 추가(기존 6필드 뒤, 기본값):

```python
    cost_usd: float = 0.0      # 이 사용자 iteration 실제 발생 비용(캐시히트=0)
    duration_ms: int = 0       # 이 사용자 iteration 벽시계 시간
```

- [ ] **Step 4: 구현 — run_briefing 타이머 + 델타 스냅샷**

`run_briefing` 시그니처 끝에 `recorder: UsageRecorder | None = None` 추가. 함수 본문 `out: list[UserBriefing] = []` 다음에 `rec = recorder if recorder is not None else UsageRecorder()` 추가. `for u in users:` 루프 최상단에 `before = rec.total(); t0 = time.monotonic()` 추가. `_process(...)` 호출에 `recorder=rec` 인자 추가(아래 Step 5). 마지막 `UserBriefing(...)` 생성에 두 필드 추가:

```python
        out.append(
            UserBriefing(
                user_id=u.id,
                recipient=u.recipient,
                cards=cards,
                email=render.render_email(
                    cards, u, settings, source_categories=source_categories, today=today
                ),
                published=sum(1 for c in cards if c.decision == "PUBLISH"),
                quarantined=sum(1 for c in cards if c.decision == "QUARANTINE"),
                cost_usd=round(rec.total() - before, 6),
                duration_ms=int((time.monotonic() - t0) * 1000),
            )
        )
```

- [ ] **Step 5: 구현 — _process 가 recorder 를 gate 로 전달**

`_process` 시그니처에 `recorder=None` 추가(기존 마지막 위치 인자 뒤). 내부의 `produce_card(fs, _FACT_USER, settings, store, draft_fn=draft_fn, revise_fn=revise_fn, verify_fn=verify_fn)` → 끝에 `, recorder=recorder` 추가. `interpret_card(fact, fs, u, settings, interp_fn=interp_fn)` → 끝에 `, recorder=recorder` 추가. `run_briefing` 의 `_process(fs, u, settings, store, card_cache, ledger, run_date, draft_fn, revise_fn, verify_fn, interp_fn, fact_memo, interp_memo)` 호출에 `, recorder=rec` 추가.

- [ ] **Step 6: 통과 + 회귀 확인**

Run: `uv run pytest tests/test_pipeline_metrics.py -v && uv run pytest -q`
Expected: 새 테스트 PASS, 기존 전부 PASS. (pure 경로=recorder 내부 생성·author 콜 0 → cost 0, 결정론 유지)

- [ ] **Step 7: 커밋**

```bash
git add src/briefing/core/pipeline.py tests/test_pipeline_metrics.py
git commit -m "feat(pipeline): UserBriefing cost_usd/duration_ms carrier + 사용자별 델타 스냅샷"
```

---

### Task 5: deliver 가 SES 응답을 반환

**Files:**
- Modify: `src/briefing/scheduler/deliver.py` (`DeliverFn` L13; `make_ses_deliver` L21-42)
- Test: `tests/test_deliver_returns.py`

**Interfaces:**
- Produces: `DeliverFn = Callable[[Any], dict | None]`; `make_ses_deliver(...)` 의 `deliver` 가 SES 응답 dict(발송 시) 또는 None(미발송) 반환.

- [ ] **Step 1: 실패 테스트 작성**

```python
# tests/test_deliver_returns.py
from briefing.scheduler.deliver import make_ses_deliver


class _FakeSES:
    def send_email(self, **kw):
        return {"MessageId": "MID-1"}


def _briefing(pub):
    return type("B", (), {"recipient": "a@x.com", "email": "<p>", "published": pub})()


def test_deliver_returns_ses_response_when_published():
    d = make_ses_deliver(type("S", (), {"ses_sender": "s@x.com", "region": "r"})(),
                         client=_FakeSES())
    assert d(_briefing(3)) == {"MessageId": "MID-1"}


def test_deliver_returns_none_when_nothing_published():
    d = make_ses_deliver(type("S", (), {"ses_sender": "s@x.com", "region": "r"})(),
                         client=_FakeSES())
    assert d(_briefing(0)) is None
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_deliver_returns.py -v`
Expected: FAIL — `assert None == {'MessageId': 'MID-1'}` (현재 deliver 는 None 반환)

- [ ] **Step 3: 구현**

`DeliverFn` 타입 별칭을 `DeliverFn = Callable[[Any], "dict | None"]` 로 바꾸고 주석 갱신. `deliver` 내부를 반환형으로 수정:

```python
    def deliver(briefing: Any) -> "dict | None":
        if not should_deliver(briefing):
            return None
        ses = client
        if ses is None:
            import boto3  # lazy
            ses = boto3.client("ses", region_name=settings.region)
        return ses.send_email(
            Source=settings.ses_sender,
            Destination={"ToAddresses": [briefing.recipient]},
            Message={
                "Subject": {"Data": subject or f"데일리 브리핑 ({briefing.published}건)"},
                "Body": {"Html": {"Data": briefing.email}},
            },
        )
```

- [ ] **Step 4: 통과 + 회귀 확인**

Run: `uv run pytest tests/test_deliver_returns.py -v && uv run pytest -q`
Expected: 새 PASS, 기존 전부 PASS. (dry-run 의 `lambda b: None` 도 새 계약과 호환)

- [ ] **Step 5: 커밋**

```bash
git add src/briefing/scheduler/deliver.py tests/test_deliver_returns.py
git commit -m "feat(deliver): SES 응답(MessageId) 반환 — audit 용(기존 폐기 제거)"
```

---

### Task 6: sent_log.mark_sent 필드 확장(하위호환)

**Files:**
- Modify: `src/briefing/scheduler/sent_log.py` (`mark_sent` L41-43)
- Test: `tests/test_sent_log_record.py`

**Interfaces:**
- Produces: `DynamoSentLog.mark_sent(user_id, run_date, *, record: dict | None = None)` — record 있으면 item 에 병합.

- [ ] **Step 1: 실패 테스트 작성**

```python
# tests/test_sent_log_record.py
from briefing.scheduler.sent_log import DynamoSentLog


class _FakeTable:
    def __init__(self): self.items = []
    def put_item(self, Item): self.items.append(Item)


def test_mark_sent_backward_compatible_without_record():
    t = _FakeTable()
    DynamoSentLog(t).mark_sent("u1", "2026-07-08")
    assert t.items == [{"user_id": "u1", "run_date": "2026-07-08"}]


def test_mark_sent_merges_audit_record():
    t = _FakeTable()
    DynamoSentLog(t).mark_sent("u1", "2026-07-08",
                               record={"published": 5, "status": "sent"})
    assert t.items[0] == {"user_id": "u1", "run_date": "2026-07-08",
                          "published": 5, "status": "sent"}
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_sent_log_record.py -v`
Expected: FAIL — `TypeError: mark_sent() got an unexpected keyword argument 'record'`

- [ ] **Step 3: 구현**

`mark_sent` 를 교체:

```python
    def mark_sent(self, user_id: str, run_date: str, *, record: dict | None = None) -> None:
        # 키 단위 멱등(같은 (user,date) 덮어씀). record 있으면 audit 필드 병합(하위호환: 없으면 기존 dedup 불리언).
        item = {"user_id": user_id, "run_date": run_date}
        if record:
            item.update(record)
        self._t.put_item(Item=item)
```

- [ ] **Step 4: 통과 + 회귀 확인**

Run: `uv run pytest tests/test_sent_log_record.py -v && uv run pytest -q`
Expected: 새 PASS, 기존 전부 PASS.

- [ ] **Step 5: 커밋**

```bash
git add src/briefing/scheduler/sent_log.py tests/test_sent_log_record.py
git commit -m "feat(sent_log): mark_sent record= 로 audit 필드 병합(하위호환)"
```

---

### Task 7: dispatch — audit 레코드 조립(발송 시)

**Files:**
- Modify: `src/briefing/scheduler/dispatch.py` (루프 L47-56; 상단 import)
- Test: `tests/test_dispatch_audit.py`

**Interfaces:**
- Consumes: `UserBriefing.cost_usd/duration_ms` (Task 4); deliver 반환(Task 5); `mark_sent(record=)` (Task 6).
- Produces: 발송 성공 시 sent_log 에 `{sent_at, recipient, published, quarantined, duration_ms, cost_usd(Decimal), status="sent", message_id}` 기록.

- [ ] **Step 1: 실패 테스트 작성**

```python
# tests/test_dispatch_audit.py
from datetime import datetime, timezone
from briefing.scheduler.dispatch import dispatch


class _SentLog:
    def __init__(self): self.records = {}
    def already_sent(self, uid, rd): return False
    def mark_sent(self, uid, rd, *, record=None): self.records[uid] = record


def _briefing(uid, pub):
    return type("B", (), {"user_id": uid, "recipient": f"{uid}@x.com", "email": "<p>",
                          "published": pub, "quarantined": 0, "cost_usd": 1.08,
                          "duration_ms": 662000})()


def test_dispatch_writes_audit_record_on_send(monkeypatch):
    import briefing.scheduler.dispatch as d
    monkeypatch.setattr(d, "users_due_now", lambda users, now, **k: users)
    monkeypatch.setattr(d, "run_briefing", lambda *a, **k: [_briefing("u1", 5)])
    sent = _SentLog()
    now = datetime(2026, 7, 8, 7, 0, 12, tzinfo=timezone.utc)
    dispatch(None, None, ["u1"], now, deliver_fn=lambda b: {"MessageId": "MID-9"},
             run_date="2026-07-08", sent_log=sent)
    r = sent.records["u1"]
    assert r["status"] == "sent" and r["message_id"] == "MID-9"
    assert r["published"] == 5 and r["duration_ms"] == 662000
    assert r["recipient"] == "u1@x.com" and r["sent_at"] == "2026-07-08T07:00:12+00:00"
    assert float(r["cost_usd"]) == 1.08     # Decimal 로 저장됨
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_dispatch_audit.py -v`
Expected: FAIL — `KeyError: 'status'` (현재 mark_sent 는 record 없이 호출됨)

- [ ] **Step 3: 구현**

`dispatch.py` 상단에 `from decimal import Decimal` 추가. 루프(L48-56)를 교체:

```python
    for b in briefings:
        if not should_deliver(b):                                   # QUARANTINE/빈 발행 → skip
            continue
        if sent_log is not None and sent_log.already_sent(b.user_id, rd):
            continue                                                # 중복 발송 방지
        resp = deliver_fn(b)                                        # 비가역: SES 발송(응답=MessageId)
        if sent_log is not None:
            record = {
                "sent_at": now_utc.isoformat(),
                "recipient": b.recipient,
                "published": b.published,
                "quarantined": b.quarantined,
                "duration_ms": b.duration_ms,
                # DynamoDB 는 float 거부 → Decimal(str()). 읽을 때 admin.py 가 float() 환원.
                "cost_usd": Decimal(str(round(b.cost_usd, 6))),
                "status": "sent",
                "message_id": (resp or {}).get("MessageId", ""),
            }
            sent_log.mark_sent(b.user_id, rd, record=record)
        delivered.append(b.user_id)
    return delivered
```

- [ ] **Step 4: 통과 + 회귀 확인**

Run: `uv run pytest tests/test_dispatch_audit.py -v && uv run pytest -q`
Expected: 새 PASS, 기존 전부 PASS.

- [ ] **Step 5: 커밋**

```bash
git add src/briefing/scheduler/dispatch.py tests/test_dispatch_audit.py
git commit -m "feat(dispatch): 발송 시 audit 레코드(비용·시간·기사수·MessageId) sent_log 기록"
```

---

### Task 8: webapi — claims 헬퍼 추출 + GET /admin/emails

**Files:**
- Create: `src/briefing/webapi/authz.py`
- Create: `src/briefing/webapi/admin.py`
- Modify: `src/briefing/webapi/app.py` (`_parse_groups`·`_event_from_request`·`_claims` 제거 후 authz 재사용; 라우터 include)
- Test: `tests/test_webapi_admin_route.py`

**Interfaces:**
- Consumes: 없음(신규 표면).
- Produces: `authz.claims_from_request(req) -> dict`, `authz.require_admin(req) -> dict`; `admin.router`(`GET /admin/emails`).

- [ ] **Step 1: authz 추출(리팩토링) — 회귀 테스트로 안전망**

먼저 `webapi/authz.py` 생성(app.py 의 3함수 이동):

```python
# src/briefing/webapi/authz.py
"""authz — JWT claims 추출 + admin 게이트(app.py·admin.py 공유). role 은 이 계층 밖으로 안 나간다."""
from __future__ import annotations

from fastapi import HTTPException, Request


def _event_from_request(req: Request) -> dict:
    return req.scope.get("aws.event") or {}


def _parse_groups(raw) -> set[str]:
    """cognito:groups 정규화 — HTTP API v2 는 배열 claim 을 "[a b]" 문자열로 평탄화(list·str 둘 다 수용)."""
    if raw is None:
        return set()
    if isinstance(raw, (list, tuple)):
        return {str(g).strip() for g in raw}
    return {g for g in str(raw).strip("[]").replace(",", " ").split() if g}


def claims_from_request(req: Request) -> dict:
    """JWT id-token claims → {"sub","email","is_admin"}. 401 if 미존재/비 id-token/미검증."""
    ev = _event_from_request(req)
    try:
        c = ev["requestContext"]["authorizer"]["jwt"]["claims"]
    except (KeyError, TypeError):
        raise HTTPException(status_code=401, detail="JWT claims unavailable")
    if c.get("token_use") != "id":
        raise HTTPException(status_code=401, detail="id token required")
    if str(c.get("email_verified")).lower() != "true":
        raise HTTPException(status_code=401, detail="email not verified")
    sub, email = c.get("sub"), c.get("email")
    if not sub or not email:
        raise HTTPException(status_code=401, detail="sub/email claim missing")
    return {"sub": sub, "email": email,
            "is_admin": "admins" in _parse_groups(c.get("cognito:groups"))}


def require_admin(req: Request) -> dict:
    """admin 전용 게이트 — is_admin 아니면 403. role 이 등장하는 유일 지점(집행)."""
    cl = claims_from_request(req)
    if not cl["is_admin"]:
        raise HTTPException(status_code=403, detail="admin only")
    return cl
```

`app.py` 에서 `_event_from_request`·`_parse_groups`·`_claims` 정의를 **삭제**하고, 상단에 `from .authz import claims_from_request` 추가. `get_profile`·`put_profile` 안의 `_claims(req)` 호출을 `claims_from_request(req)` 로 치환.

- [ ] **Step 2: 리팩토링 회귀 확인**

Run: `uv run pytest tests/test_webapi_profile_route.py tests/test_webapi_trial_route.py -v`
Expected: 기존 profile/trial 테스트 전부 PASS(동작 불변 — 순수 이동)

- [ ] **Step 3: admin 라우트 실패 테스트 작성**

```python
# tests/test_webapi_admin_route.py
from decimal import Decimal

import briefing.webapi.admin as admin_mod
from fastapi import Request, HTTPException


def _event(groups):
    return {"requestContext": {"authorizer": {"jwt": {"claims": {
        "token_use": "id", "email_verified": "true", "sub": "s", "email": "a@x.com",
        "cognito:groups": groups}}}}}


def _scope(groups):
    return {"type": "http", "aws.event": _event(groups), "headers": []}


class _FakeTable:
    def scan(self, **kw):
        return {"Items": [{"user_id": "u1", "recipient": "a@x.com", "run_date": "2026-07-08",
                           "sent_at": "2026-07-08T07:00:12+00:00", "published": 5,
                           "quarantined": 0, "duration_ms": 662000,
                           "cost_usd": Decimal("1.08"), "status": "sent", "message_id": "MID-1"}]}


def test_admin_list_emails_returns_rows_and_totals(monkeypatch):
    monkeypatch.setattr(admin_mod, "_sent_log_table", lambda: _FakeTable())
    out = admin_mod.list_emails(Request(_scope("[admins]")))
    assert out["totals"]["count"] == 1
    assert out["emails"][0]["recipient"] == "a@x.com"
    assert out["emails"][0]["cost_usd"] == 1.08   # Decimal→float 환원


def test_non_admin_forbidden(monkeypatch):
    monkeypatch.setattr(admin_mod, "_sent_log_table", lambda: _FakeTable())
    try:
        admin_mod.list_emails(Request(_scope("[]")))
        assert False, "should have raised 403"
    except HTTPException as e:
        assert e.status_code == 403


def test_admin_route_registered_on_app():
    from briefing.webapi.app import app
    assert any(getattr(r, "path", None) == "/admin/emails" for r in app.routes)
```

- [ ] **Step 4: 실패 확인**

Run: `uv run pytest tests/test_webapi_admin_route.py -v`
Expected: FAIL — `ModuleNotFoundError: briefing.webapi.admin`

- [ ] **Step 5: 구현 — admin.py**

```python
# src/briefing/webapi/admin.py
"""admin — 운영 모니터링 읽기 API(admin 전용). role 은 여기(require_admin)서만 집행된다.

GET /admin/emails: briefing-sent-log 을 Scan(작은 테이블) → 발송 이메일 리스트(비용·시간·기사수).
cost_usd 는 DDB Decimal → JSON float 환원. v1=Scan(GSI 불필요).
"""
from __future__ import annotations

import os
from decimal import Decimal

from fastapi import APIRouter, Request

from .authz import require_admin

router = APIRouter()


def _sent_log_table():
    """운영 boto3 Table(lazy). 테스트는 monkeypatch 로 fake 주입."""
    import boto3
    region = os.getenv("AWS_REGION", "us-east-1")
    name = os.getenv("SENT_LOG_TABLE", "briefing-sent-log")
    return boto3.resource("dynamodb", region_name=region).Table(name)


def _to_json(item: dict) -> dict:
    """DDB item → JSON 안전(Decimal→float/int)."""
    out = {}
    for k, v in item.items():
        out[k] = float(v) if isinstance(v, Decimal) else v
    return out


@router.get("/admin/emails")
def list_emails(req: Request, date: str | None = None, limit: int = 200) -> dict:
    require_admin(req)   # 403 if not admin — role 집행 단일 지점
    table = _sent_log_table()
    kw: dict = {}
    if date:
        from boto3.dynamodb.conditions import Attr
        kw["FilterExpression"] = Attr("run_date").eq(date)
    items = [_to_json(i) for i in table.scan(**kw).get("Items", [])]
    items.sort(key=lambda x: x.get("sent_at", ""), reverse=True)
    items = items[:limit]
    total_cost = round(sum(float(i.get("cost_usd", 0)) for i in items), 4)
    durs = [i.get("duration_ms", 0) for i in items]
    totals = {"count": len(items), "cost_usd": total_cost,
              "avg_duration_ms": int(sum(durs) / len(durs)) if durs else 0}
    return {"emails": items, "totals": totals}
```

`app.py` 하단에 라우터 등록:

```python
from .admin import router as admin_router  # noqa: E402
app.include_router(admin_router)
```

- [ ] **Step 6: 통과 + 회귀 확인**

Run: `uv run pytest tests/test_webapi_admin_route.py tests/test_webapi_profile_route.py tests/test_webapi_trial_route.py -v && uv run pytest -q`
Expected: 새 PASS(admin 200 / 비admin 403), 리팩토링·기존 전부 PASS.

- [ ] **Step 7: 커밋**

```bash
git add src/briefing/webapi/authz.py src/briefing/webapi/admin.py src/briefing/webapi/app.py tests/test_webapi_admin_route.py
git commit -m "feat(webapi): authz 헬퍼 추출 + GET /admin/emails(require_admin, sent-log Scan)"
```

---

### Task 9: deploy_api — webapi Lambda IAM 에 sent-log 읽기 추가

**Files:**
- Modify: `src/briefing/webapi/deploy_api.py` (Lambda 역할 정책 — 현재 briefing-users + briefing-trials 만)

- [ ] **Step 1: 현재 정책 확인**

Run: `grep -n "briefing-users\|briefing-trials\|dynamodb:" src/briefing/webapi/deploy_api.py`
Expected: users/trials 리소스에 대한 `dynamodb:GetItem/UpdateItem/...` 문(statement) 확인. sent-log 없음.

- [ ] **Step 2: 정책에 sent-log 읽기 추가**

Lambda 역할 인라인 정책의 Resource 목록(또는 Statement)에 `briefing-sent-log` 에 대한 읽기 권한을 추가한다. 기존 users/trials statement 옆에 추가(리전/계정은 기존 문과 동일 패턴 재사용):

```python
    {
        "Effect": "Allow",
        "Action": ["dynamodb:Scan", "dynamodb:GetItem", "dynamodb:Query"],
        "Resource": f"arn:aws:dynamodb:{region}:{account_id}:table/briefing-sent-log",
    },
```

(정확한 변수명 `region`·`account_id`·정책 dict 위치는 Step 1 grep 결과에 맞춘다 — 기존 trials statement 를 복제해 테이블명만 교체하는 것이 가장 안전.)

- [ ] **Step 3: 검증(배포 없이 정적 확인)**

Run: `grep -n "briefing-sent-log" src/briefing/webapi/deploy_api.py`
Expected: 새 statement 1건 매치. `uv run ruff check src/briefing/webapi/deploy_api.py` clean.

- [ ] **Step 4: 커밋**

```bash
git add src/briefing/webapi/deploy_api.py
git commit -m "feat(deploy_api): webapi Lambda 역할에 briefing-sent-log 읽기(Scan/Get/Query) 추가"
```

---

### Task 10: 프론트엔드 — /admin 대시보드

**Files:**
- Modify: `web/src/auth/session.ts` (`isAdmin()` 헬퍼)
- Create: `web/src/pages/Admin.tsx`
- Modify: `web/src/App.tsx` (`/admin` 라우트)
- Test: `web/src/pages/Admin.test.tsx`

**Interfaces:**
- Consumes: `GET /admin/emails` 응답(Task 8); `authedFetch`(기존).
- Produces: `isAdmin(): boolean`; `/admin` 라우트.

- [ ] **Step 1: 실패 테스트 작성**

```tsx
// web/src/pages/Admin.test.tsx
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import Admin from './Admin'

vi.mock('../auth/session', () => ({
  isAdmin: () => true,
  authedFetch: vi.fn(async () => ({ ok: true, json: async () => ({
    emails: [{ user_id: 'u1', recipient: 'a@x.com', run_date: '2026-07-08',
      sent_at: '2026-07-08T07:00:12Z', published: 5, quarantined: 0,
      duration_ms: 662000, cost_usd: 1.08, status: 'sent', message_id: 'MID-1' }],
    totals: { count: 1, cost_usd: 1.08, avg_duration_ms: 662000 } }) })),
}))

beforeEach(() => vi.clearAllMocks())

describe('Admin dashboard', () => {
  it('발송 이메일 행과 비용을 렌더한다', async () => {
    render(<Admin />)
    expect(await screen.findByText('a@x.com')).toBeInTheDocument()
    expect(await screen.findByText(/1\.08/)).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: 실패 확인**

Run: `cd web && npm test -- Admin` (또는 `npx vitest run src/pages/Admin.test.tsx`)
Expected: FAIL — `Cannot find module './Admin'`

- [ ] **Step 3: 구현 — isAdmin 헬퍼(session.ts)**

`web/src/auth/session.ts` 에 추가(id_token payload 의 cognito:groups 디코드 — 백엔드 `_parse_groups` 와 동형: 배열·문자열 모두 수용):

```ts
export function isAdmin(): boolean {
  const tok = getIdToken()
  if (!tok) return false
  try {
    const payload = JSON.parse(atob(tok.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')))
    const g = payload['cognito:groups']
    const groups = Array.isArray(g) ? g : String(g ?? '').replace(/[[\]]/g, '').split(/[ ,]+/)
    return groups.includes('admins')
  } catch {
    return false
  }
}
```

(`getIdToken` 이 이미 export 되어 있지 않으면 함께 export.)

- [ ] **Step 4: 구현 — Admin.tsx**

```tsx
// web/src/pages/Admin.tsx
import { useEffect, useState } from 'react'
import { isAdmin, authedFetch } from '../auth/session'

type Email = {
  user_id: string; recipient: string; run_date: string; sent_at: string
  published: number; quarantined: number; duration_ms: number; cost_usd: number
  status: string; message_id: string
}
const mins = (ms: number) => `${Math.floor(ms / 60000)}m${Math.round((ms % 60000) / 1000)}s`

export default function Admin() {
  const [rows, setRows] = useState<Email[]>([])
  const [err, setErr] = useState('')
  useEffect(() => {
    if (!isAdmin()) { setErr('관리자 전용'); return }
    authedFetch(`${import.meta.env.VITE_API_BASE}/admin/emails`)
      .then((r) => r.json()).then((d) => setRows(d.emails ?? []))
      .catch(() => setErr('불러오기 실패'))
  }, [])
  if (err) return <p>{err}</p>
  return (
    <div>
      <h2>관리자 · 발송 이메일</h2>
      <table>
        <thead><tr><th>수신자</th><th>발송시각</th><th>기사</th><th>소요</th><th>비용</th><th>상태</th></tr></thead>
        <tbody>
          {rows.map((e) => (
            <tr key={`${e.user_id}-${e.run_date}`}>
              <td>{e.recipient}</td><td>{e.sent_at}</td><td>{e.published}</td>
              <td>{mins(e.duration_ms)}</td><td>≈${e.cost_usd.toFixed(2)}</td><td>{e.status}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
```

- [ ] **Step 5: 구현 — /admin 라우트(App.tsx)**

`App.tsx` 에 `import Admin from './pages/Admin'` 추가하고 Routes 안에 추가:

```tsx
          <Route path="/admin" element={<Admin />} />
```

- [ ] **Step 6: 통과 + 프론트 빌드 확인**

Run: `cd web && npm test -- Admin && npm run build`
Expected: Admin 테스트 PASS, `tsc -b && vite build` 성공.

- [ ] **Step 7: 커밋**

```bash
git add web/src/auth/session.ts web/src/pages/Admin.tsx web/src/App.tsx web/src/pages/Admin.test.tsx
git commit -m "feat(web): /admin 발송 모니터링 대시보드 + isAdmin 게이팅"
```

---

### Task 11: docs 색인 상태 갱신 + 최종 검증

**Files:**
- Modify: `docs/README.md` (admin-monitoring 행 DRAFT → SHIPPED, 배포 후)

- [ ] **Step 1: 전체 백엔드 회귀**

Run: `uv run pytest -q && uv run ruff check src tests`
Expected: 전부 PASS(기존 208 + 신규), ruff clean.

- [ ] **Step 2: 로컬 baseline 스모크(계측 무해 확인)**

Run: `uv run python -m briefing.local.run`
Expected: 기존과 동일 동작(계측은 additive — 출력 무붕괴).

- [ ] **Step 3: (배포는 별도 세션·승인 후)** `deploy_api` → `deploy_web` 후 라이브 검증 시 `docs/README.md` admin-monitoring 행을 SHIPPED 로 갱신, 커밋.

---

## Self-Review

**1. Spec coverage** — 스펙 §6 통합 지점 10개 매핑: #1 author cost=T2 · #2 certify 추정=T3(certifier 무수정으로 **리팩토링**: verify_card 에서 계산) · #3 pipeline carrier/timer=T4 · #4 deliver 반환=T5 · #5 dispatch audit=T7 · #6 mark_sent=T6 · #7 admin.py=T8 · #8 include_router=T8 · #9 deploy_api IAM=T9 · #10 프론트=T10. §5 데이터모델=T4/T6/T1. §7 API=T8. §8 프론트=T10. §9 엣지(dry-run 미기록=구조상 dispatch 만 기록·§Global · Float→Decimal=T7 · 비admin 403=T8). §10 테스트=각 태스크 TDD. **갭 없음.**

**2. Placeholder scan** — 모든 코드 스텝에 실코드 포함. T9 만 기존 정책 dict 위치에 의존(grep 선행 스텝으로 구체화) — 이는 저장소 실물 확인 후 복제이므로 placeholder 아님.

**3. Type consistency** — `UsageRecorder.add/total`·`EST_CERTIFY_USD_PER_ENTAILMENT`·파라미터명 `recorder`·`UserBriefing.cost_usd/duration_ms`·`mark_sent(record=)`·`DeliverFn→dict|None`·`claims_from_request/require_admin`·`_sent_log_table`·`isAdmin` — 태스크 간 일치 확인.

> **스펙 대비 1건 정제:** 스펙 §6 #2 는 `certifier.py` 를 가리켰으나, 플랜은 **gate.verify_card** 에서 certify 추정을 계산한다 — certifier 의 "envelope 4필드 외 미열람·최소 컨텍스트" 불변식을 지키기 위해 certifier.py 를 건드리지 않는 편이 옳다(동일 결과, 더 안전).
