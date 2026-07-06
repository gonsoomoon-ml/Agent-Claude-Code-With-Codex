"""실 end-to-end 스모크 — 실 RSS → Strands author(Bedrock) → codex certifier → render.

검증-후-발행(verify-before-publish) 전 과정을 *실제로* 한 기사에 대해 돌려 단계별로 보여준다.
필요: AWS 자격증명(Bedrock us-east-1, Sonnet 4.6) + codex CLI(`~/.codex/config.toml` → Bedrock).

실행 (저장소 루트에서):
    uv run python scripts/e2e_smoke.py            # 기본: aws-ml 첫 기사
    uv run python scripts/e2e_smoke.py aitimes    # 다른 출처(clean RSS: aws-ml | aitimes | deepmind)
"""
from __future__ import annotations

import sys

from briefing.core import render
from briefing.core.retrieval import sources as src
from briefing.core.config import load_settings, load_user
from briefing.core.gate import interpret_card, produce_card
from briefing.core.pipeline import _FACT_USER  # 사실층 합성 사용자(general·무skill) — 파이프라인과 동일 경로
from briefing.core.stores.source_store import SourceStore


def main() -> None:
    source_key = sys.argv[1] if len(sys.argv) > 1 else "aws-ml"
    user_id = sys.argv[2] if len(sys.argv) > 2 else "gonsoo"

    settings = load_settings()
    store = SourceStore(settings.source_store_path)
    user = load_user(user_id, settings)
    print(f"[설정] author={settings.author_model_id} region={settings.region} user={user.id} lens={user.lens}")

    source = next((s for s in src.CATALOG if s.key == source_key), None)
    if source is None:
        sys.exit(f"알 수 없는 출처 '{source_key}' — 가능: {[s.key for s in src.CATALOG]}")
    if source.fragile:
        sys.exit(f"'{source_key}' 는 fragile(Browser Tool v1.5) — clean RSS 로 시도: aws-ml | aitimes | deepmind")

    print(f"[1] fetch: {source.key} ({source.url})")
    articles = src.fetch_clean_rss(source, window_hours=0, max_items=1)
    if not articles:
        sys.exit(f"'{source_key}' 에서 기사를 못 받음 (피드 빈값/네트워크 확인)")
    art = articles[0]
    print(f"    → {art.title[:72]!r}  ({len(art.raw_text)}자)")

    fs = store.freeze(url=art.url, title=art.title, raw_text=art.raw_text, fetched_at=art.published_at)
    print(f"[2] freeze: source_id={fs.source_id[:16]}…  (content-addressed)")

    print("[3] 사실층: author(general·무skill) → envelope → certifier(codex) per claim … (수십 초~수 분)")
    fact = produce_card(fs, _FACT_USER, settings, store)

    print(f"[4] GATE: decision={fact.decision}  attempts={fact.attempts}  claims={len(fact.verdicts)}")
    for v in fact.verdicts:
        print(f"      {v.claim_id}: {v.verdict:8} ({v.model})  {v.evidence[:64]}")

    print(f"[5] 해석층: lens={user.lens} — draft_interpretation + 결정론 lint (실패 시 사실층 why 폴백)")
    gated = interpret_card(fact, fs, user, settings)
    print(f"    → {'해석 교체' if gated is not fact else '폴백(사실층 general why 유지)'}")
    print(f"    why: {gated.card.why_it_matters[:120]}")

    email = render.render_email([gated], user, settings, store)
    print(f"[6] render: {len(email)} bytes (depth={user.depth})\n")
    print(email)


if __name__ == "__main__":
    main()
