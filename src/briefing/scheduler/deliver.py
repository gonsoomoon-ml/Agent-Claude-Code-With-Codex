"""deliver — C5 DeliverFn. 기본 = SES SendEmail. **검증 발행분이 있을 때만** 발송(fail-closed).

DeliverFn = Callable[[UserBriefing], dict | None] — briefing 만 받는다. settings/client 는 클로저로 캡처
(`make_ses_deliver`). SES 응답 dict(발송 시) 또는 None(미발송) 반환. 테스트는 fake client 주입 → 실 SES 무접촉.
★ QUARANTINE/빈 발행은 발송 안 함 — render 가 PUBLISH 만 담지만, 여기서도 한 번 더 게이트(이중 안전).
★ SES sandbox: 수신자 사전 verify · @gmail 발신은 DMARC 거부 → 커스텀 도메인 발신(settings.ses_sender).
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

DeliverFn = Callable[[Any], dict | None]   # Callable[[UserBriefing], dict | None] — 덕타이핑(.recipient·.email·.published), SES 응답 또는 None 반환


def should_deliver(briefing: Any) -> bool:
    """발송 조건 = 검증 발행분 1개 이상. 0 이면(QUARANTINE-only·빈) 미발송."""
    return briefing.published > 0


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
                "Subject": {"Data": subject or f"데일리 브리핑 ({briefing.published}건)"},
                "Body": {"Html": {"Data": briefing.email}},
            },
        )

    return deliver
