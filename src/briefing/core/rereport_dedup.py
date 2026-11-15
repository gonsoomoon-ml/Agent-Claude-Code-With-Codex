"""rereport_dedup — 재보도 제외: 이미 보냈거나 오늘 함께 보낼 원문(A)이나 그 사이트를 본문에서 링크한 기사(B) 중
주로 같은 발표를 옮긴 글(재보도·한국어 소개)을 뺀다(2026-10-28 사용자 결정).

★ 비교 대상은 "링크로 걸린 쌍"뿐이다 — 오늘 후보 × 지난 90일 발송을 전부 비교하면 run당 수십만 쌍이지만,
  인용 키로 걸리는 쌍은 run당 ~2건(2026-10-28 실측 7 run: 약 20만 쌍 → 12쌍). 링크가 없으면 판정하지 않는다
  (같은 사건 추측 묶기 = 2026-10-18 기각 목록과의 경계).
★ 링크가 걸리는 방식은 둘이다(2026-11-14 넓힘):
  (a)(b) B 가 A 의 주소를 정확히 링크 — 지난 90일 발송(a) · 오늘 함께 보낼 기사(b).
  (c)    B 가 A 와 같은 사이트의 다른 페이지를 링크 — 재보도는 발표 글 대신 제품 페이지·프로그램 페이지·기술
         보고서·모델 모음을 링크하는 일이 잦다(실측 17회 발송: 놓친 중복 7쌍). A 는 최근 7일 안에 보냈거나 오늘
         함께 보낼 기사, B 는 News & Media·Community 매체 글일 때만(SAME_SITE_B_CATEGORIES). 판정 호출은 run당 평균
         약 23쌍·최대 50쌍(재생 24회, 2026-10-21~11-13: (a)(b) 포함 545쌍).
  어느 쪽이든 링크는 후보를 고를 뿐이고, 빼는 결정은 쌍마다 판정자가 한다.
원칙: A 는 언제나 유지 · 판정 실패·애매함은 B 유지(fail-open) · 판정은 run 메모로 사용자 간 공유.
순수 함수 — 파이프라인과 재생 게이트(scripts/dedup_audit/rereport_replay.py)가 같은 코드를 쓴다.
설계: docs/superpowers/specs/2026-10-28-cited-rereport-dedup-design.md
"""
from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence
from datetime import datetime, timezone

from .article_identity import cite_host, cite_key
from .retrieval.rereport import RereportFn, RereportVerdict
from .stores.source_store import FrozenSource
from .top_picks import big_org

# (c) 같은 사이트 다른 페이지 판정은 통과한 글(B)이 이 분야 매체일 때만 한다(사용자 결정 2026-11-14, A2).
# 실측(관리자 발송 17회, 2026-10-28~11-13): 같은 사이트 후보 627쌍 중 "같은 발표" 10쌍은 전부 B 가 이 두 분야
# (The Decoder·PyTorch Korea)였고, B 가 1차 매체(Anthropic·Google·AWS 등)인 256쌍에서는 0쌍 — 잡을 것은 없고
# 원 발표 글이 형제 글의 재보도로 빠질 길만 생긴다. ★ 매체 분야로 글을 빼는 것이 아니다(2026-10-18 기각한
# "2차 소스 일괄 제외"와 다름) — 판정자에게 물을 범위만 정하고, 빼는 결정은 쌍마다 판정자가 한다.
SAME_SITE_B_CATEGORIES = frozenset({"News & Media", "Community"})


def _published(fetched_at: str) -> tuple[datetime, bool] | None:
    """동결본 fetched_at(실제로는 발행 시각·날짜) → (UTC 시각, 시각까지 있는가). 파싱 불가·빈값은 None.

    date-only(html 소스 — 페이지 메타데이터가 날짜만)는 자정으로 두되 "시각 없음"으로 표시한다.
    """
    s = (fetched_at or "").strip()
    try:
        t = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (t if t.tzinfo else t.replace(tzinfo=timezone.utc)), len(s) > 10


def _mutual_keeper(x: tuple[FrozenSource, str], y: tuple[FrozenSource, str]) -> FrozenSource | None:
    """서로 인용한 같은 날 쌍에서 남길 쪽(사용자 결정 2026-10-28). 정할 수 없으면 None(판정하지 않고 둘 다 통과).

    ① 한쪽만 빅테크 1차 글(카탈로그 category + 매체 이름에 top_picks.big_org)이면 그쪽 ② 아니면 발행이 이른 쪽.
    ★ 한쪽이라도 날짜만 있으면 날짜로만 비교한다 — 같은 날이면 순서를 모른다(None). 자정으로 비교하면 date-only
      html 소스가 늘 "이른 쪽"이 돼 시각 있는 원문이 빠진다(최종 리뷰 2026-10-28).
    """
    (fx, cx), (fy, cy) = x, y
    bx, by = bool(big_org(f"{cx} {fx.media}")), bool(big_org(f"{cy} {fy.media}"))
    if bx != by:
        return fx if bx else fy
    px, py = _published(fx.fetched_at), _published(fy.fetched_at)
    if px is None or py is None:
        return None
    (tx, x_timed), (ty, y_timed) = px, py
    kx, ky = (tx, ty) if (x_timed and y_timed) else (tx.date(), ty.date())
    if kx == ky:
        return None
    return fx if kx < ky else fy


def drop_rereports(
    survivors: list[tuple[FrozenSource, str]],
    *,
    cited: Mapping[str, tuple[str, ...]],
    sent_index: Mapping[str, str],
    get_source: Callable[[str], FrozenSource],
    judge: RereportFn,
    memo: dict[tuple[str, str], RereportVerdict],
    recent_hosts: Mapping[str, Sequence[str]] | None = None,
) -> dict[str, tuple[FrozenSource, RereportVerdict]]:
    """한 사용자의 오늘 생존자(기존 dedup 통과, (동결본, category)) → `{빠질 B source_id: (A, 판정)}`.

    cited = {source_id: 인용 키}(curate 의 cited_out) · sent_index = {cite_key(보낸 URL): source_id}
    (published_keys 의 url_index) · memo = run 공유 `{(A_sid, B_sid): 판정}` — 실패(None)도 메모해 재호출하지 않는다.
    한 B 가 여러 A 에 걸리면 하나라도 same=True 면 뺀다.
    recent_hosts = {호스트: 최근 7일 안에 보낸 기사 source_id}(published_keys 의 recent_hosts) — 주면 (c) 같은 사이트
    다른 페이지 쌍도 판정한다(빈 dict 면 같은 날 쌍만). None(기본)이면 (c) 는 꺼진다.
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

    # (c) 같은 사이트 다른 페이지: B 가 원문 기사 대신 그 사이트의 제품 페이지·기술 보고서·모델 모음을 링크(2026-11-14)
    #     — 정확히 걸린 링크는 (a)(b) 가 맡았으므로 호스트를 내지 않고, B 가 정확히 인용한 기사는 A 후보에서도 뺀다
    #     (서로 인용해 일부러 판정하지 않은 쌍을 다시 묶지 않게).
    if recent_hosts is None:
        return drops
    on_host: dict[str, list[FrozenSource]] = {}
    for fs, _cat in survivors:
        if k := cite_key(fs.url):
            on_host.setdefault(cite_host(k), []).append(fs)

    def candidates(host: str, skip: set[str]) -> Iterator[FrozenSource]:
        """그 호스트의 A 후보 — 오늘 생존자 먼저, 다음에 최근 7일 안에 보낸 기사(최근 순). 원본 없는 기사는 건너뛴다."""
        for a in on_host.get(host, ()):
            if a.source_id not in skip:
                yield a
        for sid in recent_hosts.get(host, ()):
            if sid in skip:
                continue
            try:
                a = get_source(sid)
            except Exception:  # noqa: BLE001 — 원본 없음은 그 후보만 건너뛴다
                continue
            yield a

    for b, b_cat in survivors:
        if b.source_id in drops or b_cat not in SAME_SITE_B_CATEGORIES:
            continue
        keys = cited.get(b.source_id, ())
        skip = {b.source_id} | {sent_index[k] for k in keys if k in sent_index} \
            | {by_url[k][0].source_id for k in keys if k in by_url}
        for host in dict.fromkeys(cite_host(k) for k in keys if k not in sent_index and k not in by_url):
            for a in candidates(host, skip):
                skip.add(a.source_id)
                if a.source_id in drops or a.media == b.media:
                    continue
                v = judged(a, b)
                if v.same is True:
                    drops[b.source_id] = (a, v)
                    break
            if b.source_id in drops:
                break
    return drops
