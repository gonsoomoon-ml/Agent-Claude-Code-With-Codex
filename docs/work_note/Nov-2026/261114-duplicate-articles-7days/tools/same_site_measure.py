#!/usr/bin/env python3
"""문제 2 범위 재기(읽기 전용): 발송된 기사 B 가 "이미 보냈거나 같은 날 보낸 기사 A 와 같은 사이트의 다른 페이지"를
링크한 쌍을 모으고, 운영 판정자에게 같은 발표인지 물어본다.

    uv run python docs/work_note/Nov-2026/261114-duplicate-articles-7days/tools/same_site_measure.py <출력.json>

- 대상: 관리자 발송 카드, run_date 2026-10-28 ~ 11-13(재보도 제외 출시 이후 17회).
- 정확히 걸린 링크(운영이 이미 판정하는 쌍)는 뺀다. 남은 인용 키의 호스트가 최근 7일(같은 날 포함) 발송 기사 A 의
  호스트와 같으면 후보 쌍. 호스트가 다른 같은 회사 사이트(anthropic.com ↔ claude.com 등)는 세지 않는다.
- 판정은 쌍마다 2회(현재 체크아웃의 프롬프트).
- ★ 끝의 집계는 판정 실패(`same` 이 None — 응답 JSON 을 못 읽음)를 따로 센다. 2026-11-14 에 돌린 판은 실패를 "다름"에
  섞어 셌다 — 저장된 `same-site-measure.txt` 의 "2회 모두 다름 617"은 다름 616 + 2회 모두 판정 실패 1 이다.
"""
from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

from briefing.core.article_identity import cite_key, published_keys
from briefing.core.config import DEFAULT_DEDUP_LOOKBACK_DAYS, load_settings
from briefing.core.retrieval.relevance_bedrock import make_bedrock_rereport
from briefing.core.retrieval.sources import _cited_keys, _http_get
from briefing.core.stores.dynamo import ledger_from_settings, source_store_from_settings

OUT = sys.argv[1]
ADMIN = "445814b8-5001-70a6-84a6-6c010ac347ba"
SINCE, UNTIL, WINDOW = "2026-10-28", "2026-11-13", 7

s = load_settings()
ledger, store = ledger_from_settings(s), source_store_from_settings(s)
judge = make_bedrock_rereport(s)
rows = [r for r in ledger.query(ADMIN) if r.get("decision") in ("PUBLISH", "QUARANTINE")]
first_run: dict[str, str] = {}
for r in sorted(rows, key=lambda r: r["run_date"]):
    first_run.setdefault(r["source_id"], r["run_date"])
src_cache: dict[str, object] = {}


def src(sid):
    if sid not in src_cache:
        try:
            src_cache[sid] = store.get_source(sid)
        except KeyError:
            src_cache[sid] = None
    return src_cache[sid]


def cited_of(fs):
    html = _http_get(fs.url)
    return _cited_keys(html, fs.url) if html else ()


def host(key: str) -> str:
    return key.split("/", 1)[0]


cands: dict[tuple[str, str], dict] = {}
exact = 0
meta_memo: dict = {}
d, end = date.fromisoformat(SINCE), date.fromisoformat(UNTIL)
while d <= end:
    rd = d.isoformat()
    lo = (d - timedelta(days=WINDOW)).isoformat()
    d += timedelta(days=1)
    today = [fs for sid in sorted({r["source_id"] for r in rows if r["run_date"] == rd}) if (fs := src(sid))]
    if not today:
        continue
    with ThreadPoolExecutor(8) as ex:
        cited = dict(zip([fs.source_id for fs in today], ex.map(cited_of, today)))
    sent_index: dict[str, str] = {}
    published_keys(ledger, store, ADMIN, rd, DEFAULT_DEDUP_LOOKBACK_DAYS, meta_memo, url_index=sent_index)
    today_keys = {k: fs.source_id for fs in today if (k := cite_key(fs.url))}
    # 최근 7일(같은 날 포함) 발송 기사 — 호스트별
    recent: dict[str, list[str]] = {}
    for k, sid in list(sent_index.items()) + list(today_keys.items()):
        fr = first_run.get(sid, "")
        if lo <= fr <= rd:
            recent.setdefault(host(k), []).append(sid)
    n_day = 0
    for b in today:
        for k in cited.get(b.source_id, ()):
            if (sent_index.get(k) or today_keys.get(k)) not in (None, b.source_id):
                exact += 1
                continue
            for a_sid in recent.get(host(k), ()):
                if a_sid == b.source_id or (a_sid, b.source_id) in cands:
                    continue
                a = src(a_sid)
                if a is None or a.media == b.media:
                    continue
                cands[(a_sid, b.source_id)] = dict(run_date=rd, a_run=first_run.get(a_sid), cited=k, a_sid=a_sid,
                                                   b_sid=b.source_id, a_title=a.title, b_title=b.title, a_media=a.media,
                                                   b_media=b.media, a_url=a.url, b_url=b.url)
                n_day += 1
    print(f"{rd}: 발송 {len(today)} · 후보 쌍 +{n_day}", flush=True)

print(f"정확히 걸린 링크 {exact} · 같은 사이트 다른 페이지 후보 {len(cands)}쌍 → 판정 2회씩", flush=True)


def run(c):
    a, b = src(c["a_sid"]), src(c["b_sid"])
    vs = [judge(a.text, b.text) for _ in range(2)]
    return dict(c, same=[v.same for v in vs], reason=vs[0].reason)


with ThreadPoolExecutor(6) as ex:
    out = list(ex.map(run, cands.values()))
json.dump(out, open(OUT, "w"), ensure_ascii=False, indent=1)
both = [c for c in out if c["same"] == [True, True]]
failed = [c for c in out if None in c["same"]]
mixed = [c for c in out if sorted(map(str, c["same"])) == ["False", "True"]]
print(f"\n2회 모두 같은 발표 {len(both)} · 갈림 {len(mixed)} · 판정 실패 포함 {len(failed)} · "
      f"2회 모두 다름 {len(out) - len(both) - len(mixed) - len(failed)}")
for c in sorted(both + mixed + failed, key=lambda c: (c["run_date"], c["b_title"])):
    tag = "같음" if c["same"] == [True, True] else ("실패" if None in c["same"] else "갈림")
    print(f"\n{c['run_date'][5:]} {tag} B [{c['b_media'][:16]}] {c['b_title'][:64]}\n"
          f"        A [{c['a_media'][:16]}] ({c['a_run'][5:]}) {c['a_title'][:60]}\n"
          f"        B 가 건 링크: {c['cited'][:100]}\n        A 주소: {c['a_url'][:100]}")
