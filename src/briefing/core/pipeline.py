"""pipeline — host-agnostic 브리핑 드라이버 (curate → 공유 사실층 → per-user 해석층 → render).

★ 오케스트레이션을 *호스트 무관* 함수로 추출 — AgentCore entrypoint·로컬 스모크·테스트가 *모두* 이 함수를 부른다
(배포 어댑터에 용접 + 스모크 중복 제거). 결정론: gate 가 비가역 결정 소유; 이 드라이버는 수집·팬아웃·렌더 *순서*만.
DI seam(fetch/draft/revise/verify/interp_fn) 그대로 통과 → 단위 테스트가 전 파이프라인을 결정론으로 덮음.

2층화(card-layering §5): 사실층(headline·summary·claims)은 general·무skill 로 출처당 1회 생성·검증 —
전 사용자 공유(키에 lens/skill 없음). 해석층(why)만 (출처, lens)당 1회. run 내 메모 + 캐시 2키.
"""
from __future__ import annotations

import time
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from . import _debug, quality_checks, render
from .article_identity import identity_keys, match_kind, published_keys
from .retrieval import sources as src
from .authoring.author import INTERP_PROMPT_VERSION, PROMPT_VERSION
from .stores.cache import CardCache, fact_card_key, interp_card_key
from .config import DEFAULT_DEDUP_LOOKBACK_DAYS, Settings, UserConfig
from .retrieval.curation import FetchArticleFn, curate
from .retrieval.headlines import HeadlineAreaFn, HeadlineFetchFn, HeadlineSelectFn, collect_headlines
from .gate import GatedCard, interpret_card, produce_card
from .lenses import DEFAULT_LENS, resolve_lens
from .stores.ledger import Ledger
from .stores.source_store import SourceStore
from .stores.usage import UsageRecorder
from .top_picks import TopPickFn, top_source_ids

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
    headline_fetch_fn: HeadlineFetchFn | None = None,
    headline_select_fn: HeadlineSelectFn | None = None,
    headline_area_fn: HeadlineAreaFn | None = None,
    relevance_fn=None,
    select_fn=None,
    draft_fn=None,
    revise_fn=None,
    verify_fn=None,
    interp_fn=None,
    top_pick_fn: TopPickFn | None = None,
    card_cache: CardCache | None = None,
    ledger: Ledger | None = None,
    run_date: str = "",
    sent_at: datetime | None = None,
    recorder: UsageRecorder | None = None,
) -> list[UserBriefing]:
    """공유 수집(union)→동결 → 공유 사실층 → per-user [해석층 → render]. 사용자별 UserBriefing 목록 반환.

    ★ gate/certifier 는 user-blind(trust 경계). 배달(SES)·QUARANTINE 행선지는 호출자(어댑터) 책임 — 여기선 산출만.
    run 내 메모(사실층=출처당 1회, 해석층=(출처,lens)당 1회)는 캐시 유무와 무관하게 보장 — 비용 O(기사)+O(기사×lens).
    """
    fetch_targets = src.fetch_set(u.sources for u in users)  # 모든 사용자 선택의 합집합 1회
    by_key = curate(store, fetch_targets, window_hours=window_hours,
                    fetch_article_fn=fetch_article_fn, relevance_fn=relevance_fn, select_fn=select_fn)
    # 제목·링크 전용 소스(headlines_only) — 본문 미수집·카드 없음. 판정자(Haiku)는 제목만 받는다(headlines.py).
    # covered = 이번 run 카드 소스의 동결본 제목(전 사용자 합집합) → 헤드라인 칸이 카드와 같은 소식을 반복하지 않게.
    covered = [fs.title for fss in by_key.values() for fs in fss]
    headlines = collect_headlines(fetch_targets, window_hours=window_hours, fetch_fn=headline_fetch_fn,
                                  relevance_fn=relevance_fn, headline_select_fn=headline_select_fn,
                                  headline_area_fn=headline_area_fn, covered_titles=covered)

    out: list[UserBriefing] = []
    rec = recorder if recorder is not None else UsageRecorder()
    fact_memo: dict[str, GatedCard] = {}                 # run 내 사실층 공유 (source_id →)
    interp_memo: dict[tuple[str, str], GatedCard] = {}   # run 내 해석층 공유 ((source_id, lens) →)
    lookback_days = getattr(settings, "dedup_lookback_days", DEFAULT_DEDUP_LOOKBACK_DAYS)
    meta_memo: dict = {}   # source_id → SourceMeta | None — run 동안 사용자 간 공유(dedup join 은 사실상 run당 1회)
    top_memo: dict = {}    # 발행 카드 묶음 → 오늘의 핵심 3 source_id — 같은 묶음을 받는 사용자는 판정 1회 공유
    shadow = {"cards": 0, "hits": Counter()}   # S3 그림자 검사 집계 — 이 run 에서 새로 만든 사실층 카드 기준
    for u in users:
        # 머리 날짜 = 발송 시각(sent_at)을 받는 사람 시간대로 바꾼 날짜(없으면 run_date). run_date 는 저장 키라 UTC 그대로.
        today = render.briefing_date(run_date, sent_at, getattr(u, "timezone", ""))
        before = rec.total()
        t0 = time.monotonic()
        # (frozen, category) 쌍 — category 는 출처 카탈로그 Source.category (분야 그룹 키)
        fs_cat = [(fs, s.category) for s in src.resolve_sources(u.sources) for fs in by_key.get(s.key, [])]
        # ★ cross-day 발행 dedup — "사용자당 기사 1회". 신원 = 해시·URL·(매체,제목) 키 3종(article_identity):
        #   원문 수정(해시 변경)·slug 변경(URL 변경)에도 같은 기사로 본다. 과거 기사 메타는 source-store join.
        #   의미론 3결정(PUBLISH 만 · strictly-earlier · run_date 빈값이면 off)은 published_keys 가 보존.
        seen: frozenset[str] = frozenset()
        if ledger is not None and run_date:
            try:
                seen = published_keys(ledger, store, u.id, run_date, lookback_days, meta_memo)
            except Exception as e:  # noqa: BLE001 — dedup 은 보조 장치: DDB 오류가 전 사용자 브리핑을 막으면 안 된다
                _debug.warn("pipeline dedup", f"{u.id}: 이전 발행 조회 실패 — 이번 run 은 dedup off(fail-open): "
                                              f"{type(e).__name__}: {e}")   # 빈 메일함보다 중복 1건이 낫다
        # ★ 카드별 격리(비협상): 한 카드의 author/certify 실패(TimeoutExpired·throttle rc≠0·네트워크)가
        #   *브리핑 전체*를 무너뜨리지 않게 각 카드를 개별 try 로 감싼다 — 실패 카드만 드롭하고 나머지는 발행.
        #   (fs↔category 를 카드와 *묶어서* 유지 → 카드 드롭 시 positional zip 오정렬 방지.)
        produced: list[tuple[GatedCard, str]] = []
        deduped = 0
        for fs, cat in fs_cat:
            kind = match_kind(identity_keys(source_id=fs.source_id, url=fs.url, title=fs.title, media=fs.media),
                              seen) if seen else ""
            if kind:
                deduped += 1
                if kind != "sid":  # 새 신원 키로 막힌 건 항상 warn — 오탐이 있으면 여기서 보인다(해시 일치는 48h 겹침의 일상)
                    _debug.warn("pipeline dedup", f"{u.id}: {kind} 키 일치 — 이전 발행 기사 제외: {fs.title[:50]}")
                continue
            try:
                g = _process(fs, u, settings, store, card_cache, ledger, run_date,
                             draft_fn, revise_fn, verify_fn, interp_fn, fact_memo, interp_memo,
                             recorder=rec, shadow=shadow)
            except Exception as e:  # noqa: BLE001 — graceful degradation(스케일): 한 카드 유실이 배치를 막지 않게
                _debug.warn("pipeline card", f"{u.id}/{fs.source_id}: {type(e).__name__}: {e}")
                continue            # silent drop 아님 — 위 warn 로 관측 가능(빈-발송 알림은 별도 계층)
            produced.append((g, cat))
        if deduped:  # non-silent — 무엇이/몇 건 빠졌나 기록(curate filter 와 동형)
            _debug.dprint("pipeline dedup", f"{u.id}: 이전 발행 {deduped}건 제외(ledger)", "yellow")
        cards = tuple(g for g, _ in produced)
        # render 는 *카드의* source_id 로 분야를 찾는다(실 author 는 fs.source_id 복사) → 카드 기준으로 매핑
        source_categories = {g.card.source_id: cat for g, cat in produced}
        top = top_source_ids(cards, top_pick_fn, top_memo)   # 발행 6장 미만·미주입·실패면 () = 핵심 칸 없음
        out.append(
            UserBriefing(
                user_id=u.id,
                recipient=u.recipient,
                cards=cards,
                email=render.render_email(
                    cards, u, settings, store, source_categories=source_categories, today=today,
                    headlines=[h for s in src.resolve_sources(u.sources) for h in headlines.get(s.key, [])],
                    top_picks=top,
                ),
                published=sum(1 for c in cards if c.decision == "PUBLISH"),
                quarantined=sum(1 for c in cards if c.decision == "QUARANTINE"),
                cost_usd=round(rec.total() - before, 6),
                duration_ms=int((time.monotonic() - t0) * 1000),
            )
        )
    if shadow["cards"]:  # S3 — run 마다 한 줄(CloudWatch). M1 정기 지표·U8 ② 전후 비교의 원자료
        hits = " · ".join(f"{k} {v}" for k, v in sorted(shadow["hits"].items())) or "걸림 0"
        _debug.warn("quality shadow 집계", f"새 사실층 카드 {shadow['cards']}장 · {hits}")
    unresolved = sum(1 for m in meta_memo.values() if m is None)
    if unresolved:  # 07-24 이전 행(TTL 만료분)이 90일 창을 벗어나면 0 으로 수렴 — 다시 늘면 source-store 이상 신호
        _debug.warn("pipeline dedup", f"source-store 에 원본 없는 이전 발행 {unresolved}건 — 해시로만 비교(fail-open)")
    return out


def _process(fs, u, settings, store, card_cache, ledger, run_date,
             draft_fn, revise_fn, verify_fn, interp_fn, fact_memo, interp_memo,
             recorder=None, shadow=None) -> GatedCard:
    """2층 처리: 공유 사실층(작성+검증, general·무skill) → lens 해석층(가드된 why 교체) + 캐시 2키 + ledger.

    - 사실층: fact_memo(run 내) → card_cache(fact_key) → produce_card(_FACT_USER). 전 사용자 공유.
    - 해석층: lens=general 이면 사실층 그대로(동일물). 아니면 interp_memo → card_cache(interp_key)
      → gate.interpret_card(가드·격리·폴백 소유). QUARANTINE 사실층도 해석한다(N5 — ⚠ 표시로 메일에 실림).
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
        _shadow_log(fact, fs, shadow)   # 새로 만든 카드만 — 캐시 히트는 만들 때 이미 검사했다
    fact_memo[fs.source_id] = fact

    lens = resolve_lens(getattr(u, "lens", "") or "").key   # 미상 lens 는 general 로 폴백(기존 계약)
    if lens == DEFAULT_LENS:
        gated, key = fact, fact_key                          # 사실층 = general 카드 그 자체
    else:
        key = interp_card_key(fs.source_id, lens, fact_key, INTERP_PROMPT_VERSION)
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


def _shadow_log(fact: GatedCard, fs, shadow) -> None:
    """S3 그림자 검사(2026-10-18) — 걸린 검사를 CloudWatch 에 한 줄씩 남긴다. **로그만**: 판정·메일·캐시는 그대로.

    검사 실패도 삼킨다 — 품질 측정이 브리핑을 막으면 안 된다(카드별 격리와 같은 원칙).
    """
    if shadow is None:
        return
    try:
        found = quality_checks.shadow_checks(fact.card, fs.text)
    except Exception as e:  # noqa: BLE001 — 그림자 검사는 보조 장치
        _debug.warn("quality shadow", f"{fs.source_id[:12]} 검사 실패(무시): {type(e).__name__}: {e}")
        return
    shadow["cards"] += 1
    for f in found:
        shadow["hits"][f.check] += 1
        _debug.warn("quality shadow", f"{fs.source_id[:12]} {f.check}: {f.detail}")
