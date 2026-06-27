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
    source_store_path: str # content-addressed source-of-record(공유)
    users_dir: str         # per-user 설정 디렉토리


def load_settings() -> Settings:
    g = os.getenv
    author_model_id = g("AUTHOR_MODEL_ID", "global.anthropic.claude-sonnet-4-6")
    return Settings(
        region=g("AWS_REGION", "us-east-1"),
        author_model_id=author_model_id,
        supervisor_model_id=g("SUPERVISOR_MODEL_ID", author_model_id),  # 미설정 시 author 모델 재사용
        ses_sender=g("SES_SENDER", ""),
        source_store_path=g("SOURCE_STORE_PATH", "./.data/source_store"),
        users_dir=g("USERS_DIR", "./users"),
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
    """users_dir 아래 profile.yaml 을 가진 디렉토리 = 사용자 목록."""
    root = Path(settings.users_dir)
    if not root.exists():
        return []
    return sorted(p.name for p in root.iterdir() if (p / "profile.yaml").exists())


def load_user(user_id: str, settings: Settings) -> UserConfig:
    """users/<id>/profile.yaml(운영) + skill.md(편집 개인화) → UserConfig."""
    if yaml is None:  # pragma: no cover
        raise RuntimeError("pyyaml 필요 — `uv sync`")
    d = Path(settings.users_dir) / user_id
    prof = yaml.safe_load((d / "profile.yaml").read_text(encoding="utf-8")) or {}
    skill_path = d / "skill.md"
    # TODO(검증 — write 계층=웹 UI/API): recipient(이메일)·depth(enum)·sources(∈CATALOG)·send_hour 검증.
    #   외부 입력 user_id 는 path-traversal 검증 필수(지금은 list_users 내부값이라 안전).
    return UserConfig(
        id=prof.get("id", user_id),
        recipient=prof.get("recipient", ""),
        type=prof.get("type", "ai-news"),
        sources=tuple(prof.get("sources") or ()),  # 빈 값 = 전체 (resolve_sources 가 처리)
        depth=prof.get("depth", "full"),
        lens=prof.get("lens", "general"),
        send_hour=int(prof.get("send_hour", 7)),
        timezone=prof.get("timezone", "Asia/Seoul"),
        skill_md=skill_path.read_text(encoding="utf-8") if skill_path.exists() else "",
    )
