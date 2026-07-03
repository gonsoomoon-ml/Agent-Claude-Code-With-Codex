"""seed_users — 로컬 users/*.yaml 프로필 → briefing-users DDB 시드(H4 전환). ★ skill_md 는 *안* 씀(파일 오버레이).

왜: BACKEND=dynamo 로 전환하면 load_user 가 DDB 를 읽는데, 시드 전엔 빈 테이블 → 발송 0.
    그래서 runtime 재배포 *전에* 이걸 돌려 기존 파일 유저(gonsoo)를 DDB 로 옮긴다.
실행(저장소 루트): AWS creds + region/USERS_TABLE 은 settings(.env) →
    uv run python scripts/seed_users.py
"""
from __future__ import annotations

import dataclasses

from briefing.core.config import list_users, load_settings, load_user
from briefing.core.stores.dynamo import user_store_from_settings

_FIELDS = ("recipient", "type", "sources", "depth", "lens", "send_hour", "timezone")


def main() -> None:
    settings = load_settings()
    local = dataclasses.replace(settings, backend="local")   # 읽기는 파일에서 강제(BACKEND env 무관)
    store = user_store_from_settings(settings)               # 쓰기는 DDB(settings.users_table)
    ids = list_users(local)
    print(f"seeding {len(ids)} users → {settings.users_table} ({settings.region})")
    for uid in ids:
        u = load_user(uid, local)
        store.put_user(uid, {k: getattr(u, k) for k in _FIELDS})   # 7 운영 필드만 — skill_md 제외
        print(f"  ✅ {uid} (skill_md 는 파일 유지 — trust 경계)")
    print("done. ⚠️ 다음 단계: runtime 재배포(load_user 의 DDB 분기 반영).")


if __name__ == "__main__":
    main()
