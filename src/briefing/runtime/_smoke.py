"""smoke — 결정론 fake DI fns + 합성 사용자. **②a 배포 plumbing 검증 전용**(claude/codex/네트워크 0).

★ 왜 존재하나: 실 AgentCore 에 1회 invoke 해서 *컨테이너 빌드·IAM execution role·invoke→SSE·teardown* 을
  **결정론으로** 증명하기 위함. LLM/CLI/네트워크 경계(fetch·draft·verify)만 fake 로 대체하고,
  `run_briefing` 의 오케스트레이션(curate→per-user gate→render)은 **실제 코드 그대로** 탄다.
  → 실패하면 원인이 "plumbing" 으로 국소화된다(진짜 파이프라인·CLI 번들과 무관).

② 단계 분리: ②a = 이 fake 로 plumbing green. ②b = `claude`+`codex` 를 이미지에 번들 → mode 분기 없이
  진짜 검증 후 발행(verify-before-publish). 그때 이 모듈은 빠진다(테스트/로컬 DI fake 와 동일 역할).

entrypoint 가 payload `{"mode":"smoke"}` 일 때 `smoke_fns()`/`smoke_users()` 를 `run_briefing` 에 주입.
"""
from __future__ import annotations

from ..shared import sources as src
from ..shared.author import Claim, DraftCard
from ..shared.certifier import CertVerdict
from ..shared.config import Settings, UserConfig, list_users, load_user
from ..shared.source_store import FrozenSource
from ..shared.sources import FetchedArticle, Source


def smoke_fetch_fn(source: Source, window_hours: int) -> list[FetchedArticle]:
    """fake 권위 페치 — 네트워크 0. 어떤 source 든 합성 기사 1건(curate→freeze 경로 실행)."""
    return [
        FetchedArticle(
            source_key=source.key,
            url=f"https://smoke.invalid/{source.key}",
            title=f"(smoke) {source.name}",
            raw_text="smoke 모드 합성 본문 — 네트워크·LLM 미사용. 배포 plumbing 검증용.",
            published_at="2026-06-27T00:00:00Z",
        )
    ]


def smoke_draft_fn(source: FrozenSource, user: UserConfig, settings: Settings) -> DraftCard:
    """fake author — `claude -p` 미호출. 동결본 1건 → 결정론 카드(claims 1개, core)."""
    return DraftCard(
        source_id=source.source_id,
        headline="(smoke) 배포 검증 카드",
        summary="이 카드는 smoke 모드의 결정론 산출물이다(LLM 미호출).",
        why_it_matters="배포 plumbing(컨테이너·IAM·invoke→SSE)이 살아있음을 증명한다.",
        claims=(
            Claim(id="C1", text="smoke 모드는 결정론으로 동작한다.",
                  claim_type="entailment", importance="core"),
        ),
    )


def smoke_revise_fn(
    source: FrozenSource, user: UserConfig, settings: Settings,
    *, prior: DraftCard, failed_ids: tuple[str, ...],
) -> DraftCard:
    """fake 재도출 — smoke 는 항상 전부 VERIFIED 라 호출되지 않지만 시그니처 충족용."""
    return prior


def smoke_verify_fn(card: DraftCard) -> tuple[CertVerdict, ...]:
    """fake certifier — `codex exec` 미호출. 모든 claim 을 결정론 VERIFIED 처리 → PUBLISH."""
    return tuple(
        CertVerdict(c.id, "VERIFIED", "smoke: 결정론 검증(항상 통과)", "smoke")
        for c in card.claims
    )


def smoke_fns() -> dict:
    """run_briefing 에 주입할 DI seam 4종(fetch/draft/revise/verify) — 전부 fake."""
    return {
        "fetch_article_fn": smoke_fetch_fn,
        "draft_fn": smoke_draft_fn,
        "revise_fn": smoke_revise_fn,
        "verify_fn": smoke_verify_fn,
    }


def harness_fns() -> dict:
    """②b harness 모드 — **fetch 만 fake, draft/verify 는 진짜 `claude -p`·`codex exec`**.

    smoke(전부 fake)와 real(아무것도 fake 안 함) 사이의 *격리 검증*: 네트워크/RSS/fragile/프로필을 빼고
    "컨테이너에서 claude·codex 가 실제로 실행되는가" 만 본다. draft/revise/verify 키를 *안* 넣으므로
    gate 가 기본값(실제 하니스)으로 배선된다(합성 source 1건 → 진짜 author→certify).
    """
    return {"fetch_article_fn": smoke_fetch_fn}


def smoke_users(settings: Settings) -> list[UserConfig]:
    """실 사용자(users/<id>/)가 있으면 그대로, 없으면 *합성 사용자 1명* — 컨테이너에 users/ 가
    안 복사돼도 smoke invoke 가 per-user SSE 를 내도록 self-contained 보장.
    """
    ids = list_users(settings)
    if ids:
        return [load_user(uid, settings) for uid in ids]
    key = src.CATALOG[0].key if src.CATALOG else ""
    return [
        UserConfig(
            id="smoke",
            recipient="smoke@example.com",
            type="ai-news",
            sources=(key,) if key else (),  # 단일 출처(결정론 1카드); 빈 값이면 전체
            depth="full",
            lens="general",
            send_hour=7,
            timezone="Asia/Seoul",
            skill_md="",
        )
    ]
