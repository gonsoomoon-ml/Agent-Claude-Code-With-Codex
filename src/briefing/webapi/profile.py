"""profile — 구독 프로필 검증(순수/DI). app.py 가 JWT claims·DynamoUserStore 로 배선.

★ 보안: PK·recipient 는 *검증된 JWT claims* 에서만(app.py). 여기선 6 선호 필드 catalog 검증만.
"""
from __future__ import annotations

from collections.abc import Sequence


def validate_profile(fields: dict, *, catalog_keys, lens_keys, depths, send_hours,
                     types: Sequence[str] = ("ai-news",), max_sources: int = 5) -> str | None:
    """6 선호 필드 검증 실패 메시지 or None. recipient/user_id 는 여기서 안 봄(JWT 소유)."""
    sources = fields.get("sources") or []
    if not (1 <= len(sources) <= max_sources):
        return f"출처를 1~{max_sources}개 선택하세요."
    if any(s not in set(catalog_keys) for s in sources):
        return "알 수 없는 출처가 포함되어 있습니다."
    if fields.get("type", "ai-news") not in set(types):
        return "지원하지 않는 브리핑 종류입니다."
    if fields.get("depth", "summary") not in set(depths):
        return "알 수 없는 depth."
    if fields.get("lens", "general") not in set(lens_keys):
        return "알 수 없는 lens."
    try:
        sh = int(fields.get("send_hour", 7))
    except (TypeError, ValueError):
        return "send_hour 형식 오류."
    if sh not in set(send_hours):
        return "지원하지 않는 발송 시각."
    tz = fields.get("timezone", "Asia/Seoul")
    if not isinstance(tz, str):
        return "timezone 형식 오류."
    try:
        from zoneinfo import ZoneInfo
        ZoneInfo(tz)
    except Exception:  # noqa: BLE001 — 미지 tz 는 due 계산을 오염시킴
        return "알 수 없는 시간대입니다."
    return None
