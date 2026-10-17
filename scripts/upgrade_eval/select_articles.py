"""기사 12건 층화 선정(설계 §5) — 운영 데이터는 읽기만 하고, 원문은 저장소 밖 로컬 저장소에 복사한다.

층(소스 종류·뉴스는 언어까지)마다 고정 시드로 무작위 추출한 뒤, 잘린 원문·짧은 글·숫자·유보·인용 조건을
같은 층 안의 교체로 채운다. 교체는 이미 채운 조건을 깨지 않는 것만 하고, 채울 수 없으면 조용히 넘어가지
않고 shortfalls 에 적는다. manifest 에는 원문을 넣지 않는다(저작권).
"""
from __future__ import annotations

import json
import random
import re
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Callable

from briefing.core.stores.source_store import SourceStore
from briefing.core.verification import numeric

from .common import EXP_ROOT, SEED, source_kind, source_lang
from .metrics import has_hedge

MANIFEST_PATH = Path(__file__).resolve().parent / "manifest.json"
TRUNCATED_MIN_CHARS = 7900
QUOTAS: dict[tuple[str, str | None], int] = {
    ("뉴스", "ko"): 2, ("뉴스", "en"): 2, ("기업 발표", None): 3, ("기술·연구", None): 3, ("커뮤니티", None): 2,
}
_TRUNC_TARGET = 4
_HUMAN_CHECK_KINDS = ("뉴스", "기업 발표", "기술·연구")


@dataclass(frozen=True)
class CardRow:
    source_id: str
    url: str
    title: str
    kind: str
    lang: str
    length: int
    truncated: bool
    has_numbers: bool
    has_hedge: bool
    has_quote: bool


# (이름, 조건, 최소, 최대) — 순서대로 채운다. 앞에서 채운 조건은 뒤의 교체가 깨지 못한다.
_CONSTRAINTS: list[tuple[str, Callable[[CardRow], bool], int, int | None]] = [
    ("잘린 원문", lambda r: r.truncated, 3, 5),
    ("3,000자 미만", lambda r: r.length < 3000, 1, None),
    ("숫자 많은 글", lambda r: r.has_numbers, 2, None),
    ("유보 있는 글", lambda r: r.has_hedge, 2, None),
    ("인용 있는 글", lambda r: r.has_quote, 1, None),
]


def _stratum(row: CardRow) -> tuple[str, str | None]:
    return (row.kind, row.lang if row.kind == "뉴스" else None)


def _label(stratum: tuple[str, str | None]) -> str:
    return f"{stratum[0]}({stratum[1]})" if stratum[1] else stratum[0]


def select_articles(rows: list[CardRow], *, seed: int = SEED) -> dict:
    rng = random.Random(seed)
    picked: dict[tuple, list[CardRow]] = {}
    pool: dict[tuple, list[CardRow]] = {}
    reasons: dict[str, str] = {}
    shortfalls: list[str] = []
    for stratum, quota in QUOTAS.items():
        cands = sorted((r for r in rows if _stratum(r) == stratum), key=lambda r: r.source_id)
        rng.shuffle(cands)
        picked[stratum], pool[stratum] = cands[:quota], cands[quota:]
        if len(cands) < quota:
            shortfalls.append(f"{_label(stratum)}: 후보 {len(cands)}건 < 할당 {quota}건")
        for r in picked[stratum]:
            reasons[r.source_id] = "무작위"

    def selected() -> list[CardRow]:
        return [r for s in QUOTAS for r in picked[s]]

    def holds(bounds: list[tuple[Callable, int, int | None]]) -> bool:
        sel = selected()
        return all(sum(p(r) for r in sel) >= lo and (hi is None or sum(p(r) for r in sel) <= hi) for p, lo, hi in bounds)

    def swap(want: Callable[[CardRow], bool], name: str, keep: list[tuple[Callable, int, int | None]]) -> bool:
        """같은 층에서 want 를 만족하는 후보로 만족하지 않는 선택분 하나를 바꾼다(keep 조건 유지)."""
        for stratum in QUOTAS:
            for incoming in [r for r in pool[stratum] if want(r)]:
                for i, outgoing in enumerate(picked[stratum]):
                    if want(outgoing):
                        continue
                    picked[stratum][i] = incoming
                    if holds(keep):
                        pool[stratum].remove(incoming)
                        pool[stratum].append(outgoing)
                        reasons.pop(outgoing.source_id, None)
                        reasons[incoming.source_id] = f"교체: {name}"
                        return True
                    picked[stratum][i] = outgoing
        return False

    satisfied: list[tuple[Callable, int, int | None]] = []
    for name, pred, lo, hi in _CONSTRAINTS:
        target = _TRUNC_TARGET if name == "잘린 원문" else lo
        while sum(pred(r) for r in selected()) < target and swap(pred, name, satisfied):
            pass
        if hi is not None:
            while sum(pred(r) for r in selected()) > hi and swap(lambda r, p=pred: not p(r), name, satisfied):
                pass
        n = sum(pred(r) for r in selected())
        if n < lo or (hi is not None and n > hi):
            shortfalls.append(f"조건 미충족: {name} {n}건(허용 {lo}–{hi if hi is not None else '∞'})")
        else:
            satisfied.append((pred, lo, hi))

    articles, seen_kinds = [], set()
    for r in selected():
        human = r.kind in _HUMAN_CHECK_KINDS and r.kind not in seen_kinds
        if human:
            seen_kinds.add(r.kind)
        articles.append({**asdict(r), "human_check": human, "reason": reasons[r.source_id]})
    return {"articles": articles, "shortfalls": shortfalls}


def load_manifest() -> list[dict]:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))["articles"]


# ── 운영 데이터에서 CardRow 만들기(읽기 전용) ──
_EN_HEDGE = re.compile(r"\b(may|might|could|unclear|not yet|reportedly|however|although|caveat|limitation|preview)\b", re.I)
_QUOTE_SPAN = re.compile(r"[\"“]([^\"“”]{12,})[\"”]")


def _row_from_source(item: dict) -> CardRow:
    text, url = item.get("text", ""), item.get("url", "")
    nums = numeric.scan(text)
    return CardRow(
        source_id=item["source_id"], url=url, title=item.get("title", ""), kind=source_kind(url), lang=source_lang(url),
        length=len(text), truncated=len(text) >= TRUNCATED_MIN_CHARS,
        has_numbers=len(nums.values) + len(nums.percents) >= 5,
        has_hedge=has_hedge(text) or bool(_EN_HEDGE.search(text)),
        has_quote=bool(_QUOTE_SPAN.search(text)),
    )


def main() -> None:
    import boto3

    from briefing.core.config import load_settings

    settings = load_settings()
    ddb = boto3.resource("dynamodb", region_name="us-east-1")
    cache, sources = ddb.Table(settings.cache_table), ddb.Table(settings.source_table)
    items, start = [], None
    while True:                                                   # 읽기 전용: scan 만
        kw = {"ProjectionExpression": "card_json"}
        if start:
            kw["ExclusiveStartKey"] = start
        resp = cache.scan(**kw)
        items += resp["Items"]
        start = resp.get("LastEvaluatedKey")
        if not start:
            break
    published = set()
    for it in items:
        d = json.loads(it["card_json"])
        if d.get("decision") == "PUBLISH" and not d["card"].get("based_on"):
            published.add(d["card"]["source_id"])
    source_items = {}
    for sid in sorted(published):                                 # 읽기 전용: get_item 만
        got = sources.get_item(Key={"source_id": sid}).get("Item")
        if got:
            source_items[sid] = got
    rows = [_row_from_source(it) for it in source_items.values()]
    result = select_articles(rows)
    result["meta"] = {"seed": SEED, "created": date.today().isoformat(), "population": len(rows),
                      "population_by_kind": {k: sum(r.kind == k for r in rows) for k in sorted({r.kind for r in rows})}}
    MANIFEST_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    store = SourceStore(str(EXP_ROOT / "sources"))
    for a in result["articles"]:
        it = source_items[a["source_id"]]
        fs = store.freeze(url=it["url"], title=it.get("title", ""), raw_text=it["text"],
                          fetched_at=it.get("fetched_at", ""), media=it.get("media", ""))
        assert fs.source_id == a["source_id"], f"로컬 사본 id 불일치: {fs.source_id} != {a['source_id']}"
    print(json.dumps({"articles": len(result["articles"]), "shortfalls": result["shortfalls"], **result["meta"]},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
