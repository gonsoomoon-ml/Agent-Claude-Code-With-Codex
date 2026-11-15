"""seed_users — 로컬 users/*.yaml 프로필 → briefing-users DDB 시드(H4 전환). ★ skill_md 는 *안* 씀(파일 오버레이).

왜: BACKEND=dynamo 로 전환하면 load_user 가 DDB 를 읽는데, 시드 전엔 빈 테이블 → 발송 0.
    그래서 runtime 재배포 *전에* 이걸 돌려 기존 파일 유저(gonsoo)를 DDB 로 옮긴다.
실행(저장소 루트): AWS creds + region/USERS_TABLE 은 settings(.env) →
    uv run python scripts/seed_users.py

★ 수신 주소는 추적 파일에 쓰지 않는다(저장소 공개) — gitignore 된 `.env` 에 둔다:
    SEED_RECIPIENTS=<id>=<email>[,<id>=<email>]
  지정이 있으면 그 주소로, 없으면 profile.yaml 의 값으로 시드한다. 둘 다 비면 그 사용자에서 멈춘다.
"""
from __future__ import annotations

import dataclasses
import os

from briefing.core.config import list_users, load_settings, load_user
from briefing.core.stores.dynamo import user_store_from_settings

_FIELDS = ("recipient", "type", "sources", "depth", "lens", "send_hour", "timezone")


def parse_recipient_overrides(raw: str) -> dict[str, str]:
    """`SEED_RECIPIENTS` 값 → {user_id: email}(순수). 형식이 틀린 항목은 버리지 않고 실패시킨다."""
    out: dict[str, str] = {}
    for item in (x.strip() for x in raw.split(",")):
        if not item:
            continue
        uid, sep, email = (x.strip() for x in item.partition("="))
        if not (uid and sep and email):
            raise ValueError(f"SEED_RECIPIENTS 형식 오류(<id>=<email> 이어야 함): {uid or item!r}")
        out[uid] = email
    return out


def resolve_recipient(uid: str, file_recipient: str, overrides: dict[str, str]) -> str:
    """수신 주소 결정(순수) — `.env` 지정 > profile.yaml. 둘 다 없으면 빈 수신자 행을 만들지 않고 실패."""
    recipient = overrides.get(uid) or (file_recipient or "").strip()
    if not recipient:
        raise ValueError(f"{uid}: 수신 주소 없음 — `.env` 의 SEED_RECIPIENTS={uid}=<email> 을 넣어라")
    return recipient


def _mask(email: str) -> str:
    local, _, dom = email.partition("@")
    return f"{local[:2]}***@{dom}"


def main() -> None:
    settings = load_settings()
    overrides = parse_recipient_overrides(os.environ.get("SEED_RECIPIENTS", ""))
    local = dataclasses.replace(settings, backend="local")   # 읽기는 파일에서 강제(BACKEND env 무관)
    store = user_store_from_settings(settings)               # 쓰기는 DDB(settings.users_table)
    ids = list_users(local)
    print(f"seeding {len(ids)} users → {settings.users_table} ({settings.region})")
    for uid in ids:
        u = load_user(uid, local)
        fields = {k: getattr(u, k) for k in _FIELDS}                # 7 운영 필드만 — skill_md 제외
        fields["recipient"] = resolve_recipient(uid, u.recipient, overrides)
        store.put_user(uid, fields)
        print(f"  ✅ {uid} → {_mask(fields['recipient'])} (skill_md 는 파일 유지 — trust 경계)")
    print("done. ⚠️ 다음 단계: runtime 재배포(load_user 의 DDB 분기 반영).")


if __name__ == "__main__":
    main()
