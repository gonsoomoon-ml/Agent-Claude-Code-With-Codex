#!/usr/bin/env python
"""ab_prompt — 사실층 요약 프롬프트 오프라인 A/B (v2 baseline vs v3 represent).

**프로덕션 미접촉:** 동결본은 source-store 에서 *읽기만* 하고, 결과는 캐시·원장·발송 어디에도 안 쓴다.
author(`claude -p`) 만 실제로 호출한다 — certifier 는 안 돌린다(요약 비교가 목적).

측정 = 요약이 원문을 얼마나 대표하는가:
  · 앵커 도달 최심(anchor depth) — 요약이 인용한 사실이 원문 어디까지 갔나(0=서두, 1=끝).
    같은 카드 claims 의 최심과 비교해야 의미가 있다(= author 가 읽은 범위의 상한).
  · 헤지(유보) 보존 — 원문의 반론·단서를 요약이 담았나.
  · filler — "주목받고 있다" 류 비정보 구문.
  · 길이·문장 수 — 부수 관측치(목표 아님. corr(길이,커버리지)=+0.47 이라 조이면 안 됨).

usage: uv run python scripts/ab_prompt.py [N]      # N = 표본 카드 수(기본 6)
"""
from __future__ import annotations

import json
import re
import statistics
import sys
import time
from pathlib import Path

import boto3

from briefing.core.authoring.author import (
    _parse_card_json,
    _run_author,
    build_user_prompt,
)
from briefing.core.config import load_settings
from briefing.core.stores.source_store import FrozenSource

REGION = "us-east-1"
ADMIN = "445814b8-5001-70a6-84a6-6c010ac347ba"
_SCRATCH = Path("/tmp/claude-1000/-home-ubuntu-Agent-Claude-Code-With-Codex/"
                "a80ab529-104b-4976-8e30-7d1cb2390975/scratchpad")

# 앵커 = 원문에 등장하는 숫자/라틴 고유명사. 한자어 개념은 안 잡히므로 **절대 수준은 과소추정**이지만,
# 두 팔이 같은 앵커 종류를 쓰므로 **비교는 유효**하다.
_TOK = re.compile(r"[A-Z][A-Za-z0-9.\-]{2,}|\d[\d,.]*")
_HEDGE = ("일 수 있다", "수 있다", "가능성", "확인되지 않", "단정", "밝히지 않", "않았다",
          "라고 밝혔다", "라고 주장", "라고 전했다", "지적", "비판", "우려", "다만", "그러나", "반면")
_FILLER = ("주목받고 있다", "관심이 모이고 있다", "귀추가 주목", "파장이 예상", "이 기사는",
           "에 대해 설명한다", "을 소개한다", "를 다룬다")


def say(*a: object) -> None:
    """즉시 출력 — 파이프로 넘기면 stdout 이 블록 버퍼링돼 진행이 안 보이고, 중단 시 통째로 유실된다."""
    print(*a, flush=True)


def _anchors(text: str) -> set[str]:
    return {m.group() for m in _TOK.finditer(text)}


def _depth(src: str, text: str) -> tuple[float | None, int]:
    """text 가 인용한 앵커의 원문 내 최심 상대 위치 + 앵커 수."""
    pos = [src.find(a) / max(1, len(src)) for a in _anchors(text) if src.find(a) >= 0]
    return (max(pos) if pos else None, len(pos))


def _sentences(t: str) -> int:
    return len([s for s in re.split(r"(?<=[.?!다])\s+", t.strip()) if len(s) > 5])


# v2 시절의 _OUTPUT_CONTRACT(f08b741 이전) — summary·why 계약 줄이 없던 버전.
_V2_OUTPUT_CONTRACT = (
    "## 출력 형식 (JSON only)\n"
    "다음 JSON object *하나*만 출력하라(코드펜스·여는 설명 금지):\n"
    '{"summary": "...", "why_it_matters": "...", '
    '"claims": [{"id": "C1", "text": "...", "claim_type": "arithmetic|entailment", '
    '"importance": "core|supporting"}]}\n'
    "제목(headline)은 만들지 마라 — 카드 제목은 기사 원제목을 그대로 쓴다(사실층 앵커, 재프레이밍 금지).\n"
    "claims 는 원자적(독립 검증 단위). 숫자/날짜/% 포함이면 claim_type=arithmetic, 그 외 entailment. 애매하면 arithmetic.\n"
    "importance: summary 또는 why_it_matters 를 직접 뒷받침하면 core, 그 외 supporting."
)


def _v2_system() -> str:
    """v2 baseline system prompt — git 이력의 원본 3조각으로 재조립(당시 build_system_prompt 와 동형)."""
    base = (_SCRATCH / "v2_author_system.md").read_text(encoding="utf-8")
    lens = '균형 잡힌 일반 독자 관점. 핵심 사실과 "왜 중요한가"를 간결히.'
    return "\n\n".join([base.strip(), "## 요약 관점(lens)\n" + lens, _V2_OUTPUT_CONTRACT])


def _v2_user(fs: FrozenSource, today: str) -> str:
    """v2 시절의 user turn — **절단 플래그도, '본문 전체에서 고른다'도 없다.**

    ★ 이걸 빼먹고 현행 build_user_prompt 를 두 팔에 같이 쓰면 baseline 이 v3 의 핵심 지시를
    받아버려 A/B 가 무효가 된다(실제로 첫 실행에서 그렇게 오염됐다 — v2 팔이 최심 0.93).
    """
    return (
        f"오늘 날짜: {today} (상대 날짜는 이 기준; 원문에 없는 날짜 생성 금지).\n\n"
        f"다음 동결 원문을 요약하고 원자적 claims 를 추출하라:\n\n{fs.text}"
    )


def _v3_system() -> str:
    """현행(v3) — 프로덕션 사실층과 동일 조립."""
    from briefing.core.authoring.author import build_system_prompt
    from briefing.core.lenses import resolve_lens
    from briefing.core.pipeline import _FACT_USER

    return build_system_prompt(
        lens_guidance=resolve_lens(_FACT_USER.lens).guidance, skill_md=_FACT_USER.skill_md
    )


def _sample(n: int) -> list[tuple[FrozenSource, float, float]]:
    """실제 발행 카드 중 **lead bias 가 심했던 것 우선** — 개선 여부를 볼 표본."""
    ddb = boto3.client("dynamodb", region_name=REGION)
    items, kw = [], {}
    while True:
        r = ddb.query(TableName="briefing-ledger", KeyConditionExpression="user_id = :u",
                      ExpressionAttributeValues={":u": {"S": ADMIN}}, **kw)
        items += [{k: list(v.values())[0] for k, v in it.items()} for it in r["Items"]]
        if "LastEvaluatedKey" not in r:
            break
        kw = {"ExclusiveStartKey": r["LastEvaluatedKey"]}

    rows, seen = [], set()
    for it in items:
        if it["source_id"] in seen:
            continue
        s = ddb.get_item(TableName="briefing-source-store",
                         Key={"source_id": {"S": it["source_id"]}}).get("Item")
        c = ddb.get_item(TableName="briefing-card-cache",
                         Key={"cache_key": {"S": it["card_key"]}}).get("Item")
        if not s or not c or "text" not in s:
            continue
        src = s["text"]["S"]
        if len(src) < 1500:            # 대표할 본문이 있어야 의미
            continue
        seen.add(it["source_id"])
        card = json.loads(c["card_json"]["S"])["card"]
        sd, _ = _depth(src, card.get("summary", ""))
        cd, _ = _depth(src, " ".join(cl["text"] for cl in card.get("claims", [])))
        if sd is None or cd is None:
            continue
        rows.append((FrozenSource(it["source_id"], s.get("url", {}).get("S", ""),
                                  s.get("title", {}).get("S", ""), src, ""), sd, cd))
    rows.sort(key=lambda r: r[1] - r[2])   # 요약이 claims 대비 가장 얕은 것부터
    return rows[:n]


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    settings = load_settings()
    # 팔 = (system, user_fn) **쌍**. user turn 도 팔마다 달라야 한다 — v3 의 '본문 전체에서 고른다'가
    # 거기 있으므로, 공용 build_user_prompt 를 쓰면 baseline 이 v3 지시를 받아 A/B 가 무효가 된다.
    arms = {
        "v2(baseline)": (_v2_system(), _v2_user),
        "v3(represent)": (_v3_system(), lambda fs, today: build_user_prompt(fs, today=today)),
    }
    say(f"표본 {n}건 · author={settings.author_model_id}")
    say(f"프롬프트 길이(system): v2={len(arms['v2(baseline)'][0])}자 · v3={len(arms['v3(represent)'][0])}자\n")

    path = _SCRATCH / "ab_result.json"
    out: list[dict] = []
    say("표본 선정 중(원장·동결본 조회)…")
    sample = _sample(n)
    for i, (fs, old_sd, old_cd) in enumerate(sample, 1):
        say(f"[{i}/{len(sample)}] {fs.title[:58]}  (원문 {len(fs.text)}자)")
        say(f"      프로덕션 실적: 요약 최심 {old_sd:.2f} vs claims 최심 {old_cd:.2f}")
        rec = {"title": fs.title, "src_len": len(fs.text), "prod_sd": old_sd, "prod_cd": old_cd}
        for arm, (system, user_fn) in arms.items():
            t0 = time.monotonic()
            try:
                text = _run_author(system, user_fn(fs, "2026-07-17"), settings)
                card = _parse_card_json(text)
            except Exception as err:            # 한 팔 실패가 전체를 죽이면 안 됨
                say(f"      {arm}: 실패 {type(err).__name__}: {err}")
                continue
            summ = str(card.get("summary", ""))
            claims = card.get("claims", [])
            sd, na = _depth(fs.text, summ)
            cd, _ = _depth(fs.text, " ".join(str(c.get("text", "")) for c in claims))
            rec[arm] = {
                "summary": summ, "len": len(summ), "sent": _sentences(summ),
                "depth": sd, "anchors": na, "claims_depth": cd, "n_claims": len(claims),
                "hedge": sum(h in summ for h in _HEDGE),
                "filler": sum(f in summ for f in _FILLER),
                "secs": round(time.monotonic() - t0),
            }
            say(f"      {arm}: {len(summ):>4}자 {_sentences(summ)}문장 · 최심 "
                f"{sd if sd is None else round(sd, 2)} (claims {cd if cd is None else round(cd, 2)}) "
                f"· 헤지 {rec[arm]['hedge']} · filler {rec[arm]['filler']} · {rec[arm]['secs']}s")
        out.append(rec)
        # ★ 카드마다 즉시 저장 — 중단(타임아웃·SIGTERM)돼도 여기까지는 남는다.
        path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

    say("\n" + "=" * 78 + "\n종합\n" + "=" * 78)
    for arm in arms:
        rs = [r[arm] for r in out if arm in r]
        if not rs:
            continue
        deep = [r["depth"] for r in rs if r["depth"] is not None]
        say(f"\n{arm}")
        say(f"  요약 최심 도달 : median {statistics.median(deep):.3f}  (높을수록 원문 전체를 대표)")
        say(f"  길이           : median {statistics.median([r['len'] for r in rs]):.0f}자  "
              f"({min(r['len'] for r in rs)}~{max(r['len'] for r in rs)})")
        say(f"  문장           : median {statistics.median([r['sent'] for r in rs]):.0f}")
        say(f"  헤지 보존      : {sum(1 for r in rs if r['hedge'] > 0)}/{len(rs)}장")
        say(f"  filler         : {sum(r['filler'] for r in rs)}건")
        say(f"  claims 수      : median {statistics.median([r['n_claims'] for r in rs]):.0f}")
    say(f"\n전문 저장: {path}")


if __name__ == "__main__":
    main()
