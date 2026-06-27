"""local baseline — AWS 없이 파이프라인 골격을 실행/검증 (다중 사용자 + 출처 선택 + 요약 lens).

흐름 (공유 수집 + per-user 팬아웃; gate 가 오케스트레이션):
  [공유]     fetch_set(모든 사용자 선택 합집합) → fetch → store.freeze(sha256)
  [per-user] resolve_sources(user) → gate.produce_card(source, user):
             author(base+lens+skill) → certify → 실패 시 재도출 루프 → PUBLISH / QUARANTINE
             → render(PUBLISH 만, user.depth) → send(user.recipient)   ← gate/certifier 는 user 안 봄
LLM/AWS 단계는 stub — 결정론 골격 + 다중 사용자·출처·lens 로딩만 실연.

실행: `uv run python -m briefing.local.run`
"""
from __future__ import annotations

from briefing.shared import lenses
from briefing.shared.retrieval import sources as src
from briefing.shared.config import list_users, load_settings, load_user
from briefing.shared.stores.source_store import SourceStore


def main() -> None:
    settings = load_settings()
    store = SourceStore(settings.source_store_path)

    print(f"[config] region={settings.region}  author={settings.author_model_id}")
    print(f"[config] sender={settings.ses_sender}  users_dir={settings.users_dir}")

    print(f"[catalog] {len(src.CATALOG)} 출처 (전역 vetted — (웹)UI 가 여기서 선택):")
    for s in src.CATALOG:
        flag = "  (fragile → Browser Tool, v1.5)" if s.fragile else ""
        print(f"   - {s.key:9} {s.kind:4} {s.lang}  {s.url}{flag}")
    print(f"[lenses]  {len(lenses.LENS_LIBRARY)} 관점: {[ln.key for ln in lenses.LENS_LIBRARY]}")

    users = [load_user(uid, settings) for uid in list_users(settings)]

    # ── 공유 수집 = 모든 사용자 선택의 합집합만 1회 fetch (content-addressing 이 dedup) ──
    fetch_targets = src.fetch_set(u.sources for u in users)
    print(f"[fetch]  합집합 {len(fetch_targets)} 출처 공유 수집 (사용자 {len(users)} 명 선택 union)")

    # 공유 결정론 핵심: 정본 1건 동결(content-addressed source-of-record)
    demo = store.freeze(
        url="https://example.com/demo",
        title="(demo) source-of-record 동결 테스트",
        raw_text="Anthropic 서울 오피스를 개소했다.\r\n직원 약 100명 규모로 시작한다.\r\n",
        fetched_at="2026-06-26T00:00:00Z",
    )
    assert store.get_source(demo.source_id).text == demo.text
    print(f"[store]  frozen source_id={demo.source_id[:16]}…  ✓ 공유 source-of-record")

    # ── per-user 팬아웃 (design-for-N, run-for-1) ──
    print(f"[users]  {len(users)} 명:")
    for u in users:
        srcs = src.resolve_sources(u.sources)
        ln = lenses.resolve_lens(u.lens)
        keys = ",".join(s.key for s in srcs)
        print(
            f"   - {u.id}: → {u.recipient} | lens={ln.key} | sources {len(srcs)}/{len(src.CATALOG)} [{keys}] "
            f"| depth={u.depth} @ {u.send_hour:02d}:00 {u.timezone} | skill.md {len(u.skill_md.splitlines())} 줄"
        )

    print("[next]   per-user: gate.produce_card(author→certify→재도출 루프 → PUBLISH/QUARANTINE)  ← gate/certifier user-blind")
    print("[next]   ★ certifier 가 lens/skill/출처를 안 보므로 사용자가 그것으로 검증을 약화 못 함(trust 경계 enforce).")


if __name__ == "__main__":
    main()
