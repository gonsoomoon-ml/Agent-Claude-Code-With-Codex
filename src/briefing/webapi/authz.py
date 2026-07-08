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
