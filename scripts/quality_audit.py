#!/usr/bin/env python
"""quality_audit — 운영 요약 품질 정기 지표(M1, 2026-10-18). **DDB 읽기만** · 모델 호출 없음($0) · 메일·파이프라인 무관.

왜: 요약 품질 공통 기준 점검(2026-10-17, work_note 01-research/criteria-application-audit.md)은 scratchpad 의
일회성 스크립트로 했다. 그 뒤 고친 것(F1·F2·F4·N5)과 바꿀 것(U8 ② 요약 모델·S5 이름 규칙)이 실제로 나아졌는지 보려면
같은 정의로 다시 재야 한다 → 저장소 스크립트로 옮겨 날짜·버전별로 나란히 본다.

대상: card-cache 의 **사실층 카드 전부**(PUBLISH + QUARANTINE — 요약 AI 가 만든 결과물의 품질을 잰다).
해석층 항목은 사실층 verdicts 를 복제하므로 뺀다. card-cache 는 30일 TTL 이라 오래된 기준선은 사라진다
→ `--json` 스냅숏(카드별 행 포함)으로 남겨 둔다.

지표(카드 1장 단위 — work-list M1 의 다섯 가지):
- 150자     — 150자(·180자) 넘는 문장이 있는 카드. 문장 나누기는 10-17 점검과 같은 규칙(46% 기준선과 같은 자).
- 이름 표기 — S3 transliterated_name(영문 이름이 확실한 회사·모델을 한글 음역). 원문 언어별로 따로 센다(D4·S5).
- 수치 커버 — S3 summary_number_not_in_claims(요약의 숫자가 어떤 claim 에도 없음 = 검증을 안 거친 숫자).
- 잘림      — 원문 길이 ≥ TRUNCATED_MIN_CHARS(author 의 절단 경고와 같은 조건). 원문이 없으면 모름.
- 격리 사유 — ⚠(QUARANTINE) 카드의 막힌 claim 판정 출처(model): deterministic=숫자 검사 · codex=검증 AI(함의)
              · codex-error=검증 오류. ★ v57(F2) 부터 'deterministic' 으로 남은 BLOCKED 는 숫자 검사와 codex 2차
              판정이 **둘 다** 막은 것이다(그 전엔 숫자 검사 단독). codex 2차 판정이 풀어 준 claim
              (deterministic→codex VERIFIED)도 센다.
(+ S3 나머지 — why 새 숫자·이름이 claim 에 없음·한정어 빠짐·인용 불일치 — 참고 표.)

묶음: `--by day`(카드 생성일, 한국 시각 — 05:00 발송 카드가 발송일에 묶인다) | `--by version`(캐시 키를
(요약 모델, 지시 버전) 후보로 다시 계산해 맞춘다 — 키 = sha256(source_id|모델|지시 버전)).
생성 시각 = ttl − 30일(put 할 때 ttl = 지금 + 30일).

usage: uv run python scripts/quality_audit.py [--by day|version] [--since YYYY-MM-DD] [--until YYYY-MM-DD]
                                              [--json PATH]
사전: AWS 자격(읽기). 테이블·리전은 load_settings(.env) 값.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from briefing.core.authoring.author import PROMPT_VERSION
from briefing.core.quality_checks import _is_korean, shadow_checks
from briefing.core.retrieval.sources import TRUNCATED_MIN_CHARS
from briefing.core.stores.cache import _deserialize, fact_card_key
from briefing.core.stores.dynamo import _CACHE_TTL_DAYS

KST = timezone(timedelta(hours=9))
# 10-17 점검과 같은 문장 나누기 — 바꾸면 150자 비율의 기준선(46%)과 다른 자가 된다.
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")
LONG, VERY_LONG = 150, 180
# 버전 복원 후보 — 운영에 쓴 적 있거나 쓸 예정인 값. .env 의 현재 요약 모델은 main 이 덧붙인다.
KNOWN_MODELS = ("global.anthropic.claude-sonnet-5", "global.anthropic.claude-sonnet-5-5",
                "global.anthropic.claude-opus-5-5", "global.anthropic.claude-sonnet-4-6")
KNOWN_PROMPT_VERSIONS = ("represent-v3.3", "represent-v3.4", "represent-v3.4.1", "represent-v3.4.2")
UNKNOWN = "미상"
NO_BLOCK = "막힘 없음"   # 막힌 claim 없이 격리된 카드(F4 이전 규칙의 옛 카드)
_PROVENANCE_KO = {"deterministic": "숫자 검사", "codex": "검증 AI", "codex-error": "검증 오류", NO_BLOCK: NO_BLOCK}


# ── 카드 1장 지표 ─────────────────────────────────────────────────────────────

def sentences(summary: str) -> list[str]:
    return [s for s in _SENT_SPLIT.split((summary or "").strip()) if s]


def card_row(gated, source_text: str | None) -> dict:
    """사실층 카드 1장(GatedCard) + 원문(없으면 None) → 지표 행. 순수 함수."""
    sents = sentences(gated.card.summary)
    blocked, demoted = Counter(), Counter()
    released = 0
    for v in gated.verdicts:
        if v.verdict == "BLOCKED":
            blocked[v.model or UNKNOWN] += 1
        elif v.verdict == "DEMOTED":
            demoted[v.model or UNKNOWN] += 1
        elif v.verdict == "VERIFIED" and v.model == "deterministic→codex":
            released += 1
    has_src = source_text is not None
    return {
        "source_id": gated.card.source_id,
        "decision": gated.decision,
        "claims": len(gated.card.claims),
        "sentences": len(sents),
        "over150": any(len(s) > LONG for s in sents),
        "over180": any(len(s) > VERY_LONG for s in sents),
        "lang": ("ko" if _is_korean(source_text) else "en") if has_src else None,
        "truncated": len(source_text) >= TRUNCATED_MIN_CHARS if has_src else None,
        # 원문이 없으면 원문이 필요한 검사(한정어·인용)는 못 걸린다 — 그래서 그 분모에서 뺀다(summarize).
        "checks": sorted({f.check for f in shadow_checks(gated.card, source_text or "")}),
        "blocked": dict(blocked),
        "demoted": dict(demoted),
        "released": released,
    }


# ── 버전 복원 · 생성 시각 ─────────────────────────────────────────────────────

def candidates(extra_models=(), extra_versions=()) -> list[tuple[str, str]]:
    models = dict.fromkeys((*KNOWN_MODELS, *extra_models))
    versions = dict.fromkeys((*KNOWN_PROMPT_VERSIONS, PROMPT_VERSION, *extra_versions))
    return [(m, v) for m in models for v in versions]


def version_label(model_id: str, prompt_version: str) -> str:
    return f"{model_id.rsplit('.', 1)[-1].removeprefix('claude-')} · {prompt_version.removeprefix('represent-')}"


def version_of(cache_key: str, source_id: str, cands) -> str:
    for m, v in cands:
        if fact_card_key(source_id, m, v) == cache_key:
            return version_label(m, v)
    return UNKNOWN


def born_at(ttl: int) -> datetime:
    return datetime.fromtimestamp(int(ttl) - _CACHE_TTL_DAYS * 86400, timezone.utc)


# ── 행 만들기 · 고르기 · 묶기 · 집계 ──────────────────────────────────────────

def build_rows(items, sources: dict[str, str], cands) -> list[dict]:
    """(cache_key, ttl, GatedCard) 목록 + {source_id: 원문} → 카드별 행(생성 시각·한국 날짜·버전 포함)."""
    rows = []
    for key, ttl, gated in items:
        sid = gated.card.source_id
        born = born_at(ttl)
        rows.append({**card_row(gated, sources.get(sid)), "born": born.isoformat(),
                     "day": born.astimezone(KST).date().isoformat(), "version": version_of(key, sid, cands)})
    return sorted(rows, key=lambda r: r["born"])


def select(rows, since: str | None = None, until: str | None = None) -> list[dict]:
    """한국 날짜(YYYY-MM-DD) 기준, 양끝 포함."""
    return [r for r in rows if (not since or r["day"] >= since) and (not until or r["day"] <= until)]


def group(rows, by: str) -> dict[str, list[dict]]:
    """day = 날짜순, version = 그 버전 카드가 처음 생긴 순."""
    out: dict[str, list[dict]] = {}
    for r in sorted(rows, key=lambda r: r["day"] if by == "day" else r["born"]):
        out.setdefault(r[by], []).append(r)
    return out


def summarize(rows) -> dict:
    """행 묶음 → 건수(비율은 표에서 분모와 함께 계산 — JSON 에는 건수를 남긴다)."""
    def has(check, rs):
        return sum(check in r["checks"] for r in rs)

    with_src = [r for r in rows if r["lang"] is not None]
    en = [r for r in with_src if r["lang"] == "en"]
    ko = [r for r in with_src if r["lang"] == "ko"]
    reasons, blocked = Counter(), Counter()
    for r in rows:
        blocked.update(r["blocked"])
        if r["decision"] == "QUARANTINE":
            reasons.update(r["blocked"].keys() or [NO_BLOCK])
    return {
        "n": len(rows),
        "publish": sum(r["decision"] == "PUBLISH" for r in rows),
        "quarantine": sum(r["decision"] == "QUARANTINE" for r in rows),
        "over150": sum(r["over150"] for r in rows),
        "over180": sum(r["over180"] for r in rows),
        "n_with_source": len(with_src), "n_en": len(en), "n_ko": len(ko),
        "translit_en": has("transliterated_name", en),
        "translit_ko": has("transliterated_name", ko),
        "num_uncovered": has("summary_number_not_in_claims", rows),
        "truncated": sum(bool(r["truncated"]) for r in with_src),
        "why_new_number": has("why_new_number", rows),
        "name_uncovered": has("summary_name_not_in_claims", rows),
        "qualifier_dropped": has("qualifier_dropped", with_src),
        "quote_not_verbatim": has("quote_not_verbatim", ko),
        "quarantine_reasons": dict(reasons),
        "blocked_claims": dict(blocked),
        "released_claims": sum(r["released"] for r in rows),
        "released_cards": sum(r["released"] > 0 for r in rows),
    }


# ── 출력 ─────────────────────────────────────────────────────────────────────

def _pct(k: int, d: int) -> str:
    return "—" if not d else f"{round(100 * k / d)}% ({k})"


def _table(header: list[str], body: list[list[str]]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(row) + " |" for row in body]
    return "\n".join(lines)


def format_report(groups: dict[str, list[dict]]) -> str:
    """묶음별 Markdown 표 3개(M1 지표 · 격리 사유 · S3 나머지) — 마지막 줄은 전체."""
    stats = {**{k: summarize(v) for k, v in groups.items()}, "전체": summarize([r for v in groups.values() for r in v])}
    reasons = ("deterministic", "codex", "codex-error", NO_BLOCK)
    t1 = _table(
        ["구간", "카드", "⚠ 격리", "150자 넘는 문장", "180자 넘는 문장", "이름 한글(영어 원문)", "이름 한글(한국어 원문)",
         "요약 숫자가 claim 에 없음", "잘린 원문"],
        [[g, str(s["n"]), _pct(s["quarantine"], s["n"]), _pct(s["over150"], s["n"]), _pct(s["over180"], s["n"]),
          _pct(s["translit_en"], s["n_en"]), _pct(s["translit_ko"], s["n_ko"]), _pct(s["num_uncovered"], s["n"]),
          _pct(s["truncated"], s["n_with_source"])] for g, s in stats.items()])
    t2 = _table(
        ["구간", "⚠ 카드", *(f"사유: {_PROVENANCE_KO[k]}" for k in reasons), "막힌 claim(숫자/AI/오류)",
         "2차 판정이 풀어 준 claim"],
        [[g, str(s["quarantine"]), *(str(s["quarantine_reasons"].get(k, 0)) for k in reasons),
          "/".join(str(s["blocked_claims"].get(k, 0)) for k in reasons[:3]),
          f"{s['released_claims']} (카드 {s['released_cards']})"] for g, s in stats.items()])
    t3 = _table(
        ["구간", "why 새 숫자", "이름이 claim 에 없음", "한정어 빠짐", "인용 불일치(한국어 원문)"],
        [[g, _pct(s["why_new_number"], s["n"]), _pct(s["name_uncovered"], s["n"]),
          _pct(s["qualifier_dropped"], s["n_with_source"]), _pct(s["quote_not_verbatim"], s["n_ko"])]
         for g, s in stats.items()])
    return (f"### M1 지표\n\n{t1}\n\n### 격리 사유 (카드 단위 — 한 카드에 출처가 둘이면 둘 다 센다)\n\n{t2}\n\n"
            f"### S3 나머지 검사 (참고)\n\n{t3}\n")


# ── DDB 읽기 ─────────────────────────────────────────────────────────────────

def load_fact_cards(table) -> list[tuple[str, int, object]]:
    """card-cache 전체 scan → [(cache_key, ttl, GatedCard)] — 사실층만(해석층은 based_on 이 있다).

    카드 형식이 바뀌어 옛 항목을 못 읽으면 건너뛰되 몇 건인지 stderr 에 남긴다(조용히 분모가 줄지 않게)."""
    out, start, unreadable = [], None, 0
    while True:
        kw = {"ProjectionExpression": "cache_key, #l, card_json", "ExpressionAttributeNames": {"#l": "ttl"}}
        if start:
            kw["ExclusiveStartKey"] = start
        resp = table.scan(**kw)
        for it in resp["Items"]:
            try:
                gated = _deserialize(json.loads(it["card_json"]))
            except (KeyError, TypeError, ValueError):
                unreadable += 1
                continue
            if not gated.card.based_on:
                out.append((it["cache_key"], int(it["ttl"]), gated))
        start = resp.get("LastEvaluatedKey")
        if not start:
            if unreadable:
                print(f"읽지 못한 card-cache 항목 {unreadable}건 — 집계에서 빠짐", file=sys.stderr)
            return out


def load_sources(store, source_ids) -> dict[str, str]:
    """source-store 원문 — 없는 id 는 빠진다(그 카드의 잘림·언어는 '모름')."""
    out = {}
    for sid in dict.fromkeys(source_ids):
        try:
            out[sid] = store.get_source(sid).text
        except KeyError:
            continue
    return out


def main(argv=None) -> None:
    import boto3

    from briefing.core.config import load_settings
    from briefing.core.stores.dynamo import DynamoSourceStore

    ap = argparse.ArgumentParser(description="운영 요약 품질 정기 지표(M1) — DDB 읽기만")
    ap.add_argument("--by", choices=("day", "version"), default="day")
    ap.add_argument("--since", help="한국 날짜 YYYY-MM-DD(포함)")
    ap.add_argument("--until", help="한국 날짜 YYYY-MM-DD(포함)")
    ap.add_argument("--json", type=Path, help="스냅숏 저장 경로(묶음 건수 + 카드별 행)")
    args = ap.parse_args(argv)

    settings = load_settings()
    items = load_fact_cards(boto3.resource("dynamodb", region_name=settings.region).Table(settings.cache_table))
    sources = load_sources(DynamoSourceStore(settings.source_table, region=settings.region),
                           [g.card.source_id for _, _, g in items])
    rows = select(build_rows(items, sources, candidates(extra_models=(settings.author_model_id,))),
                  args.since, args.until)
    groups = group(rows, args.by)
    print(format_report(groups))
    if args.json:
        snap = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "by": args.by, "since": args.since, "until": args.until,
                "groups": {k: summarize(v) for k, v in groups.items()}, "total": summarize(rows), "cards": rows}
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(snap, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"스냅숏: {args.json}", file=sys.stderr)


if __name__ == "__main__":
    main()
