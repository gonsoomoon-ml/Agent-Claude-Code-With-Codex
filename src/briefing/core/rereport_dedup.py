"""rereport_dedup — 재보도 제외: 이미 보냈거나 오늘 함께 보낼 원문(A)을 본문에서 링크한 기사(B) 중
주로 같은 발표를 옮긴 글(재보도·한국어 소개)을 뺀다(2026-10-28 사용자 결정).

★ 비교 대상은 "링크로 걸린 쌍"뿐이다 — 오늘 후보 × 지난 90일 발송을 전부 비교하면 run당 수십만 쌍이지만,
  인용 키로 걸리는 쌍은 run당 ~2건(2026-10-28 실측 7 run: 약 20만 쌍 → 12쌍). 링크가 없으면 판정하지 않는다
  (같은 사건 추측 묶기 = 2026-10-18 기각 목록과의 경계).
원칙: A 는 언제나 유지 · 판정 실패·애매함은 B 유지(fail-open) · 판정은 run 메모로 사용자 간 공유.
순수 함수 — 파이프라인과 재생 게이트(scripts/dedup_audit/rereport_replay.py)가 같은 코드를 쓴다.
설계: docs/superpowers/specs/2026-10-28-cited-rereport-dedup-design.md
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, timezone

from .article_identity import cite_key
from .retrieval.rereport import RereportFn, RereportVerdict
from .stores.source_store import FrozenSource
from .top_picks import big_org


def _published(fetched_at: str) -> datetime | None:
    """동결본 fetched_at(실제로는 발행 시각·날짜) → 비교 가능한 UTC 시각. date-only 는 자정, 파싱 불가·빈값은 None."""
    try:
        t = datetime.fromisoformat((fetched_at or "").strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def _mutual_keeper(x: tuple[FrozenSource, str], y: tuple[FrozenSource, str]) -> FrozenSource | None:
    """서로 인용한 같은 날 쌍에서 남길 쪽(사용자 결정 2026-10-28). 정할 수 없으면 None(판정하지 않고 둘 다 통과).

    ① 한쪽만 빅테크 1차 글(카탈로그 category + 매체 이름에 top_picks.big_org)이면 그쪽 ② 아니면 발행이 이른 쪽.
    """
    (fx, cx), (fy, cy) = x, y
    bx, by = bool(big_org(f"{cx} {fx.media}")), bool(big_org(f"{cy} {fy.media}"))
    if bx != by:
        return fx if bx else fy
    tx, ty = _published(fx.fetched_at), _published(fy.fetched_at)
    if tx is None or ty is None or tx == ty:
        return None
    return fx if tx < ty else fy


def drop_rereports(
    survivors: list[tuple[FrozenSource, str]],
    *,
    cited: Mapping[str, tuple[str, ...]],
    sent_index: Mapping[str, str],
    get_source: Callable[[str], FrozenSource],
    judge: RereportFn,
    memo: dict[tuple[str, str], RereportVerdict],
) -> dict[str, tuple[FrozenSource, RereportVerdict]]:
    """한 사용자의 오늘 생존자(기존 dedup 통과, (동결본, category)) → `{빠질 B source_id: (A, 판정)}`.

    cited = {source_id: 인용 키}(curate 의 cited_out) · sent_index = {cite_key(보낸 URL): source_id}
    (published_keys 의 url_index) · memo = run 공유 `{(A_sid, B_sid): 판정}` — 실패(None)도 메모해 재호출하지 않는다.
    한 B 가 여러 A 에 걸리면 하나라도 same=True 면 뺀다.
    """
    drops: dict[str, tuple[FrozenSource, RereportVerdict]] = {}

    def judged(a: FrozenSource, b: FrozenSource) -> RereportVerdict:
        key = (a.source_id, b.source_id)
        if key not in memo:
            try:
                memo[key] = judge(a.text, b.text)
            except Exception as err:  # noqa: BLE001 — 판정자 예외도 B 유지(fail-open)
                memo[key] = RereportVerdict(None, f"{type(err).__name__}: {err}")
        return memo[key]

    # (a) 과거: B 가 이 사용자에게 이미 보낸 기사(지난 90일)를 링크
    for b, _cat in survivors:
        for k in cited.get(b.source_id, ()):
            a_sid = sent_index.get(k)
            if not a_sid or a_sid == b.source_id:
                continue
            try:
                a = get_source(a_sid)
            except Exception:  # noqa: BLE001 — 원본 없음(TTL 만료분 등)은 그 키만 건너뛴다
                continue
            v = judged(a, b)
            if v.same is True:
                drops[b.source_id] = (a, v)
                break

    # (b) 같은 날: B 가 오늘 이 사용자의 다른 생존자 A 를 링크 — 이미 빠진 기사는 A 로 쓰지 않는다(둘 다 빠짐 방지)
    by_url = {k: (fs, cat) for fs, cat in survivors if (k := cite_key(fs.url))}
    for b, b_cat in survivors:
        if b.source_id in drops:
            continue
        b_key = cite_key(b.url)
        for k in cited.get(b.source_id, ()):
            hit = by_url.get(k)
            if hit is None or hit[0].source_id == b.source_id or hit[0].source_id in drops:
                continue
            a = hit[0]
            if b_key and b_key in cited.get(a.source_id, ()):   # 서로 인용 — 남길 쪽이 B 면 이 방향은 판정하지 않는다
                if _mutual_keeper(hit, (b, b_cat)) is not a:
                    continue
            v = judged(a, b)
            if v.same is True:
                drops[b.source_id] = (a, v)
                break
    return drops
