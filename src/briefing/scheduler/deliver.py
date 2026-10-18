"""deliver — C5 DeliverFn. 기본 = SES SendEmail. **카드가 하나라도 있을 때만** 발송(빈 브리핑은 미발송).

DeliverFn = Callable[[UserBriefing], dict | None] — briefing 만 받는다. settings/client 는 클로저로 캡처
(`make_ses_deliver`). SES 응답 dict(발송 시) 또는 None(미발송) 반환. 테스트는 fake client 주입 → 실 SES 무접촉.
★ 격리(QUARANTINE) 카드도 ⚠ 표시로 싣는다(N5, 2026-10-18 사용자 결정 — 비중요 브리핑). 빈 브리핑만 발송 안 함.
★ SES sandbox: 수신자 사전 verify · @gmail 발신은 DMARC 거부 → 커스텀 도메인 발신(settings.ses_sender).
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

DeliverFn = Callable[[Any], dict | None]   # Callable[[UserBriefing], dict | None] — 덕타이핑(.recipient·.email·.published), SES 응답 또는 None 반환


def should_deliver(briefing: Any) -> bool:
    """발송 조건 = 메일에 실린 카드(검증 + ⚠ 격리) 1장 이상. 빈 브리핑만 미발송."""
    return _card_count(briefing) > 0


def _card_count(briefing: Any) -> int:
    """메일에 실린 카드 수 — 검증 카드 + 격리 카드(⚠). quarantined 가 없는 덕타입(옛 fake)은 0 으로 본다."""
    return briefing.published + getattr(briefing, "quarantined", 0)


def make_ses_deliver(settings: Any, *, client: Any = None, subject: str | None = None) -> DeliverFn:
    """C5 기본 DeliverFn 생성 — SES SendEmail. should_deliver 면 발송, 아니면 no-op.

    client 미지정 시 boto3 SES(lazy — local 경로 boto3 무접촉). 발신=settings.ses_sender(verify identity).
    """
    def deliver(briefing: Any) -> dict | None:
        """발송 후 SES 응답 dict 반환(MessageId 포함), 미발송 시 None."""
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
                "Subject": {"Data": subject or f"데일리 브리핑 ({_card_count(briefing)}건)"},
                "Body": {"Html": {"Data": briefing.email}},
            },
        )

    return deliver
