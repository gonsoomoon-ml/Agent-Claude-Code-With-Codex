"""S2 측정 — claim 이 요약의 귀속·양태·수치 한정어를 담는가(코드 지표) + claim 수·검증 결과 분포.

판정 AI 없이 Stage A 기록(records.jsonl)만 읽는다. 대조군 S1C 와 실험군 S2B(초안 B)를 나란히 본다.
지표는 **근사**다 — 두 조건에 같은 규칙을 적용해 차이의 방향을 보는 데 쓴다(절대값은 참고).

- 귀속 보존: 요약의 귀속 절('…라고 밝혔다'·'에 따르면'·'…로 추정했다' 로 끝나는 절)마다, 낱말이 가장 많이 겹치는
  claim(대응 claim)도 귀속 표지를 가지면 보존. 겹침이 너무 적으면(대응 claim 없음) 분모에서 빼고 따로 센다 — 그건
  귀속이 아니라 검증 회피 문제다. (말한 주체 낱말로 맞추는 방식은 S1C 표본 점검에서 오판이 많아 버렸다.)
- 양태 보존: 요약의 양태·단계어(예정·계획·가능·수 있·추정·전망·프리뷰·베타·시범)마다 같은 낱말을 가진 claim 이 있으면 보존.
- 수치 한정어 보존: 요약의 (한정어, 숫자) 짝('최대 72'·'30 이상')마다 같은 짝을 가진 claim 이 있으면 보존.
- 검증 결과: claim 을 표지 있음/단정으로 나눠 claim_type 별 DEMOTED·BLOCKED 비율(최종 판정 — 다시 쓰기 뒤).
- claim 수: 카드당 평균과 v3.3 범위(10–22) 밖 카드 수. 격리·다시 쓰기 수.

실행: PYTHONPATH=scripts uv run python -m upgrade_eval.s2_metrics --base S1C --arm S2B [--json PATH]
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from .common import read_jsonl
from .stats import paired_bootstrap

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")
# 귀속 표지 — 인용 어미('다고'·'라고') 뒤 보도·판단 동사(과거·현재·연결형 모두), '에 따르면', '…로 추정했다'.
# '이라고 불리는'(이름 붙이기)은 귀속이 아니라서 동사 목록에 '불리' 를 넣지 않는다.
_VERB = (r"(?:밝[혔히힌혀]|말[했하한]|전[했하한]|덧붙|본다|봤|보았|보며|보고\s*있|들[었은]|"
         r"(?:설명|주장|발표|강조|평가|보고|추정|예상|전망|언급|지적|답|경고|예측|분석|판단|보도|자평|소개)[했하한])")
ATTR = re.compile(rf"[라다]고\s*{_VERB}"                  # …라고 밝혔다
                  r"|[라다]고\s*(?:했|하며|한다|하고)"        # …다고 했다(= 말했다)
                  rf"|[라다]고\s.{{0,50}}?{_VERB}"           # …라고 MiMo 팀은 밝혔다 · …다고 팟캐스트에서 밝혔다(사이에 주어·장소)
                  r"|(?<!원문)(?<!기사)에 따르면"               # '원문에 따르면'은 말한 주체가 아니라 글 자체를 가리킨다
                  r"|(?:으로|로)\s*(?:설명|소개|묘사|규정|추정|예상|전망|추산|평가)[했하한]")
MODAL = re.compile(r"수 있|가능|예정|계획|추정|전망|프리뷰|베타|시범")
_QUAL_BEFORE = re.compile(r"(?<![가-힣])(최대|최소|약|거의|대략|평균)\s*(\d[\d,.]*)")
_QUAL_AFTER = re.compile(r"(\d[\d,.]*)\s*[^\s\d]{0,3}?\s*(이상|이하|미만|초과|이내|가량|넘게|넘는|안팎|정도|남짓|내외|가까이)")
_CLAUSE_SEP = re.compile(r",\s|(?:며|면서)\s")
_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9.\-]*[A-Za-z0-9]|\d[\d,.]*|[가-힣]{2,}")
_PARTICLE = re.compile(r"(?:으로|에서|에게|까지|부터|이며|이고|은|는|이|가|을|를|의|에|로|와|과|도|만)$")
MIN_OVERLAP = 0.25          # 귀속 절 낱말 중 이만큼은 겹쳐야 대응 claim 으로 본다
CLAIMS_RANGE = (10, 22)


def sentences(text: str) -> list[str]:
    return [s for s in _SENT_SPLIT.split((text or "").strip()) if s]


def attributed_clauses(sentence: str) -> list[str]:
    """귀속 표지로 끝나는 절들 — 표지 앞의 가장 가까운 절 경계(',' · '며 ' · '면서 ')부터 표지 끝까지."""
    out = []
    for m in ATTR.finditer(sentence):
        head = sentence[:m.start()]
        cut = max((x.end() for x in _CLAUSE_SEP.finditer(head)), default=0)
        out.append(sentence[cut:m.end()].strip())
    return out


def _tokens(text: str) -> set[str]:
    return {_PARTICLE.sub("", w) if w[0] >= "가" else w.rstrip(".,") for w in _TOKEN.findall(text)} - {""}


def _clause_matches(summary: str, claims: list[tuple[str, str]]) -> list[tuple[bool, str] | None]:
    """요약의 귀속 절마다 (보존?, 대응 claim 종류) — 대응 claim 이 없으면 None.
    대응 claim = 낱말이 가장 많이 겹치는 claim(동점이면 모두). 보존이면 귀속을 지킨 대응 claim 의 종류를 적는다."""
    out: list[tuple[bool, str] | None] = []
    claim_tokens = [(_tokens(text), text, ctype) for text, ctype in claims]
    for s in sentences(summary):
        for clause in attributed_clauses(s):
            want = _tokens(clause)
            scores = [(len(want & ct) / len(want) if want else 0.0, text, ctype) for ct, text, ctype in claim_tokens]
            best = max((x for x, _, _ in scores), default=0.0)
            if best < MIN_OVERLAP:
                out.append(None)
                continue
            tied = [(text, ctype) for x, text, ctype in scores if x == best]
            keeper = next(((text, ctype) for text, ctype in tied if ATTR.search(text)), None)
            out.append((True, keeper[1]) if keeper else (False, tied[0][1]))
    return out


def attribution(summary: str, claims: list[str]) -> tuple[int, int, int]:
    """(보존, 분모, 대응 claim 없음) — 요약의 귀속 절 단위."""
    res = _clause_matches(summary, [(c, "") for c in claims])
    matched = [r for r in res if r is not None]
    return sum(k for k, _ in matched), len(matched), len(res) - len(matched)


def attribution_by_type(summary: str, claims: list[tuple[str, str]]) -> dict[str, tuple[int, int]]:
    """대응 claim 종류별 (보존, 분모). 숫자형(arithmetic) claim 은 숫자만 코드로 검사하고 검증 AI 에 안 가서,
    그 안의 귀속은 아무도 확인하지 않는다 — 보존이 숫자형에서만 늘면 '검증된 귀속'이 늘어난 게 아니다."""
    out: dict[str, list[int]] = {}
    for r in _clause_matches(summary, claims):
        if r is None:
            continue
        kept, ctype = r
        k = out.setdefault(ctype, [0, 0])
        k[0] += kept
        k[1] += 1
    return {ct: (k, n) for ct, (k, n) in out.items()}


def laundering(summary: str, claims: list[str]) -> tuple[int, int]:
    """(세탁 후보, 귀속 claim 수) — 귀속 표지가 있는 claim 중, 낱말이 가장 많이 겹치는 요약 문장에는 귀속이 없는 것.
    리서치 위험 ②: claim 이 요약보다 더 유보·귀속되면 claim 은 통과해도 발행된 요약은 원문보다 세다."""
    sents = [(_tokens(s), s) for s in sentences(summary)]
    count = attributed = 0
    for c in claims:
        if not ATTR.search(c):
            continue
        attributed += 1
        want = _tokens(c)
        scored = [(len(want & st) / len(want) if want else 0.0, s) for st, s in sents]
        best = max((x for x, _ in scored), default=0.0)
        if best >= MIN_OVERLAP and not any(ATTR.search(s) for x, s in scored if x == best):
            count += 1
    return count, attributed


def modality(summary: str, claims: list[str]) -> tuple[int, int]:
    words = MODAL.findall(summary or "")
    return sum(any(w in c for c in claims) for w in words), len(words)


def _qual_pairs(text: str) -> list[tuple[str, str]]:
    pairs = [(q, n.replace(",", "").rstrip(".")) for q, n in _QUAL_BEFORE.findall(text or "")]
    pairs += [(q, n.replace(",", "").rstrip(".")) for n, q in _QUAL_AFTER.findall(text or "")]
    return pairs


def qualifiers(summary: str, claims: list[str]) -> tuple[int, int]:
    in_claims = {p for c in claims for p in _qual_pairs(c)}
    pairs = _qual_pairs(summary)
    return sum(p in in_claims for p in pairs), len(pairs)


def marker_group(claim_text: str) -> str:
    return "표지" if ATTR.search(claim_text) or MODAL.search(claim_text) or _qual_pairs(claim_text) else "단정"


def card_metrics(rec: dict) -> dict:
    """Stage A 기록 1건(카드가 있는 것) → 카드 지표."""
    claims = rec.get("claims") or []
    texts = [c["text"] for c in claims]
    verdict_of = {v["claim_id"]: v["verdict"] for v in rec.get("verdicts") or []}
    verdicts = Counter((c["claim_type"], marker_group(c["text"]), verdict_of.get(c["id"], "없음")) for c in claims)
    summary = rec.get("summary") or ""
    return {"arm": rec.get("arm"), "source_id": rec.get("source_id"), "rep": rec.get("rep"),
            "decision": rec.get("decision"), "revised": (rec.get("attempts") or 1) > 1, "claims": len(claims),
            "arith_claims": sum(c["claim_type"] == "arithmetic" for c in claims),
            "attribution": attribution(summary, texts),
            "attribution_by_type": attribution_by_type(summary, [(c["text"], c["claim_type"]) for c in claims]),
            "laundering": laundering(summary, texts),
            "modality": modality(summary, texts), "qualifiers": qualifiers(summary, texts), "verdicts": dict(verdicts)}


def summarize_arm(cards: list[dict]) -> dict:
    v = Counter()
    for c in cards:
        v.update(c["verdicts"])
    n_claims = sum(c["claims"] for c in cards)
    lo, hi = CLAIMS_RANGE

    def rate(verdict, ctype=None, group=None):
        sel = [(k, n) for k, n in v.items() if (ctype is None or k[0] == ctype) and (group is None or k[1] == group)]
        d = sum(n for _, n in sel)
        return (sum(n for k, n in sel if k[2] == verdict), d)

    return {
        "cards": len(cards),
        "quarantine": sum(c["decision"] == "QUARANTINE" for c in cards),
        "revised": sum(c["revised"] for c in cards),
        "claims_total": n_claims,
        "claims_mean": round(n_claims / len(cards), 2) if cards else 0.0,
        "claims_out_of_range": sum(not (lo <= c["claims"] <= hi) for c in cards),
        "attribution_kept": sum(c["attribution"][0] for c in cards),
        "attribution_total": sum(c["attribution"][1] for c in cards),
        "attribution_unmatched": sum(c["attribution"][2] for c in cards),
        "modality_kept": sum(c["modality"][0] for c in cards),
        "modality_total": sum(c["modality"][1] for c in cards),
        "qualifiers_kept": sum(c["qualifiers"][0] for c in cards),
        "qualifiers_total": sum(c["qualifiers"][1] for c in cards),
        "arith_claims": sum(c["arith_claims"] for c in cards),
        "attribution_by_type": {ct: tuple(sum(c["attribution_by_type"].get(ct, (0, 0))[i] for c in cards) for i in (0, 1))
                                for ct in ("arithmetic", "entailment")},
        "laundering": sum(c["laundering"][0] for c in cards),
        "attributed_claims": sum(c["laundering"][1] for c in cards),
        "marked_claims": sum(n for k, n in v.items() if k[1] == "표지"),
        "demoted": sum(n for k, n in v.items() if k[2] == "DEMOTED"),
        "blocked": sum(n for k, n in v.items() if k[2] == "BLOCKED"),
        "rates": {f"{verdict}|{ct or '전체'}|{g or '전체'}": rate(verdict, ct, g)
                  for verdict in ("DEMOTED", "BLOCKED") for ct in (None, "entailment", "arithmetic")
                  for g in (None, "표지", "단정")},
    }


def paired_diffs(base: dict[str, list[tuple[int, int]]], arm: dict[str, list[tuple[int, int]]]) -> dict[str, float]:
    """기사별 (보존, 분모) 목록 → 회차를 합친 비율의 차(실험군 − 대조군). 어느 쪽이든 분모가 0 인 기사는 뺀다."""
    out = {}
    for sid in sorted(set(base) & set(arm)):
        b = [sum(x) for x in zip(*base[sid])]
        a = [sum(x) for x in zip(*arm[sid])]
        if b[1] and a[1]:
            out[sid] = a[0] / a[1] - b[0] / b[1]
    return out


def _per_article(cards: list[dict], key: str) -> dict[str, list[tuple[int, int]]]:
    out: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for c in cards:
        out[c["source_id"]].append(tuple(c[key][:2]))
    return out


def _per_article_value(cards: list[dict], value) -> dict[str, list[tuple[int, int]]]:
    out: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for c in cards:
        out[c["source_id"]].append(value(c))
    return out


def compare(records: list[dict], base: str, arm: str) -> dict:
    """대조군·실험군의 카드 지표 요약 + 기사 단위 짝 비교(95% 부트스트랩)."""
    from .aggregate import _latest_runs

    latest, missing = _latest_runs([r for r in records if r.get("arm") in (base, arm)])
    cards = {k: [card_metrics(r) for r in latest if r["arm"] == k and r.get("decision") in ("PUBLISH", "QUARANTINE")]
             for k in (base, arm)}
    errors = {k: sum(r["arm"] == k and r.get("decision") == "ERROR" for r in latest) for k in (base, arm)}
    paired = {}
    for key in ("attribution", "modality", "qualifiers"):
        paired[key] = paired_bootstrap(paired_diffs(_per_article(cards[base], key), _per_article(cards[arm], key)))

    def demoted(c):
        return (sum(n for k, n in c["verdicts"].items() if k[2] == "DEMOTED"), c["claims"])

    paired["demoted"] = paired_bootstrap(paired_diffs(_per_article_value(cards[base], demoted),
                                                      _per_article_value(cards[arm], demoted)))
    claims_diff = {}
    for sid in sorted({c["source_id"] for c in cards[base]} & {c["source_id"] for c in cards[arm]}):
        def mean(k, s=sid):
            xs = [c["claims"] for c in cards[k] if c["source_id"] == s]
            return sum(xs) / len(xs)
        claims_diff[sid] = mean(arm) - mean(base)
    paired["claims"] = paired_bootstrap(claims_diff)
    return {"base": base, "arm": arm, "missing_keys": missing, "errors": errors,
            "summary": {k: summarize_arm(v) for k, v in cards.items()}, "paired": paired}


def _pct(k: int, d: int) -> str:
    return "—" if not d else f"{100 * k / d:.1f}% ({k}/{d})"


def format_report(res: dict) -> str:
    b, a = res["base"], res["arm"]
    sb, sa = res["summary"][b], res["summary"][a]
    rows = [
        ("카드(오류)", f"{sb['cards']} ({res['errors'][b]})", f"{sa['cards']} ({res['errors'][a]})"),
        ("격리 / 다시 쓰기", f"{sb['quarantine']} / {sb['revised']}", f"{sa['quarantine']} / {sa['revised']}"),
        ("claim 수(카드당 평균)", str(sb["claims_mean"]), str(sa["claims_mean"])),
        ("claim 수 10–22 밖 카드", str(sb["claims_out_of_range"]), str(sa["claims_out_of_range"])),
        ("숫자형 claim", _pct(sb["arith_claims"], sb["claims_total"]), _pct(sa["arith_claims"], sa["claims_total"])),
        ("귀속 보존", _pct(sb["attribution_kept"], sb["attribution_total"]), _pct(sa["attribution_kept"], sa["attribution_total"])),
        ("— 대응 claim 이 함의형(검증 AI 가 봄)", _pct(*sb["attribution_by_type"]["entailment"]),
         _pct(*sa["attribution_by_type"]["entailment"])),
        ("— 대응 claim 이 숫자형(숫자만 검사)", _pct(*sb["attribution_by_type"]["arithmetic"]),
         _pct(*sa["attribution_by_type"]["arithmetic"])),
        ("귀속 절의 대응 claim 없음", str(sb["attribution_unmatched"]), str(sa["attribution_unmatched"])),
        ("요약보다 귀속이 센 claim(세탁 후보)", _pct(sb["laundering"], sb["attributed_claims"]),
         _pct(sa["laundering"], sa["attributed_claims"])),
        ("양태 보존", _pct(sb["modality_kept"], sb["modality_total"]), _pct(sa["modality_kept"], sa["modality_total"])),
        ("수치 한정어 보존", _pct(sb["qualifiers_kept"], sb["qualifiers_total"]), _pct(sa["qualifiers_kept"], sa["qualifiers_total"])),
        ("표지 있는 claim", _pct(sb["marked_claims"], sb["claims_total"]), _pct(sa["marked_claims"], sa["claims_total"])),
    ]
    for key, label in (("DEMOTED|entailment|전체", "미확인(함의)"), ("DEMOTED|arithmetic|전체", "미확인(숫자)"),
                       ("BLOCKED|arithmetic|전체", "차단(숫자)"), ("DEMOTED|전체|표지", "미확인(표지 있는 claim)"),
                       ("DEMOTED|전체|단정", "미확인(단정 claim)")):
        rows.append((label, _pct(*sb["rates"][key]), _pct(*sa["rates"][key])))
    lines = [f"| 지표 | {b} | {a} |", "|---|---|---|"] + [f"| {x} | {y} | {z} |" for x, y, z in rows]
    lines += ["", f"**기사 단위 짝 비교({a} − {b}, 95% 부트스트랩)**", ""]
    for key, label in (("attribution", "귀속 보존"), ("modality", "양태 보존"), ("qualifiers", "수치 한정어 보존"),
                       ("demoted", "미확인 비율"), ("claims", "claim 수")):
        mean, lo, hi = res["paired"][key]
        lines.append(f"- {label}: {mean:+.3f} [{lo:+.3f}, {hi:+.3f}]")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> None:
    from .stage_a import RECORDS

    ap = argparse.ArgumentParser(prog="s2_metrics")
    ap.add_argument("--base", default="S1C")
    ap.add_argument("--arm", default="S2B")
    ap.add_argument("--json", type=Path)
    args = ap.parse_args(argv)
    res = compare(read_jsonl(RECORDS), args.base, args.arm)
    print(format_report(res))
    if args.json:
        args.json.write_text(json.dumps(res, ensure_ascii=False, indent=1, default=list), encoding="utf-8")


if __name__ == "__main__":
    main()
