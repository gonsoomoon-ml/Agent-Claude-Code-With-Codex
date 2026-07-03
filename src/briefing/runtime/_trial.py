"""_trial — 체험하기 코어(DI). entrypoint(mode=trial)가 실 ses/run_briefing/sleep 을 배선.

검증(Success)까지 polling → 그 후에만 run_briefing → published>0 발송 / ==0 폴백.
부수효과는 전부 인자(주입) — fake 로 결정론 단위테스트.
"""
from __future__ import annotations

import re
from typing import Any, Callable

from ..core.config import Settings, UserConfig


def _slug(email: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", email.lower()).strip("-")[:40] or "anon"


def build_trial_user(payload: dict, settings: Settings) -> UserConfig:
    """체험 사용자 설정 구성(9필드). payload['email']·source·lens·depth·timezone·type 취합.

    Args:
        payload: {'email', 'sources', 'lens', 'depth', 'timezone', 'type'} (일부 선택)
        settings: ses_sender 등 시스템 설정

    Returns:
        UserConfig(id=trial-<slug>, send_hour=0, timezone=Asia/Seoul, depth=summary,
                   lens=general, skill_md="", type=ai-news)
    """
    email = payload["email"]
    return UserConfig(
        id=f"trial-{_slug(email)}", recipient=email, type=payload.get("type", "ai-news"),
        sources=tuple(payload.get("sources") or ()), depth=payload.get("depth", "summary"),
        lens=payload.get("lens", "general"), send_hour=0,
        timezone=payload.get("timezone", "Asia/Seoul"), skill_md="",
    )


def poll_verified(ses: Any, email: str, *, attempts: int, sleep_seconds: int,
                  sleep_fn: Callable[[int], None]) -> bool:
    """get_identity_verification_attributes 를 attempts 회 polling — Success 면 True.

    마지막 시도 후엔 sleep_fn 호출 금지 (테스트에서 instant 검증 허용).

    Args:
        ses: boto3 SES client (또는 fake)
        email: 검증 대상 주소
        attempts: 최대 폴링 회수
        sleep_seconds: 각 대기 간격(주입)
        sleep_fn: 대기 함수(주입) — 테스트는 no-op 설정

    Returns:
        True if Success, False on timeout
    """
    for i in range(attempts):
        attrs = ses.get_identity_verification_attributes(Identities=[email])
        st = attrs.get("VerificationAttributes", {}).get(email, {}).get("VerificationStatus")
        if st == "Success":
            return True
        if i < attempts - 1:
            sleep_fn(sleep_seconds)
    return False


def run_trial(settings: Settings, store: Any, card_cache: Any, payload: dict, *,
              ses: Any, run_briefing_fn: Callable, deliver_fn: Callable[[Any], None],
              fallback_fn: Callable[[str], None], sleep_fn: Callable[[int], None],
              run_date: str, attempts: int = 45, sleep_seconds: int = 20,
              status_fn: Callable[[str, int | None], None] = lambda s, p=None: None) -> str:
    """검증 polling → run_briefing → 발송/폴백. 상태 문자열 반환(로깅용).

    미검증(timeout) 시 run_briefing 호출 금지 (LLM 비용 0).
    published>0 → deliver_fn; ==0 또는 empty → fallback_fn.
    각 단계마다 status_fn 콜백 호출(DI, 테스트용 상태 추적).

    Args:
        settings, store, card_cache: 블리핑 런타임
        payload: {'email', 'sources', ...}
        ses: SES client (또는 fake)
        run_briefing_fn: callable(settings, store, users, card_cache, ledger, run_date)
        deliver_fn, fallback_fn: 부수효과(주입)
        sleep_fn: 대기 함수(주입)
        run_date: ISO 날짜 문자열
        attempts, sleep_seconds: 폴링 설정
        status_fn: 상태 콜백(주입) — status_fn(단계, published_count) 또는 status_fn(단계)

    Returns:
        상태 로그(str) — "trial timeout(...)", "trial empty(...)", "trial delivered(...)", "trial fallback(...)"
    """
    email = payload["email"]
    if not poll_verified(ses, email, attempts=attempts, sleep_seconds=sleep_seconds, sleep_fn=sleep_fn):
        status_fn("expired")
        return f"trial timeout(unverified): {email}"
    status_fn("generating")
    user = build_trial_user(payload, settings)
    briefs = run_briefing_fn(settings, store, [user], card_cache=card_cache, ledger=None, run_date=run_date)
    if not briefs:
        fallback_fn(email)
        status_fn("fallback")
        return f"trial empty: {email}"
    b = briefs[0]
    if b.published > 0:
        deliver_fn(b)
        status_fn("sent", b.published)
        return f"trial delivered({b.published}): {email}"
    fallback_fn(email)
    status_fn("fallback")
    return f"trial fallback(published=0): {email}"
