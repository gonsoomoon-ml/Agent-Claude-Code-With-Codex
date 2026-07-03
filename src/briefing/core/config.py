"""설정 로더 — 배포 전역 설정(Settings)과 사용자별 설정(UserConfig)을 읽는다.

- `Settings`   = 배포 전역값(`.env` 에서): region · author 모델 · SES 발신자 · store backend · users 디렉토리 · Gateway 값들.
- `UserConfig` = 사용자별값(`users/<id>/`): 운영 설정(profile.yaml) + 편집 개인화(skill.md).
  ★ `skill.md` 는 *편집 취향*만 담는다 — 검증 규칙은 base(prompts/author_system.md)가 소유하고, **certifier 는 이 파일을 읽지 않는다**(신뢰 경계).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# dotenv 와 yaml 은 없어도 죽지 않게 선택 의존성처럼 다룬다(단, load_user 의 파일 경로는 yaml 이 필요).
try:
    from dotenv import load_dotenv

    load_dotenv(override=True)  # 루트 .env 의 값이 기존 OS 환경변수를 덮어쓴다(override=True)
except ModuleNotFoundError:  # pragma: no cover
    pass

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover
    yaml = None


@dataclass(frozen=True)
class Settings:
    region: str
    author_model_id: str       # author(claude -p)에게 ANTHROPIC_MODEL 로 넘기는 모델 id
    supervisor_model_id: str   # Strands supervisor 오케스트레이터 모델(미설정 시 author 와 동일) — 역할별로 다르게 라우팅 가능
    # certifier 모델은 codex 쪽(~/.codex/config.toml)이 소유한다 — 여기서 설정하지 않고 provenance 만 기록.
    ses_sender: str            # 공유 발신 주소(수신자는 사용자별)
    backend: str           # "local"(기본) | "dynamo" — source/cache/ledger 세 store 를 한꺼번에 고른다
    source_store_path: str # local backend 용 — 정본 원문 저장 경로(content-addressed)
    cache_path: str        # local backend 용 — 결과 카드 캐시 경로(같은 입력 재계산 방지)
    ledger_path: str       # local backend 용 — 발행 기록(시간·사용자별) JSONL 경로
    cache_table: str       # dynamo backend 용 — card-cache 테이블명(CFN infra/ddb.yaml)
    ledger_table: str      # dynamo backend 용 — ledger 테이블명(시간·사용자별 발행 기록)
    source_table: str      # dynamo backend 용 — source-store 테이블명(정본 원문, content-addressed)
    users_table: str       # dynamo backend 용 — users 테이블명(사용자별 프로필; ④ 쓰기 ↔ load_user 읽기 seam)
    ddb_endpoint_url: str  # 빈값이면 실제 AWS(기본), 값을 주면 DynamoDB Local(무료 에뮬레이터)로 붙는다
    users_dir: str         # 사용자별 설정이 담긴 디렉토리(users/<id>/)
    # ── Gateway(① 승격) — 기본 off 라 켜기 전엔 영향 없음(additive). 인증은 Cognito CUSTOM_JWT(aiops 패턴) ──
    gateway_enabled: bool       # 켜면 fabric 이 retrieval 을 Gateway(MCP) 경유로 호출(기본은 직접 호출)
    gateway_url: str            # Gateway MCP 엔드포인트(.../mcp) — deploy_gateway 가 출력
    gateway_target: str         # MCP 도구 이름 앞 prefix(target 이름) → "TARGET___fetch_article"
    cognito_scope: str          # resource server scope(예: "briefing-gw/invoke")
    cognito_token_url: str      # Cognito OAuth2 토큰 엔드포인트 — *로컬*에서 직접 토큰 받을 때만 사용
    cognito_client_id: str      # M2M 앱 클라이언트 id
    cognito_client_secret: str  # ★ 비밀 — .env/로컬 전용(Runtime 은 Identity 사용; gitignore 확인됨)
    oauth_provider_name: str    # AgentCore Identity 자격증명 provider — *Runtime* 이 비밀 없이 토큰 받는 경로


def load_settings() -> Settings:
    g = os.getenv
    author_model_id = g("AUTHOR_MODEL_ID", "global.anthropic.claude-sonnet-4-6")
    return Settings(
        region=g("AWS_REGION", "us-east-1"),
        author_model_id=author_model_id,
        supervisor_model_id=g("SUPERVISOR_MODEL_ID", author_model_id),  # 따로 설정 안 하면 author 모델을 그대로 쓴다
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
    recipient: str            # 받는 이메일 주소(SES sandbox 에서는 미리 verify 필요)
    type: str                 # 브리핑 종류(버티컬): ai-news / stock-news ...
    sources: tuple[str, ...]  # 고른 출처 키들(sources.CATALOG 의 key); 빈 튜플이면 전체
    depth: str                # 깊이: title-only / summary / full
    lens: str                 # 요약 관점(렌즈) — lenses.LENS_LIBRARY 의 key, 기본 general
    send_hour: int
    timezone: str
    skill_md: str     # users/<id>/skill.md 내용(편집 개인화) — ★ certifier 는 읽지 않는다(신뢰 경계)


def list_users(settings: Settings) -> list[str]:
    """사용자 목록을 돌려준다. BACKEND=dynamo 면 briefing-users 를 Scan, 아니면 users_dir 에서 profile.yaml 을 가진 디렉토리들."""
    if settings.backend == "dynamo":
        from .stores.dynamo import user_store_from_settings  # 필요할 때만 import — config↔stores 순환을 피한다
        return user_store_from_settings(settings).list_users()
    root = Path(settings.users_dir)
    if not root.exists():
        return []
    return sorted(p.name for p in root.iterdir() if (p / "profile.yaml").exists())


def _read_skill_md(settings: Settings, user_id: str) -> str:
    """skill_md 를 읽는다 — 언제나 `users/<id>/skill.md` 파일에서(파일 오버레이). ★ web/DDB 에는 *없다*(신뢰 경계 — certifier 미열람).

    파일이 없는 공개 유저는 ""(빈 문자열) → 편집 개인화는 lens 가 대신한다. 즉 사용자가 web 으로 skill_md 를 쓸 경로가 *구조적으로* 없다.
    """
    p = Path(settings.users_dir) / user_id / "skill.md"
    return p.read_text(encoding="utf-8") if p.exists() else ""


def _user_from_fields(user_id: str, f: dict, skill_md: str) -> UserConfig:
    """운영 7필드 dict(profile.yaml 또는 DDB 항목) + skill_md(파일)를 합쳐 UserConfig 를 만든다. 두 backend 가 공유하는 빌더."""
    return UserConfig(
        id=f.get("id", user_id),
        recipient=f.get("recipient", ""),
        type=f.get("type", "ai-news"),
        sources=tuple(f.get("sources") or ()),  # 비어 있으면 전체 출처(resolve_sources 가 알아서 처리)
        depth=f.get("depth", "full"),
        lens=f.get("lens", "general"),
        send_hour=int(f.get("send_hour", 7)),
        timezone=f.get("timezone", "Asia/Seoul"),
        skill_md=skill_md,
    )


def load_user(user_id: str, settings: Settings) -> UserConfig:
    """사용자 프로필을 읽어 UserConfig 로 만든다. 운영 7필드는 backend 에 따라(파일 profile.yaml | DDB), **skill_md 는 언제나 파일에서**.

    ★ skill_md 는 web 에서 쓸 수 있는 저장소(DDB)에 *없다* — 파일 오버레이만 쓴다(신뢰 경계; ④ 구독은 운영 7필드만 쓴다).
    """
    skill_md = _read_skill_md(settings, user_id)
    if settings.backend == "dynamo":
        from .stores.dynamo import user_store_from_settings  # 필요할 때만 import(순환 회피)
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
