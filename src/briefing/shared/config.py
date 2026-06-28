"""설정 로더.

- `Settings`   = 배포-전역(.env): region · author model · SES sender · store · users_dir.
- `UserConfig` = per-user(users/<id>/): 운영(profile.yaml) + 편집 개인화(skill.md).
  ★ `skill.md` 는 *편집 취향*만 — 검증 규칙은 base(prompts/author_system.md) 소유, **certifier 미열람**.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# dotenv·yaml 은 선택 의존성처럼 다룬다(미설치 시 graceful) — 단 load_user 는 yaml 필요.
try:
    from dotenv import load_dotenv

    load_dotenv(override=True)  # 루트 .env 가 기존 OS env 를 덮어씀
except ModuleNotFoundError:  # pragma: no cover
    pass

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover
    yaml = None


@dataclass(frozen=True)
class Settings:
    region: str
    author_model_id: str       # author=`claude -p` 에 ANTHROPIC_MODEL 로 전달
    supervisor_model_id: str   # Strands supervisor 오케스트레이터 모델(기본=author) — per-role 라우팅
    # certifier 모델은 codex 가 소유(~/.codex/config.toml) — 우리는 설정하지 않음(provenance 만 기록).
    ses_sender: str            # 공유 발신 신원(수신자는 per-user)
    backend: str           # "local"(기본) | "dynamo" — 세 store(source/cache/ledger) 일관 선택
    source_store_path: str # local backend: content-addressed source-of-record(공유)
    cache_path: str        # local backend: 결과 캐시 루트(③ 재실행 방지)
    ledger_path: str       # local backend: run history(시간·사용자) JSONL 루트
    cache_table: str       # dynamo backend: card-cache 테이블명(CFN infra/ddb.yaml)
    ledger_table: str      # dynamo backend: ledger 테이블명(시간·사용자 history)
    source_table: str      # dynamo backend: source-store 테이블명(content-addressed source-of-record)
    users_table: str       # dynamo backend: users 테이블명(per-user 프로필; ④ 쓰기 ↔ load_user 읽기 seam)
    ddb_endpoint_url: str  # 빈값=실 AWS(기본); 값 주면 DynamoDB Local(무료 에뮬레이터)
    users_dir: str         # per-user 설정 디렉토리
    # ── Gateway (① 승격; 기본 off → additive). 인증 = Cognito CUSTOM_JWT (aiops 패턴) ──
    gateway_enabled: bool       # truthy → fabric 이 retrieval 을 Gateway MCP 로 호출(기본=직접)
    gateway_url: str            # Gateway MCP 엔드포인트(.../mcp) — deploy_gateway 출력
    gateway_target: str         # MCP 도구 prefix(target 이름) → "TARGET___fetch_article"
    cognito_scope: str          # resource server scope (예 "briefing-gw/invoke")
    cognito_token_url: str      # Cognito OAuth2 token endpoint — *로컬* 직접 발급용
    cognito_client_id: str      # M2M app client id
    cognito_client_secret: str  # ★ 비밀 — .env/로컬 전용 (Runtime 은 Identity; gitignore 확인됨)
    oauth_provider_name: str    # AgentCore Identity credential provider — *Runtime* 토큰(비밀 없이)


def load_settings() -> Settings:
    g = os.getenv
    author_model_id = g("AUTHOR_MODEL_ID", "global.anthropic.claude-sonnet-4-6")
    return Settings(
        region=g("AWS_REGION", "us-east-1"),
        author_model_id=author_model_id,
        supervisor_model_id=g("SUPERVISOR_MODEL_ID", author_model_id),  # 미설정 시 author 모델 재사용
        ses_sender=g("SES_SENDER", ""),
        backend=g("BACKEND", "local"),
        source_store_path=g("SOURCE_STORE_PATH", "./.data/source_store"),
        cache_path=g("CACHE_PATH", "./.data/card_cache"),
        ledger_path=g("LEDGER_PATH", "./.data/ledger"),
        cache_table=g("CACHE_TABLE", "briefing-card-cache"),
        ledger_table=g("LEDGER_TABLE", "briefing-ledger"),
        source_table=g("SOURCE_TABLE", "briefing-source-store"),
        users_table=g("USERS_TABLE", "briefing-users"),
        ddb_endpoint_url=g("DDB_ENDPOINT_URL", ""),
        users_dir=g("USERS_DIR", "./users"),
        gateway_enabled=g("GATEWAY_ENABLED", "").strip().lower() in ("1", "true", "yes", "on"),
        gateway_url=g("GATEWAY_URL", ""),
        gateway_target=g("GATEWAY_TARGET", "briefing"),
        cognito_scope=g("COGNITO_SCOPE", ""),
        cognito_token_url=g("COGNITO_TOKEN_URL", ""),
        cognito_client_id=g("COGNITO_CLIENT_ID", ""),
        cognito_client_secret=g("COGNITO_CLIENT_SECRET", ""),
        oauth_provider_name=g("OAUTH_PROVIDER_NAME", ""),
    )


@dataclass(frozen=True)
class UserConfig:
    id: str
    recipient: str            # 수신 이메일 (SES sandbox: 사전 verify)
    type: str                 # TYPE: ai-news / stock-news ...
    sources: tuple[str, ...]  # 선택한 출처 키 (sources.CATALOG); 빈 튜플 = 전체
    depth: str                # DEPTH: title-only / summary / full
    lens: str                 # LENS: 요약 관점 (lenses.LENS_LIBRARY 키; 기본 general)
    send_hour: int
    timezone: str
    skill_md: str     # users/<id>/skill.md 내용 (편집 개인화; ★ certifier 미열람)


def list_users(settings: Settings) -> list[str]:
    """사용자 목록. BACKEND=dynamo → briefing-users Scan, 아니면 users_dir 의 profile.yaml 디렉토리."""
    if settings.backend == "dynamo":
        from .stores.dynamo import user_store_from_settings  # lazy — config↔stores 순환 회피
        return user_store_from_settings(settings).list_users()
    root = Path(settings.users_dir)
    if not root.exists():
        return []
    return sorted(p.name for p in root.iterdir() if (p / "profile.yaml").exists())


def _read_skill_md(settings: Settings, user_id: str) -> str:
    """skill_md = users/<id>/skill.md 파일 오버레이(양 backend 공통). ★ web/DDB 에 *없음* — trust 경계(certifier 미열람).

    공개 유저(파일 없음)는 "" → lens 가 편집 개인화 담당. user-write 경로가 *구성상* 존재하지 않음.
    """
    p = Path(settings.users_dir) / user_id / "skill.md"
    return p.read_text(encoding="utf-8") if p.exists() else ""


def _user_from_fields(user_id: str, f: dict, skill_md: str) -> UserConfig:
    """7 운영 필드 dict(profile.yaml 또는 DDB 항목) + skill_md(파일) → UserConfig. 양 backend 공통 빌더."""
    return UserConfig(
        id=f.get("id", user_id),
        recipient=f.get("recipient", ""),
        type=f.get("type", "ai-news"),
        sources=tuple(f.get("sources") or ()),  # 빈 값 = 전체 (resolve_sources 가 처리)
        depth=f.get("depth", "full"),
        lens=f.get("lens", "general"),
        send_hour=int(f.get("send_hour", 7)),
        timezone=f.get("timezone", "Asia/Seoul"),
        skill_md=skill_md,
    )


def load_user(user_id: str, settings: Settings) -> UserConfig:
    """per-user 프로필 → UserConfig. 7 운영 필드는 backend(파일 profile.yaml | DDB), **skill_md 는 항상 파일**.

    ★ skill_md 는 web-writable 저장소(DDB)에 *없다* — 파일 오버레이만(trust 경계; ④ 구독은 7필드만 씀).
    """
    skill_md = _read_skill_md(settings, user_id)
    if settings.backend == "dynamo":
        from .stores.dynamo import user_store_from_settings  # lazy — 순환 회피
        rec = user_store_from_settings(settings).get_user(user_id)
        if rec is None:
            raise KeyError(f"DDB 에 사용자 없음: {user_id}")
        return _user_from_fields(user_id, rec, skill_md)
    if yaml is None:  # pragma: no cover
        raise RuntimeError("pyyaml 필요 — `uv sync`")
    # TODO(검증 — write 계층=웹 UI/API): recipient(이메일)·depth(enum)·sources(∈CATALOG)·send_hour 검증.
    #   외부 입력 user_id 는 path-traversal 검증 필수(지금은 list_users 내부값이라 안전).
    prof = yaml.safe_load((Path(settings.users_dir) / user_id / "profile.yaml").read_text(encoding="utf-8")) or {}
    return _user_from_fields(user_id, prof, skill_md)
