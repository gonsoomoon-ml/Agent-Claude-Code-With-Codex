"""runtime 배포 어댑터(②)의 *순수·테스트가능* 단위 — AWS·CLI·네트워크 0.

검증 대상(결정론):
  - deploy_runtime.runtime_env  : 컨테이너 주입 env (DEBUG on/off forward 포함)
  - deploy_runtime._upsert_env_lines : 루트 .env writeback (idempotent — 재배포해도 중복 0)
  - invoke_runtime.parse_sse_event : SSE `data: {...}` 파싱(노이즈 견고)
  - _smoke.smoke_fns/smoke_users   : smoke invoke 가 *결정론으로 PUBLISH* (배포 plumbing 검증의 신뢰성)

AWS 호출(configure/launch/teardown)은 실 배포(done-when)로 검증 — 여기선 순수 로직만.
"""
from __future__ import annotations

import dataclasses

from briefing.core.config import Settings, load_settings


def _settings(tmp_path, *, users_dir: str | None = None, **overrides) -> Settings:
    # load_settings() 기본값 위에 override — Settings 에 필드가 추가돼도(③ DB 등) 깨지지 않게(replace).
    base = dict(
        region="us-east-1",
        author_model_id="global.anthropic.claude-sonnet-4-6",
        supervisor_model_id="global.anthropic.claude-sonnet-4-6",
        ses_sender="briefing@example.com",
        source_store_path=str(tmp_path / "store"),
        users_dir=users_dir or str(tmp_path / "nousers"),
        author_provider="bedrock", certifier_provider="bedrock", judge_provider="bedrock",   # 이 폴더 .env 가 subscription 이어도 기본 경로를 본다
    )
    return dataclasses.replace(load_settings(), **(base | overrides))


# ───────────────────────── runtime_env (DEBUG on/off forward) ─────────────────────────

def test_runtime_env_includes_container_core_keys(tmp_path, monkeypatch):
    from briefing.runtime.deploy_runtime import runtime_env

    monkeypatch.delenv("DEBUG", raising=False)
    monkeypatch.delenv("LABEL_MODEL_ID", raising=False)
    env = runtime_env(_settings(tmp_path, label_model_id=""))
    # 컨테이너는 .env 를 안 읽음 → launch(env_vars=...) 로 주입되는 핵심 키들
    assert env["AWS_REGION"] == "us-east-1"
    assert "LABEL_MODEL_ID" not in env               # 설정 안 하면 안 넘긴다(컨테이너도 RELEVANCE 상속)
    assert env["AUTHOR_MODEL_ID"] == "global.anthropic.claude-sonnet-4-6"
    assert env["SES_SENDER"] == "briefing@example.com"
    assert env["CLAUDE_CODE_USE_BEDROCK"] == "1"   # author=claude -p 를 Bedrock 로 라우팅
    assert env["ENABLE_TOOL_SEARCH"] == "false"
    assert env["BACKEND"] == "dynamo"              # ③ DB: 클라우드는 dynamo backend(영속)


def test_runtime_env_forwards_label_model_id_when_set(tmp_path):
    """★ 화이트리스트에 없으면 프로덕션은 조용히 Haiku 기본값으로 돈다(스펙 §6.1) — 설정값은 반드시 컨테이너로."""
    from briefing.runtime.deploy_runtime import runtime_env

    env = runtime_env(_settings(tmp_path, label_model_id="global.anthropic.claude-sonnet-5-5"))
    assert env["LABEL_MODEL_ID"] == "global.anthropic.claude-sonnet-5-5"


def test_runtime_env_forwards_debug_on(tmp_path, monkeypatch):
    from briefing.runtime.deploy_runtime import runtime_env

    monkeypatch.setenv("DEBUG", "1")
    assert runtime_env(_settings(tmp_path))["DEBUG"] == "1"   # 호스트 DEBUG → 컨테이너 is_debug() on


def test_runtime_env_debug_off_forwards_empty(tmp_path, monkeypatch):
    from briefing.runtime.deploy_runtime import runtime_env

    monkeypatch.delenv("DEBUG", raising=False)
    # 미설정 시 빈 문자열 forward → 컨테이너 is_debug()==False (zero overhead)
    assert runtime_env(_settings(tmp_path))["DEBUG"] == ""


def test_runtime_env_overrides_store_path_for_container():
    """컨테이너는 비-root 유저(uid 1000) → /app 하위 상대경로(./.data) 쓰기 불가(Errno 13).

    실 invoke 가 PermissionError 로 잡아낸 회귀 — host 경로와 무관하게 *writable 절대경로* 주입.
    """
    from briefing.runtime.deploy_runtime import CONTAINER_STORE_PATH, runtime_env

    # host 가 비-writable 상대경로(./.data)여도 컨테이너엔 writable 절대경로 주입
    s = dataclasses.replace(load_settings(), source_store_path="./.data/source_store")
    assert runtime_env(s)["SOURCE_STORE_PATH"] == CONTAINER_STORE_PATH
    assert CONTAINER_STORE_PATH.startswith("/tmp/")   # ephemeral writable (v1; ③ DB 백킹 후속)


# ───────────────────────── .env writeback (idempotent) ─────────────────────────

def test_upsert_env_lines_replaces_value_without_duplicating(tmp_path):
    from briefing.runtime.deploy_runtime import _upsert_env_lines

    base = "AWS_REGION=us-east-1\nSES_SENDER=x@y.com\n"
    once = _upsert_env_lines(base, {"BRIEFING_RUNTIME_ARN": "arn:1"}, section="# Briefing Runtime")
    twice = _upsert_env_lines(once, {"BRIEFING_RUNTIME_ARN": "arn:2"}, section="# Briefing Runtime")

    assert twice.count("BRIEFING_RUNTIME_ARN=") == 1     # 재배포해도 중복 라인 0
    assert "BRIEFING_RUNTIME_ARN=arn:2" in twice
    assert "arn:1" not in twice
    assert twice.count("# Briefing Runtime") == 1        # 섹션 마커도 중복 안 됨


def test_upsert_env_lines_preserves_unrelated_keys(tmp_path):
    from briefing.runtime.deploy_runtime import _upsert_env_lines

    base = "AWS_REGION=us-east-1\nSES_SENDER=x@y.com\n"
    out = _upsert_env_lines(base, {"BRIEFING_RUNTIME_ID": "rid-1"}, section="# Briefing Runtime")
    assert "AWS_REGION=us-east-1" in out and "SES_SENDER=x@y.com" in out


# ───────────────────────── SSE 파싱 ─────────────────────────

def test_parse_sse_event_parses_data_prefixed_json():
    from briefing.runtime.invoke_runtime import parse_sse_event

    ev = parse_sse_event(b'data: {"type": "user", "user": "gonsoo", "published": 1}')
    assert ev is not None and ev["user"] == "gonsoo" and ev["published"] == 1


def test_parse_sse_event_ignores_blank_and_nonjson():
    from briefing.runtime.invoke_runtime import parse_sse_event

    assert parse_sse_event(b"") is None
    assert parse_sse_event(b"\n") is None
    assert parse_sse_event(b"not json at all") is None


# ───────────────────────── smoke = 결정론 PUBLISH ─────────────────────────

def test_harness_fns_fakes_only_fetch(tmp_path):
    """②b harness 모드: fetch 만 fake(네트워크/RSS/fragile 회피), draft/verify 는 *진짜* claude/codex.

    → run_briefing 에 fetch_article_fn 만 주입되고 draft/revise/verify 는 미주입(None=실제 하니스).
    """
    from briefing.runtime._smoke import harness_fns

    # 수집 seam 2종(본문·헤드라인)만 fake — draft/revise/verify 키 *없음* → 실제 CLI
    assert set(harness_fns()) == {"fetch_article_fn", "headline_fetch_fn"}


def test_smoke_users_synthesizes_when_no_real_users(tmp_path):
    from briefing.runtime._smoke import smoke_users

    users = smoke_users(_settings(tmp_path))   # users_dir 없음 → 합성 사용자 1명
    assert len(users) == 1
    assert users[0].recipient                  # 비지 않은 수신자(렌더/발송 경로 통과용)


def test_smoke_invoke_publishes_deterministically(tmp_path):
    from briefing.runtime._smoke import smoke_fns, smoke_users
    from briefing.core.pipeline import run_briefing
    from briefing.core.stores.source_store import SourceStore

    settings = _settings(tmp_path)
    store = SourceStore(settings.source_store_path)
    users = smoke_users(settings)

    out = run_briefing(settings, store, users, window_hours=24, **smoke_fns())

    assert out, "smoke invoke 가 사용자별 브리핑을 산출해야 함(per-user SSE 의 원천)"
    assert out[0].published >= 1               # fake 검증 = 전부 VERIFIED → PUBLISH
    assert out[0].quarantined == 0


# ── production fns 배선 (2026-07-27: trial 경로가 판정자를 안 쓰던 결함) ──────────

def test_production_fns_wires_judge_when_enabled(tmp_path):
    """relevance_llm_enabled=True 면 관련성 판정자·top-K 선별자가 주입된다."""
    from briefing.runtime.agentcore_runtime import _production_fns

    fns = _production_fns(_settings(tmp_path, relevance_llm_enabled=True))
    assert "relevance_fn" in fns and "select_fn" in fns and "headline_select_fn" in fns
    assert "label_fn" in fns   # 핵심 3 + 분야 라벨(한 호출) — 정기·체험·수동이 같은 묶음을 쓴다
    assert "headline_area_fn" in fns   # 헤드라인 칸 분야 묶음
    assert "rereport_fn" in fns   # 재보도 판정자(2026-10-28) — 정기·체험이 같은 판정자


def test_production_fns_use_claude_cli_when_judge_provider_is_subscription(tmp_path, monkeypatch):
    """JUDGE_PROVIDER=subscription → 판정 6종이 `claude -p` 경로(relevance_claude)로 · Bedrock 클라이언트는 만들지 않는다."""
    from briefing.core.retrieval import relevance_bedrock as rb
    from briefing.core.retrieval import relevance_claude as rc
    from briefing.runtime.agentcore_runtime import _production_fns

    calls = []
    monkeypatch.setattr(rc, "_run_author", lambda system, user, settings, **kw: calls.append(kw) or "YES")
    monkeypatch.setattr(rb, "_client", lambda region: (_ for _ in ()).throw(AssertionError("Bedrock 클라이언트 생성 금지")))
    fns = _production_fns(_settings(tmp_path, relevance_llm_enabled=True, judge_provider="subscription"))
    assert set(fns) == {"relevance_fn", "select_fn", "headline_select_fn", "headline_area_fn", "label_fn", "rereport_fn"}
    assert fns["relevance_fn"]("제목", "본문") is True
    fns["rereport_fn"]("A 본문", "B 본문")
    fns["headline_area_fn"](["제목 1"])
    assert len(calls) == 3 and all(c["provider"] == "subscription" and c["tools"] is False for c in calls)


def test_production_fns_default_judge_provider_stays_on_bedrock(tmp_path, monkeypatch):
    """기본(bedrock) = 종전대로 Converse — `claude -p` 판정 경로는 호출되지 않는다."""
    from briefing.core.retrieval import relevance_bedrock as rb
    from briefing.core.retrieval import relevance_claude as rc
    from briefing.runtime.agentcore_runtime import _production_fns

    sent = []

    class C:
        def converse(self, **kw):
            sent.append(kw["modelId"])
            return {"output": {"message": {"content": [{"text": "YES"}]}}}

    monkeypatch.setattr(rb, "_client", lambda region: C())
    monkeypatch.setattr(rc, "_run_author", lambda *a, **kw: (_ for _ in ()).throw(AssertionError("claude -p 판정 금지")))
    s = _settings(tmp_path, relevance_llm_enabled=True)
    assert _production_fns(s)["relevance_fn"]("제목", "본문") is True
    assert sent == [s.relevance_model_id]


def test_production_fns_empty_when_disabled(tmp_path):
    """플래그 off(로컬·테스트 기본)면 주입 없음 → curate 가 결정론 키워드로 폴백."""
    from briefing.runtime.agentcore_runtime import _production_fns

    assert _production_fns(_settings(tmp_path, relevance_llm_enabled=False)) == {}


def test_trial_uses_same_production_fns_as_scheduled(tmp_path):
    """★ trial 도 정기 발송과 **같은** 필터를 써야 한다.

    2026-07-27 실측 결함: trial 은 `run_briefing_fn=run_briefing`(맨 함수)을 넘겨 판정자가 빠졌고,
    그 결과 체험 메일이 키워드 전용 필터로 나갔다(비-AI 기사 발행). 웹 퍼널의 첫인상 경로다.
    """
    import pathlib

    import briefing.runtime.agentcore_runtime as rt

    # 소스 검사인 이유: entrypoint 는 @app.entrypoint 로 감싸져 호출 검증이 무겁고, 여기서 지키려는 것은
    # "두 경로가 같은 묶음을 쓴다"는 **구조 불변식**이다(맨 run_briefing 을 넘기면 필터가 조용히 빠진다).
    src = pathlib.Path(rt.__file__).read_text(encoding="utf-8")
    trial_part = src[src.index('mode == "trial"'):src.index('if mode == "smoke"')]
    assert "_production_fns" in trial_part, "trial 경로가 production fns 를 주입하지 않는다"


def test_scheduled_uses_production_fns(tmp_path):
    """★ 정기 발송(scheduled)도 production fns(Haiku 판정·선별)를 넘겨야 한다.

    2026-10-17 실측 결함: scheduled 분기의 dispatch(...) 가 fns 를 안 넘겨, 7월 판정자 배포 후 100일간
    매일 밤 run 의 Haiku(global 프로필) 호출이 0건 — require_ai·select:llm 소스가 키워드·최신순으로만 돌았다.
    trial 테스트와 같은 구조 불변식(소스 검사)으로 지킨다.
    """
    import pathlib

    import briefing.runtime.agentcore_runtime as rt

    src = pathlib.Path(rt.__file__).read_text(encoding="utf-8")
    scheduled_part = src[src.index('mode == "scheduled"'):src.index('mode == "trial"')]
    assert "_production_fns" in scheduled_part, "scheduled 경로가 production fns 를 주입하지 않는다"


def test_runtime_env_forwards_dedup_lookback(tmp_path):
    from briefing.runtime.deploy_runtime import runtime_env
    assert runtime_env(_settings(tmp_path, dedup_lookback_days=45))["DEDUP_LOOKBACK_DAYS"] == "45"


def test_smoke_fns_never_touch_network_for_headline_sources(tmp_path, monkeypatch):
    """smoke = 네트워크 0 계약 — 헤드라인 전용 소스(aitimes)를 구독해도 실 피드를 부르지 않는다."""
    from briefing.core.pipeline import run_briefing
    from briefing.core.retrieval import headlines
    from briefing.core.stores.source_store import SourceStore
    from types import SimpleNamespace

    from briefing.runtime._smoke import smoke_fns

    real_calls: list[str] = []   # raise 대신 기록 — collect_headlines 는 fetch 예외를 삼키므로(degradation) 기록으로 판정

    monkeypatch.setattr(headlines, "fetch_headline_feed", lambda s, _w: real_calls.append(s.key) or [])
    settings = _settings(tmp_path)
    user = SimpleNamespace(id="u", recipient="u@x", sources=("aws-ml", "aitimes"), depth="full",
                           lens="general", skill_md="", send_hour=7)
    out = run_briefing(settings, SourceStore(settings.source_store_path), [user], window_hours=24, **smoke_fns())
    assert real_calls == []
    assert out[0].published >= 1


def test_runtime_env_forwards_effort_and_interp_only_when_set(tmp_path):
    """컨테이너는 .env 를 못 읽는다 — 설정한 값만 넘기고 빈 값은 빼서(빈 값 = 상속/CLI 기본) 컨테이너도 같은 해석."""
    from briefing.runtime.deploy_runtime import runtime_env
    unset = runtime_env(_settings(tmp_path, author_effort="", interp_model_id="", interp_effort=""))
    assert not {"AUTHOR_EFFORT", "INTERP_MODEL_ID", "INTERP_EFFORT"} & unset.keys()
    env = runtime_env(_settings(tmp_path, author_effort="medium",
                                interp_model_id="global.anthropic.claude-sonnet-5", interp_effort="default"))
    assert (env["AUTHOR_EFFORT"], env["INTERP_MODEL_ID"], env["INTERP_EFFORT"]) == (
        "medium", "global.anthropic.claude-sonnet-5", "default")


# ── 런타임 IAM: 코드가 부르는 DynamoDB 작업 ⊆ 정책 (2026-10-18 결함) ──────────

def test_runtime_iam_allows_every_dynamodb_call_the_runtime_makes():
    """런타임이 부르는 boto3 DynamoDB 작업마다 deploy_runtime 정책에 그 액션이 있어야 한다.

    2026-10-18 실측: article-identity dedup(96dee74, v47)이 source-store `batch_get_item` 을 새로 썼는데 정책에
    `dynamodb:BatchGetItem` 이 없어 매 run AccessDenied → dedup 전체 fail-open(10-17 아침 전날 기사 3건 재발행).
    fake 로 도는 단위 테스트는 IAM 을 못 보므로, 호출 목록과 정책을 소스에서 직접 대조한다.
    """
    import re
    from pathlib import Path

    from briefing.runtime.deploy_runtime import DYNAMO_ACTIONS

    pkg = Path(__file__).resolve().parents[1] / "src" / "briefing"
    files = ["core/stores/dynamo.py", "scheduler/sent_log.py", "runtime/agentcore_runtime.py"]   # boto3 DDB 를 직접 부르는 런타임 코드
    ops = {m for f in files for m in re.findall(
        r"\.(get_item|put_item|query|scan|update_item|delete_item|batch_get_item|batch_write_item)\(",
        (pkg / f).read_text(encoding="utf-8"))}
    needed = {"dynamodb:" + "".join(w.capitalize() for w in op.split("_")) for op in ops}
    assert "dynamodb:BatchGetItem" in needed                       # 검사가 실제로 이 호출을 본다(자기 검증)
    assert needed <= set(DYNAMO_ACTIONS), f"정책에 없는 DynamoDB 액션: {sorted(needed - set(DYNAMO_ACTIONS))}"


# ───────────────────────── runtime_env (주간 1-B: WEEKLY_* forward) ─────────────────────────

def test_runtime_env_forwards_weekly_keys_including_figure(tmp_path, monkeypatch):
    """★ 화이트리스트에 없으면 컨테이너의 WEEKLY_ADMIN_USER_ID 가 비어 매주 `failed`(LABEL_MODEL_ID 와 같은 함정).
    FIGURE 도 전달한다(2026-11-07 (d)): 컨테이너에 playwright + Chromium + Noto CJK 를 넣어 그림 트랙이 클라우드에서 돈다."""
    from briefing.runtime.deploy_runtime import runtime_env

    s = _settings(tmp_path)
    for k, v in {"WEEKLY_ADMIN_USER_ID": "u-1", "WEEKLY_AUTHOR_MODEL_ID": "m-w", "WEEKLY_AUTHOR_EFFORT": "high",
                 "WEEKLY_SELECT_MODEL_ID": "m-s", "WEEKLY_STRICT": "0", "WEEKLY_FIGURE": "1"}.items():
        monkeypatch.setenv(k, v)
    env = runtime_env(s)
    assert env["WEEKLY_ADMIN_USER_ID"] == "u-1" and env["WEEKLY_AUTHOR_MODEL_ID"] == "m-w"
    assert env["WEEKLY_AUTHOR_EFFORT"] == "high" and env["WEEKLY_SELECT_MODEL_ID"] == "m-s"
    assert env["WEEKLY_STRICT"] == "0"
    assert env["WEEKLY_FIGURE"] == "1"


def test_runtime_env_omits_unset_weekly_keys(tmp_path, monkeypatch):
    """설정 안 한 WEEKLY_* 는 넘기지 않는다(컨테이너도 run.py 기본값으로 같은 해석 — FIGURE 는 기본 끔)."""
    from briefing.runtime.deploy_runtime import WEEKLY_ENV_KEYS, runtime_env

    s = _settings(tmp_path)
    for k in WEEKLY_ENV_KEYS:
        monkeypatch.delenv(k, raising=False)
    assert "WEEKLY_ADMIN_USER_ID" in WEEKLY_ENV_KEYS and "WEEKLY_FIGURE" in WEEKLY_ENV_KEYS
    assert not [k for k in runtime_env(s) if k.startswith("WEEKLY_")]


def test_runtime_extras_policy_allows_list_inference_profiles():
    """주간 게이트 `check_models` 가 bedrock:ListInferenceProfiles 를 부른다 — 없으면 fail-closed 로 매주 격리."""
    from briefing.runtime.deploy_runtime import runtime_extras_policy

    policy = runtime_extras_policy("123456789012")
    stmts = [st for st in policy["Statement"] if "bedrock:ListInferenceProfiles" in st["Action"]]
    assert len(stmts) == 1 and stmts[0]["Effect"] == "Allow"
    ddb = [st for st in policy["Statement"] if st["Sid"] == "DynamoStores"][0]   # 주간 표는 기존 와일드카드가 덮는다
    assert "arn:aws:dynamodb:*:123456789012:table/briefing-*" in ddb["Resource"]


# ───────────────────────── invoke_runtime.build_payload (주간 1-B 수동 호출) ─────────────────────────

def test_invoke_build_payload_weekly_modes_carry_issue_date_and_dry_run():
    """클라우드 검증(§7-4): `--mode weekly_build --issue-date 2026-11-07` · `--mode weekly_send --dry-run`."""
    from argparse import Namespace

    from briefing.runtime.invoke_runtime import build_payload

    base = dict(window_hours=24, now_utc=None, users=None, dry_run=False, email=None, sources=None, issue_date=None)
    b = build_payload(Namespace(**{**base, "mode": "weekly_build", "issue_date": "2026-11-07"}))
    assert b == {"mode": "weekly_build", "window_hours": 24, "issue_date": "2026-11-07"}
    s = build_payload(Namespace(**{**base, "mode": "weekly_send", "dry_run": True}))
    assert s == {"mode": "weekly_send", "window_hours": 24, "dry_run": True}
    d = build_payload(Namespace(**{**base, "mode": "scheduled", "issue_date": "2026-11-07"}))
    assert "issue_date" not in d                      # 데일리 payload 는 바뀌지 않는다


def test_runtime_env_forwards_weekly_author_timeout(tmp_path, monkeypatch):
    """2026-11-07 클라우드 build 실패(write 360s) — 상한은 .env 에서 컨테이너로 넘어가야 한다."""
    from briefing.runtime.deploy_runtime import runtime_env

    s = _settings(tmp_path)
    monkeypatch.setenv("WEEKLY_AUTHOR_TIMEOUT_S", "1200")
    assert runtime_env(s)["WEEKLY_AUTHOR_TIMEOUT_S"] == "1200"


# ───────────────────────── 관측(OTEL) 끄기 — `.env` BRIEFING_OBSERVABILITY (2026-11-14 결정 9) ─────────────────────────

def test_runtime_env_observability_is_on_by_default(tmp_path, monkeypatch):
    """설정이 없으면 지금 그대로 켜짐 — 기본 동작을 코드에 남긴다."""
    from briefing.runtime.deploy_runtime import runtime_env

    monkeypatch.delenv("BRIEFING_OBSERVABILITY", raising=False)
    env = runtime_env(_settings(tmp_path))
    assert env["AGENT_OBSERVABILITY_ENABLED"] == "true" and "OTEL_SDK_DISABLED" not in env


def test_runtime_env_observability_off_disables_the_otel_sdk_and_exporters(tmp_path, monkeypatch):
    """끄면 컨테이너의 `opentelemetry-instrument` 가 아무것도 내보내지 않게 한다(Dockerfile CMD 는 그대로)."""
    from briefing.runtime.deploy_runtime import runtime_env

    monkeypatch.setenv("BRIEFING_OBSERVABILITY", "0")
    env = runtime_env(_settings(tmp_path))
    assert env["AGENT_OBSERVABILITY_ENABLED"] == "false" and env["OTEL_SDK_DISABLED"] == "true"
    assert env["OTEL_TRACES_EXPORTER"] == env["OTEL_METRICS_EXPORTER"] == env["OTEL_LOGS_EXPORTER"] == "none"


def test_configure_kwargs_disable_otel_follows_the_observability_setting():
    """toolkit 의 disable_otel 이 꺼져 있어야 launch 가 계정의 Transaction Search 를 켜지 않는다."""
    from briefing.runtime.deploy_runtime import AGENT_NAME, configure_kwargs

    on, off = configure_kwargs("us-east-1", {}), configure_kwargs("us-east-1", {"BRIEFING_OBSERVABILITY": "off"})
    assert on["disable_otel"] is False and off["disable_otel"] is True
    assert on["agent_name"] == off["agent_name"] == AGENT_NAME and off["region"] == "us-east-1"
    assert off["auto_create_execution_role"] is True and off["auto_create_ecr"] is True


# ───────────────────────── ECR 이미지 1개만 유지 — `.env` BRIEFING_ECR_KEEP_LATEST (2026-11-14 결정 3) ─────────────────────────

_REG = "111122223333"
_REPO = "bedrock-agentcore-briefing_agent"
_URI = f"{_REG}.dkr.ecr.us-east-1.amazonaws.com/{_REPO}"


def _img(digest: str, *tags: str, size: int = 1_000) -> dict:
    d = {"imageDigest": f"sha256:{digest}", "imageSizeInBytes": size}
    if tags:
        d["imageTags"] = list(tags)
    return d


class _FakeControl:
    def __init__(self, *, uri=f"{_URI}:t2", version="2", live="2", ep_status="READY"):
        self.rt = {"status": "READY", "agentRuntimeVersion": version,
                   "agentRuntimeArtifact": {"containerConfiguration": {"containerUri": uri}}}
        self.ep = {"status": ep_status, "liveVersion": live}

    def get_agent_runtime(self, **kw):
        return self.rt

    def get_agent_runtime_endpoint(self, **kw):
        assert kw["endpointName"] == "DEFAULT"
        return self.ep


class _FakeEcr:
    def __init__(self, images, *, failures=(), describe_error=None):
        self.images, self.failures, self.describe_error = list(images), list(failures), describe_error
        self.describe_kw, self.deletes = None, []

    def get_paginator(self, name):
        assert name == "describe_images"
        return self

    def paginate(self, **kw):
        if self.describe_error:
            raise self.describe_error
        self.describe_kw = kw
        half = len(self.images) // 2          # 두 페이지로 나눠 준다 — 첫 페이지만 보는 구현을 잡는다
        return [{"imageDetails": self.images[:half]}, {"imageDetails": self.images[half:]}]

    def batch_delete_image(self, **kw):
        self.deletes.append(kw)
        failed = {f["imageId"]["imageDigest"] for f in self.failures}
        return {"imageIds": [i for i in kw["imageIds"] if i["imageDigest"] not in failed],
                "failures": [f for f in self.failures if f["imageId"] in kw["imageIds"]]}


def _result():
    import types
    return types.SimpleNamespace(agent_id="briefing_agent-abc")


def test_ecr_keep_latest_is_off_by_default():
    """설정이 없으면 아무것도 지우지 않는다 — 옛 이미지가 쌓인 계정에서 실수로 지우지 않게 opt-in."""
    from briefing.runtime.deploy_runtime import ecr_keep_latest_enabled

    assert ecr_keep_latest_enabled({}) is False and ecr_keep_latest_enabled({"BRIEFING_ECR_KEEP_LATEST": "0"}) is False
    assert all(ecr_keep_latest_enabled({"BRIEFING_ECR_KEEP_LATEST": v}) for v in ("1", "true", " ON "))


def test_images_to_delete_keeps_the_image_the_runtime_uses_not_the_newest_push():
    """남기는 기준 = 런타임이 쓰는 이미지. 배포가 실패하면 가장 최근 push(t3)는 안 쓰는 이미지다."""
    from briefing.runtime.deploy_runtime import images_to_delete

    images = [_img("a", "t1"), _img("b", "t2", "extra"), _img("c", "t3"), _img("d")]   # d = tag 없는 이미지
    assert images_to_delete(images, f"{_URI}:t2") == [
        {"imageDigest": "sha256:a"}, {"imageDigest": "sha256:c"}, {"imageDigest": "sha256:d"}]


def test_images_to_delete_is_empty_when_only_the_in_use_image_exists():
    from briefing.runtime.deploy_runtime import images_to_delete

    assert images_to_delete([_img("b", "t2")], f"{_URI}:t2") == []


def test_images_to_delete_returns_none_when_the_in_use_image_cannot_be_identified():
    """쓰는 이미지를 정확히 짚지 못하면 None — 호출자는 아무것도 지우지 않는다(빈 목록과 구분)."""
    from briefing.runtime.deploy_runtime import images_to_delete

    images = [_img("a", "t1"), _img("b", "t2")]
    assert images_to_delete(images, f"{_URI}:gone") is None          # 그 tag 가 저장소에 없다
    assert images_to_delete(images, f"{_URI}@sha256:b") is None      # digest 형식 URI 는 해석하지 않는다
    assert images_to_delete(images, _URI) is None                    # tag 가 없다
    assert images_to_delete(images, "") is None


def test_prune_does_nothing_when_disabled(capsys):
    """꺼져 있으면 조회도 삭제도 출력도 없다 — 이 가드가 옛 이미지가 쌓인 계정을 지킨다.
    (오류는 prune 안에서 삼켜지므로 '예외가 안 났다' 로는 못 잡는다 → fake 의 호출 기록으로 확인)"""
    from briefing.runtime.deploy_runtime import prune_old_images

    for env in ({}, {"BRIEFING_ECR_KEEP_LATEST": "0"}, {"BRIEFING_ECR_KEEP_LATEST": ""}):
        ecr = _FakeEcr([_img("a", "t1"), _img("b", "t2"), _img("c", "t3")])
        prune_old_images(_result(), "us-east-1", env, control=_FakeControl(), ecr=ecr)
        assert ecr.deletes == [] and ecr.describe_kw is None
    assert capsys.readouterr().out == ""


def test_prune_deletes_everything_but_the_in_use_image(capsys):
    from briefing.runtime.deploy_runtime import prune_old_images

    ecr = _FakeEcr([_img("a", "t1", size=10), _img("b", "t2", size=20), _img("c", "t3", size=30), _img("d", size=40)])
    prune_old_images(_result(), "us-east-1", {"BRIEFING_ECR_KEEP_LATEST": "1"}, control=_FakeControl(), ecr=ecr)

    assert ecr.describe_kw == {"repositoryName": _REPO, "registryId": _REG}
    assert [d["imageIds"] for d in ecr.deletes] == [
        [{"imageDigest": "sha256:a"}, {"imageDigest": "sha256:c"}, {"imageDigest": "sha256:d"}]]
    assert ecr.deletes[0]["repositoryName"] == _REPO and ecr.deletes[0]["registryId"] == _REG
    out = capsys.readouterr().out
    assert "삭제 3개" in out and "실패 0개" in out and "t2" in out


def test_prune_reports_failures_from_the_response_not_the_request(capsys):
    """batch_delete_image 는 이미지별 실패를 예외가 아니라 응답의 failures 로 준다 — 요청 건수를 성공으로 세면 안 된다."""
    from briefing.runtime.deploy_runtime import prune_old_images

    failure = {"imageId": {"imageDigest": "sha256:c"}, "failureCode": "ImageReferencedByManifestList",
               "failureReason": "referenced"}
    ecr = _FakeEcr([_img("a", "t1"), _img("b", "t2"), _img("c", "t3")], failures=[failure])
    prune_old_images(_result(), "us-east-1", {"BRIEFING_ECR_KEEP_LATEST": "1"}, control=_FakeControl(), ecr=ecr)

    out = capsys.readouterr().out
    assert "삭제 1개" in out and "실패 1개" in out and "ImageReferencedByManifestList" in out


def test_prune_batches_deletes_by_100():
    from briefing.runtime.deploy_runtime import prune_old_images

    ecr = _FakeEcr([_img("keep", "t2")] + [_img(f"x{i}", f"old{i}") for i in range(250)])
    prune_old_images(_result(), "us-east-1", {"BRIEFING_ECR_KEEP_LATEST": "1"}, control=_FakeControl(), ecr=ecr)

    assert [len(d["imageIds"]) for d in ecr.deletes] == [100, 100, 50]
    assert all(i["imageDigest"] != "sha256:keep" for d in ecr.deletes for i in d["imageIds"])


def test_prune_skips_when_the_endpoint_has_not_moved_to_the_new_version(capsys):
    """endpoint 가 아직 옛 버전을 쓰면 그 이미지를 지울 수 있다 → 건너뛴다(다음 배포 때 정리)."""
    from briefing.runtime.deploy_runtime import prune_old_images

    env = {"BRIEFING_ECR_KEEP_LATEST": "1"}
    for control in (_FakeControl(live="1"), _FakeControl(ep_status="UPDATING")):
        ecr = _FakeEcr([_img("a", "t1"), _img("b", "t2")])
        prune_old_images(_result(), "us-east-1", env, control=control, ecr=ecr)
        assert ecr.deletes == [] and ecr.describe_kw is None
    assert "건너뜀" in capsys.readouterr().out


def test_prune_skips_when_the_in_use_image_is_not_in_the_repository(capsys):
    from briefing.runtime.deploy_runtime import prune_old_images

    ecr = _FakeEcr([_img("a", "t1"), _img("c", "t3")])
    prune_old_images(_result(), "us-east-1", {"BRIEFING_ECR_KEEP_LATEST": "1"}, control=_FakeControl(), ecr=ecr)

    assert ecr.deletes == [] and "건너뜀" in capsys.readouterr().out


def test_prune_error_is_a_warning_not_a_failed_deploy(capsys):
    """정리는 배포가 끝난 뒤의 청소다 — 오류가 나도 배포 결과(exit 0)를 바꾸지 않는다."""
    from briefing.runtime.deploy_runtime import prune_old_images

    ecr = _FakeEcr([], describe_error=RuntimeError("AccessDenied"))
    prune_old_images(_result(), "us-east-1", {"BRIEFING_ECR_KEEP_LATEST": "1"}, control=_FakeControl(), ecr=ecr)

    out = capsys.readouterr().out
    assert ecr.deletes == [] and "정리 실패" in out and "AccessDenied" in out


# ───────────────────────── 구독 로그인 훅(harness_auth) — run 시작 복원 · 끝 되쓰기 ─────────────────────────

def test_finish_async_saves_login_then_releases_session(monkeypatch):
    import briefing.runtime.agentcore_runtime as rt

    order = []
    monkeypatch.setattr(rt.harness_auth, "save", lambda settings: order.append(("save", settings)))
    monkeypatch.setattr(rt.app, "complete_async_task", lambda task_id: order.append(("done", task_id)))
    rt._finish_async("S", 7)
    assert order == [("save", "S"), ("done", 7)]


def test_finish_async_releases_session_even_if_save_raises(monkeypatch):
    """되쓰기가 예외를 내도 busy 해제는 반드시 — 안 하면 세션이 최대 8시간 떠 있는다."""
    import pytest

    import briefing.runtime.agentcore_runtime as rt

    done = []

    def boom(settings):
        raise RuntimeError("ssm down")

    monkeypatch.setattr(rt.harness_auth, "save", boom)
    monkeypatch.setattr(rt.app, "complete_async_task", done.append)
    with pytest.raises(RuntimeError):
        rt._finish_async("S", 7)
    assert done == [7]


def test_every_non_smoke_path_restores_and_saves_subscription_login():
    """구조 불변식(소스 검사 — 위 trial·scheduled 테스트와 같은 이유): 한 경로라도 훅이 빠지면 그 모드는
    스위치를 켠 채 로그인 없이 돈다(카드 전부 실패) · 갱신된 codex 로그인 파일을 잃는다."""
    import pathlib
    import re

    import briefing.runtime.agentcore_runtime as rt

    src = pathlib.Path(rt.__file__).read_text(encoding="utf-8")
    cut = [src.index('mode == "scheduled"'), src.index('mode in ("weekly_build"'),
           src.index('mode == "trial"'), src.index('if mode == "smoke"')]
    for name, part in zip(("scheduled", "weekly", "trial"), (src[a:b] for a, b in zip(cut, cut[1:]))):
        assert "harness_auth.prepare(settings)" in part, f"{name}: 로그인 복원 누락"
        assert "_finish_async(settings, task_id)" in part, f"{name}: 되쓰기·busy 해제 누락"
        assert "app.complete_async_task" not in part, f"{name}: 되쓰기 없이 busy 만 해제"
    sync = src[cut[3]:]
    assert re.search(r'if mode != "smoke":[^\n]*\n\s+harness_auth\.prepare\(settings\)', sync), \
        "real·harness: 복원 누락(smoke 는 제외)"
    assert re.search(r"finally:\n\s+harness_auth\.save\(settings\)", sync), "real·harness: 되쓰기 누락"


# ───────────────────────── 컨테이너 자산 — 구독용 codex 설정 · Dockerfile COPY ─────────────────────────

def test_subscription_codex_config_uses_chatgpt_login_and_file_store(monkeypatch, tmp_path):
    """구독 변형: provider 를 적지 않고(= codex 기본 OpenAI · ChatGPT 로그인) 로그인은 파일로 — harness_auth 가 복원·되쓴다."""
    import shutil
    import tomllib

    from briefing.core.verification import certifier as cert
    from briefing.runtime import deploy_runtime as dr

    src = dr.PACKAGE_DIR / "runtime" / "container" / "codex_config_subscription.toml"
    cfg = tomllib.loads(src.read_text(encoding="utf-8"))
    assert "model_provider" not in cfg and "model_providers" not in cfg
    assert (cfg["model"], cfg["model_reasoning_effort"], cfg["cli_auth_credentials_store"]) == (
        "gpt-6-luna", "medium", "file")
    shutil.copy(src, tmp_path / "config.toml")
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    assert cert.codex_model_id() == "gpt-6-luna"             # 운영 함수가 이 파일에서 모델 이름을 읽는다


def test_dockerfile_copies_only_staged_assets():
    """Dockerfile 이 COPY 로 집는 파일은 전부 빌드 컨텍스트에 실려야 한다 — 빠지면 배포 중 docker build 에서야 드러난다."""
    import re

    from briefing.runtime import deploy_runtime as dr

    container = dr.PACKAGE_DIR / "runtime" / "container"
    dockerfile = (container / "Dockerfile").read_text(encoding="utf-8")
    copied = [m.group(1) for m in re.finditer(r"^COPY\s+(\S+)\s+\S+\s*$", dockerfile, re.M) if m.group(1) != "."]
    assert "codex_config_subscription.toml" in copied and "codex_config.toml" in copied
    missing = [f for f in copied if f not in dr.CONTAINER_ASSETS or not (container / f).exists()]
    assert not missing, f"빌드 컨텍스트에 없는 COPY 원본: {missing}"
    assert "Dockerfile" in dr.CONTAINER_ASSETS


# ───────────────────────── 호출 경로 스위치 → 컨테이너 env · IAM(SSM) ─────────────────────────

_SWITCH_KEYS = ("AUTHOR_PROVIDER", "CERTIFIER_PROVIDER", "JUDGE_PROVIDER", "CODEX_HOME")
_ACCOUNT = "123456789012"
_SSM = f"arn:aws:ssm:us-east-1:{_ACCOUNT}:parameter"


def _ssm_statements(policy: dict) -> dict:
    return {st["Sid"]: st for st in policy["Statement"] if st["Sid"].startswith("Ssm")}


def test_default_providers_change_nothing_in_env_or_policy(tmp_path):
    """둘 다 bedrock = 컨테이너 env 에 새 키 0 · 정책 문장 종전 5개 그대로(스위치를 모르는 배포는 영향 0)."""
    from briefing.runtime.deploy_runtime import runtime_env, runtime_extras_policy

    s = _settings(tmp_path)
    env = runtime_env(s)
    assert env["CLAUDE_CODE_USE_BEDROCK"] == "1" and not [k for k in _SWITCH_KEYS if k in env]
    assert runtime_extras_policy(_ACCOUNT, s) == runtime_extras_policy(_ACCOUNT)
    assert [st["Sid"] for st in runtime_extras_policy(_ACCOUNT)["Statement"]] == [
        "BedrockInvokeAuthor", "BedrockMantleCertifier", "BedrockListProfilesWeeklyGate", "SesTrialAndSend",
        "DynamoStores"]


def test_author_subscription_drops_bedrock_flag_and_reads_only_the_claude_token(tmp_path):
    from briefing.runtime.deploy_runtime import runtime_env, runtime_extras_policy
    from briefing.runtime.harness_auth import PARAM_CLAUDE_TOKEN

    s = _settings(tmp_path, author_provider="subscription")
    env = runtime_env(s)
    assert "CLAUDE_CODE_USE_BEDROCK" not in env and env["AUTHOR_PROVIDER"] == "subscription"
    assert "CERTIFIER_PROVIDER" not in env and "CODEX_HOME" not in env
    ssm = _ssm_statements(runtime_extras_policy(_ACCOUNT, s))
    assert list(ssm) == ["SsmHarnessLoginRead"]                       # 쓰기 권한 없음 — Claude 토큰은 갱신되지 않는다
    assert (ssm["SsmHarnessLoginRead"]["Action"], ssm["SsmHarnessLoginRead"]["Resource"]) == (
        ["ssm:GetParameter"], [_SSM + PARAM_CLAUDE_TOKEN])


def test_certifier_subscription_points_codex_home_and_allows_write_back(tmp_path):
    from briefing.runtime import deploy_runtime as dr
    from briefing.runtime.harness_auth import PARAM_CODEX_AUTH

    s = _settings(tmp_path, certifier_provider="subscription")
    env = dr.runtime_env(s)
    assert env["CLAUDE_CODE_USE_BEDROCK"] == "1" and "AUTHOR_PROVIDER" not in env   # 요약은 그대로 Bedrock
    assert (env["CERTIFIER_PROVIDER"], env["CODEX_HOME"]) == ("subscription", dr.CONTAINER_CODEX_SUBSCRIPTION_HOME)
    dockerfile = (dr.PACKAGE_DIR / "runtime" / "container" / "Dockerfile").read_text(encoding="utf-8")
    assert f"COPY codex_config_subscription.toml {env['CODEX_HOME']}/config.toml" in dockerfile   # env ↔ 이미지 경로 일치
    ssm = _ssm_statements(dr.runtime_extras_policy(_ACCOUNT, s))
    assert ssm["SsmHarnessLoginRead"]["Resource"] == [_SSM + PARAM_CODEX_AUTH]
    assert (ssm["SsmHarnessLoginWriteBack"]["Action"], ssm["SsmHarnessLoginWriteBack"]["Resource"]) == (
        ["ssm:PutParameter"], [_SSM + PARAM_CODEX_AUTH])


def test_both_subscription_reads_both_parameters_writes_only_codex(tmp_path):
    from briefing.runtime.deploy_runtime import runtime_extras_policy
    from briefing.runtime.harness_auth import PARAM_CLAUDE_TOKEN, PARAM_CODEX_AUTH

    s = _settings(tmp_path, author_provider="subscription", certifier_provider="subscription")
    ssm = _ssm_statements(runtime_extras_policy(_ACCOUNT, s))
    assert ssm["SsmHarnessLoginRead"]["Resource"] == [_SSM + PARAM_CLAUDE_TOKEN, _SSM + PARAM_CODEX_AUTH]
    assert ssm["SsmHarnessLoginWriteBack"]["Resource"] == [_SSM + PARAM_CODEX_AUTH]


def test_judge_subscription_forwards_switch_and_reads_only_the_claude_token(tmp_path):
    """보조 판정만 구독: 스위치를 컨테이너로 넘기고(안 넘기면 컨테이너는 조용히 Bedrock), 요약용 Bedrock 플래그는 그대로."""
    from briefing.runtime.deploy_runtime import runtime_env, runtime_extras_policy
    from briefing.runtime.harness_auth import PARAM_CLAUDE_TOKEN

    s = _settings(tmp_path, judge_provider="subscription")
    env = runtime_env(s)
    assert env["JUDGE_PROVIDER"] == "subscription" and env["CLAUDE_CODE_USE_BEDROCK"] == "1"
    assert not [k for k in ("AUTHOR_PROVIDER", "CERTIFIER_PROVIDER", "CODEX_HOME") if k in env]
    ssm = _ssm_statements(runtime_extras_policy(_ACCOUNT, s))
    assert list(ssm) == ["SsmHarnessLoginRead"]
    assert ssm["SsmHarnessLoginRead"]["Resource"] == [_SSM + PARAM_CLAUDE_TOKEN]
