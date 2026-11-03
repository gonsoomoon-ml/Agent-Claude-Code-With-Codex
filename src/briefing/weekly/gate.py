"""주간 기사 게이트 — 발송 전 결정론 검사 + ② 사실 대조(Codex). 데일리 gate · certifier 재사용.

검사 3층:
  1) lint(`weekly/lint.py`) — 구성 · 글자 수 · 그림 · 용어. FAIL 이면 격리.
  2) ② 인용(cite) — 작성자가 낸 {문장, 카드 번호, claim id} 마다:
     문장이 ② 에 그대로 있나 · claim 이 그 카드의 VERIFIED id 인가 · 문장의 숫자가 인용 claims 안에 있나(결정론,
     데일리 `_interp_lint` 와 같은 `_num_tokens`) · 인용 claims 가 문장을 함의하나(`certify` = codex, clean dir).
  3) 인용 없는 ② 사실 문장 — strict 면 FAIL(푸터 "②의 사실은 원문 대조를 통과"가 참이 되게), 아니면 WARN.
신뢰 경계: Codex 에는 Envelope 4필드(인용 claims · 문장 · 유형 · 스키마)만 간다. 작성자의 추론은 가지 않는다.
「엮으면」 단락은 우리 종합(사실 아님)이라 대조하지 않는다. ③ · ④ 는 제안이라 대조하지 않는다.
"""
from __future__ import annotations

import json
import re
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass

from ..core.gate import _SCHEMA, _num_tokens
from ..core.verification.certifier import CertVerdict, Envelope, certify
from . import lint as _lint
from .collect import WeekCard


@dataclass(frozen=True)
class Cite:
    text: str                  # ② 의 문장 그대로
    card: int                  # WeekCard.n
    claims: tuple[str, ...]    # 그 카드의 claim id


@dataclass(frozen=True)
class GateItem:
    verdict: str               # PASS | WARN | FAIL
    check: str                 # "lint 9" · "cite" · "uncited" · 추가 검사 이름
    msg: str                   # run 로그용(certifier 근거 포함 가능)
    feedback: str = ""         # 작성자에게 돌려줄 말 — 확정적 사유만. 비면 msg 를 쓴다(결정론 검사)


@dataclass(frozen=True)
class GateResult:
    status: str                       # PASS | QUARANTINE
    items: tuple[GateItem, ...]
    failed_lint: tuple[str, ...]      # FAIL 난 lint 검사 번호 — 재작성 피드백
    failed_cites: tuple[str, ...]     # FAIL 난 ② 문장 — 재작성 피드백

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)


_H2_RE = re.compile(r"^## ", re.M)
_FENCE_RE = re.compile(r"^```.*?^```[ \t]*$", re.M | re.S)
_LEAD_RE = re.compile(r"^\*\*[^*]+\*\*\s*")          # 단락 머리의 굵은 표제(**Anthropic, 글 제목.** · **AWS 한 줄.**)
_SENT_RE = re.compile(r"(?<=[.!?])\s+(?=\S)")


def section_two(md: str) -> str:
    """② 본문(`## ②` 다음 줄부터 다음 `## ` 전까지). 없으면 빈 값."""
    for part in _H2_RE.split(md)[1:]:
        head, _, body = part.partition("\n")
        if head.startswith("②"):
            return body
    return ""


def fact_sentences(two: str) -> list[str]:
    """② 의 사실 문장 — 그림 · 굵은 표제는 빼고, 「엮으면」 단락은 통째로 뺀다."""
    out = []
    for para in re.split(r"\n\s*\n", _FENCE_RE.sub("", two)):
        para = " ".join(para.split())
        if not para or para.startswith("**엮으면"):
            continue
        out += [s for s in _SENT_RE.split(_LEAD_RE.sub("", para)) if s]
    return out


def _norm(s: str) -> str:
    return " ".join(s.split())


def check_cites(md: str, cites: Sequence[Cite], cards: Sequence[WeekCard], *, strict: bool = True,
                certify_fn: Callable[[str, Envelope], CertVerdict] = certify) -> list[GateItem]:
    two = _norm(section_two(md))
    by_n = {c.n: c for c in cards}
    items: list[GateItem] = []
    for i, ct in enumerate(cites, 1):
        text, where = _norm(ct.text), f"#{ct.card} {ct.text[:40]}…"
        card = by_n.get(ct.card)
        if not text or text not in two:
            items.append(GateItem("FAIL", "cite", f"{where} — 문장이 ② 에 없다"))
            continue
        if card is None or not card.cached:
            items.append(GateItem("FAIL", "cite", f"{where} — 카드 #{ct.card} 없음/캐시 miss"))
            continue
        bad = [c for c in ct.claims if c not in card.verified_ids]
        if not ct.claims or bad:
            items.append(GateItem("FAIL", "cite", f"{where} — VERIFIED 아닌 claim {bad or '(없음)'}"))
            continue
        texts = [c.text for c in card.claims if c.id in ct.claims]
        smuggled = _num_tokens(text) - {t for x in texts for t in _num_tokens(x)}
        if smuggled:
            items.append(GateItem("FAIL", "cite", f"{where} — 인용 claims 에 없는 숫자 {sorted(smuggled)}"))
            continue
        v = certify_fn(f"w{ct.card}-{i}", Envelope(source_excerpt="\n".join(texts), claim_text=text,
                                                   claim_type="entailment", schema=_SCHEMA))
        ok = v.verdict == "VERIFIED"
        items.append(GateItem("PASS" if ok else "FAIL", "cite",
                              f"{where} — codex {v.verdict}{'' if ok else ': ' + v.evidence[:120]}",
                              feedback="" if ok else f"{where} — 인용 claims 가 문장을 함의하지 않음({v.verdict}): claim 의 사실만 쓰거나 문장을 뺀다"))
    cited = [_norm(c.text) for c in cites]
    for s in fact_sentences(section_two(md)):
        if not any(s in c or c in s for c in cited):
            items.append(GateItem("FAIL" if strict else "WARN", "uncited", f"인용 없는 ② 문장: {s[:60]}…"))
    return items


def run_gate(md: str, cites: Sequence[Cite], cards: Sequence[WeekCard], *, strict: bool = True,
             certify_fn: Callable[[str, Envelope], CertVerdict] = certify,
             extra_checks: Sequence[Callable[[str], list[GateItem]]] = ()) -> GateResult:
    """lint → ② 인용 → 추가 검사(링크 · 모델) 순서로 모은다. FAIL 이 하나라도 있으면 QUARANTINE."""
    items = [GateItem(v, f"lint {n}", m) for v, n, m in _lint.lint(md) if v in ("PASS", "WARN", "FAIL")]
    failed_lint = tuple(it.check.split()[1] for it in items if it.verdict == "FAIL")
    cite_items = check_cites(md, cites, cards, strict=strict, certify_fn=certify_fn)
    items += cite_items
    for chk in extra_checks:
        items += chk(md)
    failed_cites = tuple(it.feedback or it.msg for it in cite_items if it.verdict == "FAIL")
    status = "QUARANTINE" if any(it.verdict == "FAIL" for it in items) else "PASS"
    return GateResult(status, tuple(items), failed_lint, failed_cites)
