"""trial — 체험하기 검증·가드·오케스트레이션(순수/DI). app.py 가 실 boto3 로 배선.

raw SES 검증(v1.1a): get_identity_verification_attributes → 미검증이면 verify_email_identity 트리거.
가드(⑤ 보호): 이메일 1h 쿨다운 · 전역 일일 cap. 검증 감지·발송은 runtime mode=trial 이 polling 으로.
"""
from __future__ import annotations

import re
from typing import Any, Callable

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def validate_trial(email: str, sources: list[str], catalog_keys) -> str | None:
    """검증 실패 메시지(한 줄) or None. config.py 검증 TODO 의 web 계층 일부."""
    if not (email and _EMAIL_RE.match(email)):
        return "유효한 이메일을 입력하세요."
    keyset = set(catalog_keys)
    if not sources or not (1 <= len(sources) <= 5):
        return "출처를 1~5개 선택하세요."
    if any(s not in keyset for s in sources):
        return "알 수 없는 출처가 포함되어 있습니다."
    return None


class TrialStore:
    """briefing-trials DDB 래퍼 — 쿨다운·전역 cap·기록. lazy boto3는 app.py 가 주입(table resource)."""

    def __init__(self, table: Any):
        self._t = table

    def within_cooldown(self, email: str) -> bool:
        item = self._t.get_item(Key={"email": email}).get("Item")
        return bool(item and item.get("status") in ("verification_pending", "sending"))

    def over_global_cap(self, date: str, cap: int) -> bool:
        r = self._t.update_item(
            Key={"email": f"GLOBAL#{date}"},
            UpdateExpression="ADD trial_count :one",
            ExpressionAttributeValues={":one": 1},
            ReturnValues="UPDATED_NEW",
        )
        return int(r["Attributes"]["trial_count"]) > cap

    def record(self, email: str, status: str, *, ttl: int = 0) -> None:
        self._t.put_item(Item={"email": email, "status": status, "ttl": ttl})

    def get_status(self, email: str) -> dict:
        """이메일 상태 조회. 행 없으면 status:unknown 반환."""
        item = self._t.get_item(Key={"email": email}).get("Item") or {}
        out = {"status": item.get("status", "unknown")}
        if "published" in item:
            out["published"] = int(item["published"])
        return out


def handle_trial(
    payload: dict, *, store, ses, runtime_invoke: Callable[[str, dict], None],
    cap: int, cooldown_s: int, today: str, catalog_keys,
) -> tuple[int, dict]:
    """POST /trial 코어. (status_code, body). 부수효과(ses·invoke)는 주입된 객체로."""
    email = (payload.get("email") or "").strip().lower()
    sources = payload.get("sources") or []
    err = validate_trial(email, sources, catalog_keys)
    if err:
        return 400, {"error": err}
    if store.within_cooldown(email):
        return 429, {"error": "최근에 이미 요청했어요. 잠시 후 다시 시도하세요."}
    if store.over_global_cap(today, cap):
        return 429, {"error": "오늘 체험 한도가 찼어요. 내일 다시 시도해주세요."}

    attrs = ses.get_identity_verification_attributes(Identities=[email])
    verified = (attrs.get("VerificationAttributes", {}).get(email, {})
                .get("VerificationStatus") == "Success")
    if not verified:
        ses.verify_email_identity(EmailAddress=email)
    status = "sending" if verified else "verification_pending"

    import time as _t  # ttl 계산만(테스트는 now_iso 무관)
    store.record(email, status, ttl=int(_t.time()) + cooldown_s)
    runtime_invoke("trial", {
        "mode": "trial", "email": email, "sources": list(sources),
        "depth": payload.get("depth", "summary"), "lens": payload.get("lens", "general"),
        "timezone": payload.get("timezone", "Asia/Seoul"),
    })
    return 202, {"status": status}
