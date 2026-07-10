"""pipeline — host-agnostic 브리핑 드라이버 (curate → 공유 사실층 → per-user 해석층 → render).

★ 오케스트레이션을 *호스트 무관* 함수로 추출 — AgentCore entrypoint·로컬 스모크·테스트가 *모두* 이 함수를 부른다
(배포 어댑터에 용접 + 스모크 중복 제거). 결정론: gate 가 비가역 결정 소유; 이 드라이버는 수집·팬아웃·렌더 *순서*만.
DI seam(fetch/draft/revise/verify/interp_fn) 그대로 통과 → 단위 테스트가 전 파이프라인을 결정론으로 덮음.

2층화(card-layering §5): 사실층(headline·summary·claims)은 general·무skill 로 출처당 1회 생성·검증 —
전 사용자 공유(키에 lens/skill 없음). 해석층(why)만 (출처, lens)당 1회. run 내 메모 + 캐시 2키.
"""
from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass

from . import _debug, render
from .retrieval import sources as src
from .authoring.author import PROMPT_VERSION
from .stores.cache import CardCache, fact_card_key, interp_card_key
from .config import Settings, UserConfig
from .retrieval.curation import FetchArticleFn, curate
from .gate import GatedCard, interpret_card, produce_card
from .lenses import DEFAULT_LENS, resolve_lens
from .stores.ledger import Ledger
from .stores.source_store import SourceStore
from .stores.usage import UsageRecorder

# 사실층 합성 사용자 — author 는 user 의 lens·skill_md 만 본다: general + 무skill = 공통 사실층.
# (id 는 로그 식별용일 뿐 프롬프트에 안 들어감; gate/certifier 는 원래 user-blind.)
_FACT_USER = UserConfig(
    id="__fact__", recipient="", type="", sources=(), depth="summary",
    lens=DEFAULT_LENS, send_hour=0, timezone="", skill_md="",
)


@dataclass(frozen=True)
class UserBriefing:
    user_id: str
    recipient: str
    cards: tuple[GatedCard, ...]
    email: str
    published: int
    quarantined: int
    cost_usd: float = 0.0      # 이 사용자 iteration 실제 발생 비용(캐시히트=0)
    duration_ms: int = 0       # 이 사용자 iteration 벽시계 시간


def run_briefing(
    settings: Settings,
    store: SourceStore,
    users: Sequence[UserConfig],
    *,
    window_hours: int = 24,
    fetch_article_fn: FetchArticleFn | None = None,
    relevance_fn=None,
    draft_fn=None,
    revise_fn=None,
    verify_fn=None,
    interp_fn=None,
    card_cache: CardCache | None = None,
    ledger: Ledger | None = None,
    run_date: str = "",
    recorder: UsageRecorder | None = None,
) -> list[UserBriefing]:
    """공유 수집(union)→동결 → 공유 사실층 → per-user [해석층 → render]. 사용자별 UserBriefing 목록 반환.

    ★ gate/certifier 는 user-blind(trust 경계). 배달(SES)·QUARANTINE 행선지는 호출자(어댑터) 책임 — 여기선 산출만.
    run 내 메모(사실층=출처당 1회, 해석층=(출처,lens)당 1회)는 캐시 유무와 무관하게 보장 — 비용 O(기사)+O(기사×lens).
    """
    fetch_targets = src.fetch_set(u.sources for u in users)  # 모든 사용자 선택의 합집합 1회
    by_key = curate(store, fetch_targets, window_hours=window_hours,
                    fetch_article_fn=fetch_article_fn, relevance_fn=relevance_fn)

    out: list[UserBriefing] = []
    rec = recorder if recorder is not None else UsageRecorder()
    fact_memo: dict[str, GatedCard] = {}                 # run 내 사실층 공유 (source_id →)
    interp_memo: dict[tuple[str, str], GatedCard] = {}   # run 내 해석층 공유 ((source_id, lens) →)
    today = render.format_briefing_date(run_date)
    for u in users:
        before = rec.total()
        t0 = time.monotonic()
        # (frozen, category) 쌍 — category 는 출처 카탈로그 Source.category (분야 그룹 키)
        fs_cat = [(fs, s.category) for s in src.resolve_sources(u.sources) for fs in by_key.get(s.key, [])]
        # ★ 카드별 격리(비협상): 한 카드의 author/certify 실패(TimeoutExpired·throttle rc≠0·네트워크)가
        #   *브리핑 전체*를 무너뜨리지 않게 각 카드를 개별 try 로 감싼다 — 실패 카드만 드롭하고 나머지는 발행.
        #   (fs↔category 를 카드와 *묶어서* 유지 → 카드 드롭 시 positional zip 오정렬 방지.)
        produced: list[tuple[GatedCard, str]] = []
        for fs, cat in fs_cat:
            try:
                g = _process(fs, u, settings, store, card_cache, ledger, run_date,
                             draft_fn, revise_fn, verify_fn, interp_fn, fact_memo, interp_memo,
                             recorder=rec)
            except Exception as e:  # noqa: BLE001 — graceful degradation(스케일): 한 카드 유실이 배치를 막지 않게
                _debug.warn("pipeline card", f"{u.id}/{fs.source_id}: {type(e).__name__}: {e}")
                continue            # silent drop 아님 — 위 warn 로 관측 가능(빈-발송 알림은 별도 계층)
            produced.append((g, cat))
        cards = tuple(g for g, _ in produced)
        # render 는 *카드의* source_id 로 분야를 찾는다(실 author 는 fs.source_id 복사) → 카드 기준으로 매핑
        source_categories = {g.card.source_id: cat for g, cat in produced}
        out.append(
            UserBriefing(
                user_id=u.id,
                recipient=u.recipient,
                cards=cards,
                email=render.render_email(
                    cards, u, settings, store, source_categories=source_categories, today=today
                ),
                published=sum(1 for c in cards if c.decision == "PUBLISH"),
                quarantined=sum(1 for c in cards if c.decision == "QUARANTINE"),
                cost_usd=round(rec.total() - before, 6),
                duration_ms=int((time.monotonic() - t0) * 1000),
            )
        )
    return out


def _process(fs, u, settings, store, card_cache, ledger, run_date,
             draft_fn, revise_fn, verify_fn, interp_fn, fact_memo, interp_memo,
             recorder=None) -> GatedCard:
    """2층 처리: 공유 사실층(작성+검증, general·무skill) → lens 해석층(가드된 why 교체) + 캐시 2키 + ledger.

    - 사실층: fact_memo(run 내) → card_cache(fact_key) → produce_card(_FACT_USER). 전 사용자 공유.
    - 해석층: lens=general 이면 사실층 그대로(동일물). 아니면 interp_memo → card_cache(interp_key)
      → gate.interpret_card(가드·격리·폴백 소유). QUARANTINE 사실층은 interpret_card 가 스스로 차단.
    - ledger 는 사용자가 실제 받은 카드의 키(fact_key 또는 interp_key)로 기록 — history join 유지.
    """
    fact_key = fact_card_key(fs.source_id, getattr(settings, "author_model_id", ""), PROMPT_VERSION)
    fact = fact_memo.get(fs.source_id)
    if fact is None and card_cache is not None:
        fact = card_cache.get(fact_key)
    if fact is None:
        fact = produce_card(fs, _FACT_USER, settings, store,
                            draft_fn=draft_fn, revise_fn=revise_fn, verify_fn=verify_fn,
                            recorder=recorder)
        if card_cache is not None:
            card_cache.put(fact_key, fact)
    fact_memo[fs.source_id] = fact

    lens = resolve_lens(getattr(u, "lens", "") or "").key   # 미상 lens 는 general 로 폴백(기존 계약)
    if lens == DEFAULT_LENS or fact.decision == "QUARANTINE":
        gated, key = fact, fact_key                          # 사실층 = general 카드 그 자체
    else:
        key = interp_card_key(fs.source_id, lens, fact_key)
        gated = interp_memo.get((fs.source_id, lens))
        if gated is None and card_cache is not None:
            gated = card_cache.get(key)
        if gated is None:
            gated = interpret_card(fact, fs, u, settings, interp_fn=interp_fn, recorder=recorder)
            # 폴백(해석 실패 → fact 그대로)은 캐시에 안 굳힌다 — 다음 run 에서 해석 재시도 가능하게.
            # (interpret_card 는 폴백 시 fact *객체*를 반환 → identity 로 성공/폴백 구분.)
            if card_cache is not None and gated is not fact:
                card_cache.put(key, gated)
        interp_memo[(fs.source_id, lens)] = gated

    if ledger is not None:
        ledger.append(run_date, u.id, fs.source_id, key, gated.decision, gated.card.headline)
    return gated
