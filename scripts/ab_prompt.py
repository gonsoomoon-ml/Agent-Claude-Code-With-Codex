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

usage: uv run python scripts/ab_prompt.py [N] [REPS] [arm,arm]   # 기본: 6기사 × 3반복 × 전체 팔
      예: ab_prompt.py 6 3 v3,v3.1   # 6기사 × 3반복, v3·v3.1 만
"""
from __future__ import annotations

import json
import re
import statistics
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
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
# `claude -p` 는 각자 독립 프로세스(clean dir·자체 stdin)라 동시 실행이 안전하다 — 공유 상태 0.
# 대가: 지연이 부풀려진다(프로덕션은 순차) → 타임아웃 판정에 쓰면 안 된다.
_CONCURRENCY = 8
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


def _current_system() -> str:
    """현행 계약 — 프로덕션 사실층과 동일 조립(= 지금 체크아웃된 버전)."""
    from briefing.core.authoring.author import build_system_prompt
    from briefing.core.lenses import resolve_lens
    from briefing.core.pipeline import _FACT_USER

    return build_system_prompt(
        lens_guidance=resolve_lens(_FACT_USER.lens).guidance, skill_md=_FACT_USER.skill_md
    )


# ── 과거 버전 재현 ─────────────────────────────────────────────────────────────
# 현행(체크아웃) = v3.1 로 확정(2026-07-18: v3.2 조건 규칙은 블라인드 A/B 에서 효과 없어 revert).
# v3(예산 없음)만 재현 대상. md 는 **git 원본에서 직접** 가져온다 — 손 surgery 는 재구성 버그를 두 번
# 냈다(그중 하나는 git-verify 로 잡음). 유일한 재구성은 계약 summary 줄(Python 리터럴이라 md 밖).
_REPO = Path(__file__).resolve().parent.parent
_MD_PATH = "src/briefing/core/prompts/author_system.md"
_V3_COMMIT = "f08b741"   # represent-v3 (예산 없음)
# v3 시절 계약 summary 줄(예산 조항 없음 = "목표 길이는 없다").
_V3_SUMMARY_LINE = (
    "summary: 한국어 산문 한 문단(불릿·번호·줄바꿈 금지). 첫 문장 = 이 기사에서 새로 일어난 단 하나의 사실. "
    "도입부만 옮기지 말고 본문 전체에서 고른다. 기사의 결론·논조를 바꾸는 반론·단서가 있으면 한 절이라도 포함. "
    "원문의 귀속(누가 주장했나)과 유보 표현을 유지. 목표 길이는 없다 — 담을 사실이 분량을 정한다. "
    "'왜 중요한가'는 여기 쓰지 마라.\n"
)


def _git_md(ref: str) -> str:
    """git 원본 author_system.md — **손 surgery 대신 git 에서 직접**(재구성 버그 원천 차단)."""
    import subprocess
    return subprocess.run(["git", "show", f"{ref}:{_MD_PATH}"],
                          capture_output=True, text=True, cwd=_REPO, check=True).stdout.strip()


def _v3_system() -> str:
    """v3 재현 = git f08b741 md + 현행(v3.1) lens·계약, 단 summary 줄만 예산 없는 v3 판으로 교체."""
    cur = _current_system()
    out = _git_md(_V3_COMMIT) + cur[cur.find("\n\n## 요약 관점(lens)"):]  # v3 md + 현행 lens/계약
    k = out.find("summary: 한국어 산문 한 문단")
    end = out.find("\nwhy_it_matters:", k)
    if k < 0 or end < 0:
        raise SystemExit("v3 조립 실패: summary 줄을 못 찾음")
    return out[:k] + _V3_SUMMARY_LINE.rstrip("\n") + out[end:]


def _arm_user(fs: FrozenSource, today: str) -> str:
    """v3·v3.1 은 user turn 동일(차이는 전부 system 에 있다)."""
    return build_user_prompt(fs, today=today)


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


def _run_one(job: tuple[int, FrozenSource, str, str, object, int], settings) -> dict:
    """작업 1건 = (기사, 팔, 반복) → 지표. 예외는 값으로 돌려준다(스레드 밖에서 집계)."""
    idx, fs, arm, system, user_fn, rep = job
    t0 = time.monotonic()
    try:
        card = _parse_card_json(_run_author(system, user_fn(fs, "2026-07-17"), settings))
    except Exception as err:  # noqa: BLE001 — 실패도 데이터(타임아웃율은 배포 판단 지표다)
        return {"idx": idx, "arm": arm, "rep": rep, "error": f"{type(err).__name__}",
                "secs": round(time.monotonic() - t0)}
    summ = str(card.get("summary", ""))
    claims = card.get("claims", [])
    sd, na = _depth(fs.text, summ)
    cd, _ = _depth(fs.text, " ".join(str(c.get("text", "")) for c in claims))
    return {
        "idx": idx, "arm": arm, "rep": rep, "summary": summ, "len": len(summ),
        "sent": _sentences(summ), "depth": sd, "anchors": na, "claims_depth": cd,
        "n_claims": len(claims), "hedge": sum(h in summ for h in _HEDGE),
        "filler": sum(f in summ for f in _FILLER), "secs": round(time.monotonic() - t0),
    }


def _spread(vals: list[float]) -> str:
    """팔 *내부* 분산 — 이게 팔 간 차이보다 크면 그 비교는 무의미하다(실측: v2 가 같은 기사에 343↔984자)."""
    return f"{min(vals):.2f}~{max(vals):.2f}" if vals else "—"


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    reps = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    want = sys.argv[3].split(",") if len(sys.argv) > 3 else None
    settings = load_settings()

    # 팔 = (system, user_fn) **쌍**. v3·v3.1 은 user turn 동일(차이는 전부 system).
    # 현행 = v3.1 확정. v3 = 예산 없음(길지만 충실도 최고 — 지난 라운드 fidelity 6/6, 길이 벽).
    # (v3.2 조건 규칙은 블라인드 A/B 에서 효과 없어 revert됨 — 필요시 그 커밋으로 재현.)
    all_arms = {
        "v3": (_v3_system(), _arm_user),
        "v3.1": (_current_system(), _arm_user),   # 현행 확정
    }
    arms = {k: v for k, v in all_arms.items() if want is None or k in want}
    if not arms:
        raise SystemExit(f"알 수 없는 팔: {want} — 가능: {list(all_arms)}")
    for a, b in [(x, y) for x in arms for y in arms if x < y]:
        if arms[a][0] == arms[b][0]:
            raise SystemExit(f"팔 {a}·{b} 의 system 프롬프트가 동일 — A/B 무효")
    # ★ 격리 검증(돌리기 전) — 각 팔이 자기 계약 토큰만 갖는지. 이 검사가 지난 라운드에서
    #   'md 만 되돌리고 계약엔 남은' 오염을 즉시 잡았다. md·계약 양쪽을 동시에 커버한다.
    _inv = {  # 토큰 → 있어야 하는가
        "v3":   {"3~5문장": False, "위치가 아니라 사실의 무게": True},
        "v3.1": {"3~5문장": True,  "위치가 아니라 사실의 무게": True},
    }
    for name, (sysmsg, _u) in arms.items():
        for tok, want_ in _inv.get(name, {}).items():
            if (tok in sysmsg) != want_:
                raise SystemExit(f"{name} 격리 검증 실패: '{tok}' 존재={tok in sysmsg} 기대={want_}")

    # ★ 측정용 타임아웃 상향 — 프로덕션 한도(240s)로 두면 느린 팔의 표본이 **사라져** 품질을 못 잰다.
    #   대신 실측 초를 기록해 "프로덕션이면 몇 건이 죽었나"를 사후 집계한다.
    import briefing.core.authoring.author as _author
    prod_timeout = _author._AUTHOR_TIMEOUT_S
    _author._AUTHOR_TIMEOUT_S = 600

    say(f"표본 {n}건 × 팔 {len(arms)} × 반복 {reps} = {n * len(arms) * reps}회 · "
        f"동시 {_CONCURRENCY} · author={settings.author_model_id}")
    say("팔: " + " · ".join(f"{k}(system {len(v[0])}자)" for k, v in arms.items()))
    say(f"⚠ 지연은 동시 실행이라 **부풀려진다** — 프로덕션은 카드를 순차 처리한다(pipeline.py). "
        f"타임아웃 판정은 순차 실측으로 따로 봐야 한다(참고: 프로덕션 한도 {prod_timeout}s).\n")

    say("표본 선정 중(원장·동결본 조회)…")
    sample = _sample(n)
    for i, (fs, sd, cd) in enumerate(sample):
        say(f"  [{i}] {fs.title[:56]} ({len(fs.text)}자) — 프로덕션 최심 {sd:.2f} vs claims {cd:.2f}")

    jobs = [(i, fs, arm, sysmsg, ufn, rep)
            for i, (fs, _, _) in enumerate(sample)
            for arm, (sysmsg, ufn) in arms.items()
            for rep in range(reps)]
    say(f"\n{len(jobs)}회 호출 시작…\n")

    path = _SCRATCH / "ab_result.json"
    results: list[dict] = []
    lock = threading.Lock()
    with ThreadPoolExecutor(max_workers=_CONCURRENCY) as ex:
        futs = {ex.submit(_run_one, j, settings): j for j in jobs}
        for done, f in enumerate(as_completed(futs), 1):
            r = f.result()
            with lock:   # 즉시 저장 — 중단돼도 여기까지는 남는다
                results.append(r)
                path.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
            tag = (f"실패 {r['error']}" if "error" in r else
                   f"{r['len']:>4}자 {r['sent']:>2}문장 최심 {r['depth'] if r['depth'] is None else round(r['depth'], 2)}")
            say(f"  [{done:>2}/{len(jobs)}] 기사{r['idx']} {r['arm']:<5} #{r['rep']} · {tag} · {r['secs']}s")

    say("\n" + "=" * 84 + "\n종합 (median · 팔 내부 분산 포함)\n" + "=" * 84)
    for arm in arms:
        rs = [r for r in results if r["arm"] == arm]
        ok = [r for r in rs if "error" not in r]
        if not ok:
            say(f"\n{arm}: 전부 실패 ({len(rs)}건)")
            continue
        deep = [r["depth"] for r in ok if r["depth"] is not None]
        lens = [r["len"] for r in ok]
        secs = [r["secs"] for r in ok]
        slow = sum(1 for s in secs if s > prod_timeout)
        say(f"\n{arm}  (성공 {len(ok)}/{len(rs)})")
        say(f"  요약 최심   : median {statistics.median(deep):.3f}   ← 높을수록 원문 전체를 대표")
        say(f"  길이        : median {statistics.median(lens):.0f}자  (min {min(lens)} / max {max(lens)})")
        say(f"  문장        : median {statistics.median([r['sent'] for r in ok]):.0f}")
        say(f"  헤지 보존   : {sum(1 for r in ok if r['hedge'] > 0)}/{len(ok)}")
        say(f"  filler      : {sum(r['filler'] for r in ok)}건")
        say(f"  {prod_timeout}s 초과  : {slow}/{len(ok)}  ← 프로덕션이면 카드 유실(동시 실행이라 과대추정)")
        # 같은 기사·같은 팔의 반복 간 흔들림 = 노이즈 바닥. 팔 간 차이가 이보다 작으면 판정 불가.
        jit_d = [max(v) - min(v) for v in
                 ([r["depth"] for r in ok if r["idx"] == i and r["depth"] is not None]
                  for i in {r["idx"] for r in ok}) if len(v) > 1]
        jit_l = [max(v) - min(v) for v in
                 ([r["len"] for r in ok if r["idx"] == i] for i in {r["idx"] for r in ok}) if len(v) > 1]
        if jit_d:
            say(f"  ▸ 노이즈 바닥(같은 기사 반복 간): 최심 폭 median {statistics.median(jit_d):.2f} "
                f"({_spread(jit_d)}) · 길이 폭 median {statistics.median(jit_l):.0f}자")
    say(f"\n전문 저장: {path}")


if __name__ == "__main__":
    main()
