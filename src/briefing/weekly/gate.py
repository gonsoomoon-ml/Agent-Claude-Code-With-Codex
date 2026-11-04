"""주간 기사 게이트 — 발송 전 결정론 검사 + ② 사실 대조(Codex). 데일리 gate · certifier 재사용.

검사 3층:
  1) lint(`weekly/lint.py`) — 구성 · 글자 수 · 그림(2장 · 숫자 근거) · 용어. FAIL 이면 격리.
  2) ② 인용(cite) — 작성자가 낸 {문장, 카드 번호} 마다(2안, 2026-11-04):
     문장이 ② 에 그대로 있나 · 카드가 PUBLISH 카드이고 원문이 있나 · 숫자가 있으면 데일리와 같은 값 대조
     (`certify(claim_type="arithmetic")` = numeric 값 대조 + BLOCKED 면 codex 2차) · 원문이 문장을 함의하나
     (`certify(claim_type="entailment")` = codex, clean dir). 봉투의 source_excerpt 는 **작성자가 읽은 동결 · 재수집 원문**
     — 데일리 `_build_envelope` 와 같은 모양(동결 전문). 데일리 claims 는 작성자의 읽기 보조일 뿐 대조 대상이 아니다.
  3) 인용 없는 ② 사실 문장 — strict 면 FAIL, 아니면 WARN(1단계 기본: `WEEKLY_STRICT=0`, "막지 말고 표시해서 보낸다").
신뢰 경계: Codex 에는 Envelope 4필드(원문 · 문장 · 유형 · 스키마)만 간다. 작성자의 추론은 가지 않는다.
「엮으면」 단락 · 그림 · 캡션 줄은 우리 종합(사실 아님)이라 대조하지 않는다. ③ · ④ 는 제안이라 대조하지 않는다.
★ `_run_codex` 는 프롬프트를 argv 하나로 넘기므로(리눅스 MAX_ARG_STRLEN 128KB) 원문은 바이트 상한으로 자른다.
"""
from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass

from ..core.gate import _SCHEMA
from ..core.verification import numeric
from ..core.verification.certifier import CertVerdict, Envelope, certify
from . import lint as _lint
from .collect import WeekCard

CODEX_EXCERPT_MAX_BYTES = 120_000   # argv 한 조각 상한(128KB) 아래 — 지시문 ~1KB 여유


@dataclass(frozen=True)
class Cite:
    text: str                        # ② 의 문장 그대로
    card: int                        # WeekCard.n
    claims: tuple[str, ...] = ()     # 2안 뒤 미사용(과거 JSON 호환 — 대조는 원문으로)


@dataclass(frozen=True)
class GateItem:
    verdict: str               # PASS | WARN | FAIL
    check: str                 # "lint 9" · "cite" · "uncited" · 추가 검사 이름
    msg: str                   # run 로그용(certifier 근거 포함 가능)
    feedback: str = ""         # 작성자에게 돌려줄 말 — 확정적 사유만. 비면 msg 를 쓴다(결정론 검사)
    fixable: bool = True       # False = 작성자가 고칠 수 없는 실패(certifier 미가용) — 재작성 피드백에서 뺀다(run 은 재작성을 생략)


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
_CAPTION_RE = re.compile(r"^그림\s*\d+\s*[—-]")        # 그림 캡션 줄(README §4) — 사실 문장이 아니다


def section_two(md: str) -> str:
    """② 본문(`## ②` 다음 줄부터 다음 `## ` 전까지). 없으면 빈 값."""
    for part in _H2_RE.split(md)[1:]:
        head, _, body = part.partition("\n")
        if head.startswith("②"):
            return body
    return ""


def fact_sentences(two: str) -> list[str]:
    """② 의 사실 문장 — 그림 · 굵은 표제 · 캡션 줄은 빼고, 「엮으면」 단락은 통째로 뺀다."""
    out = []
    for para in re.split(r"\n\s*\n", _FENCE_RE.sub("", two)):
        para = " ".join(para.split())
        if not para or para.startswith("**엮으면") or _CAPTION_RE.match(para):
            continue
        out += [s for s in _SENT_RE.split(_LEAD_RE.sub("", para)) if s]
    return out


def _norm(s: str) -> str:
    return " ".join(s.split())


def _unfixable(v: CertVerdict) -> bool:
    """certifier 가 실행되지 못한 판정 — 작성자가 고칠 수 없다. 함의 경로는 model "codex-error", 산술 경로는 2차 판정의 오류 문구가
    근거에 섞여 들어온다(`certify()` 가 BLOCKED · model "deterministic" 으로 감싼다)."""
    return v.model == "codex-error" or "certifier 미가용" in v.evidence


def excerpt_for_codex(text: str, limit: int = CODEX_EXCERPT_MAX_BYTES) -> str:
    """원문을 UTF-8 바이트 상한으로 자른다(글자 경계 보존). 상한 아래면 그대로."""
    raw = text.encode("utf-8")
    return text if len(raw) <= limit else raw[:limit].decode("utf-8", errors="ignore")


def check_cites(md: str, cites: Sequence[Cite], cards: Sequence[WeekCard], texts: Mapping[int, str], *,
                strict: bool = True, certify_fn: Callable[[str, Envelope], CertVerdict] = certify) -> list[GateItem]:
    """② 인용 검사(2안). texts = 카드 번호 → 작성자가 읽은 원문(동결 · 재수집)."""
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
        src = texts.get(ct.card, "")
        if not src.strip():
            items.append(GateItem("FAIL", "cite", f"{where} — 카드 #{ct.card} 원문 없음"))
            continue
        excerpt = excerpt_for_codex(src)
        if not numeric.scan(text).empty():   # 숫자 문장: 값 대조(결정론, BLOCKED 면 codex 2차) 를 먼저
            v = certify_fn(f"w{ct.card}-{i}n", Envelope(source_excerpt=excerpt, claim_text=text,
                                                        claim_type="arithmetic", schema=_SCHEMA))
            if v.verdict != "VERIFIED":
                items.append(GateItem("FAIL", "cite", f"{where} — 숫자 {v.verdict}: {v.evidence[:120]}",
                                      feedback=f"{where} — 숫자가 원문과 맞지 않음({v.verdict}): 원문 표기 그대로 쓰거나 문장을 뺀다",
                                      fixable=not _unfixable(v)))
                continue
        v = certify_fn(f"w{ct.card}-{i}", Envelope(source_excerpt=excerpt, claim_text=text,
                                                   claim_type="entailment", schema=_SCHEMA))
        ok = v.verdict == "VERIFIED"
        items.append(GateItem("PASS" if ok else "FAIL", "cite",
                              f"{where} — codex {v.verdict}{'' if ok else ': ' + v.evidence[:120]}",
                              feedback="" if ok else f"{where} — 원문이 문장을 함의하지 않음({v.verdict}): 원문에 있는 사실만 쓰거나 문장을 뺀다",
                              fixable=not _unfixable(v)))   # codex 실행 오류(미가용)는 작성자 탓이 아니다
    cited = [_norm(c.text) for c in cites]
    for s in fact_sentences(section_two(md)):
        if not any(s in c or c in s for c in cited):
            items.append(GateItem("FAIL" if strict else "WARN", "uncited", f"인용 없는 ② 문장: {s[:60]}…"))
    return items


def run_gate(md: str, cites: Sequence[Cite], cards: Sequence[WeekCard], texts: Mapping[int, str], *,
             strict: bool = True, certify_fn: Callable[[str, Envelope], CertVerdict] = certify,
             extra_checks: Sequence[Callable[[str], list[GateItem]]] = (), seed_card: int | None = None,
             min_seed_cites: int = 4) -> GateResult:
    """lint → ② 인용 → 추가 검사(링크 · 모델 · 자) 순서로 모은다. FAIL 이 하나라도 있으면 QUARANTINE.
    seed_card 가 주어지면 씨앗 카드 인용 문장이 min_seed_cites 미만일 때 WARN(설계에 필요한 사실을 빠짐없이 — README §4 ②)."""
    items = [GateItem(v, f"lint {n}", m) for v, n, m in _lint.lint(md) if v in ("PASS", "WARN", "FAIL")]
    failed_lint = tuple(it.check.split()[1] for it in items if it.verdict == "FAIL")
    cite_items = check_cites(md, cites, cards, texts, strict=strict, certify_fn=certify_fn)
    items += cite_items
    if seed_card is not None:
        n = sum(1 for c in cites if c.card == seed_card)
        if n < min_seed_cites:
            items.append(GateItem("WARN", "seed", f"씨앗 카드 #{seed_card} 인용 문장 {n}개 (< {min_seed_cites})"))
    for chk in extra_checks:
        items += chk(md)
    failed_cites = tuple(it.feedback or it.msg for it in cite_items if it.verdict == "FAIL")
    status = "QUARANTINE" if any(it.verdict == "FAIL" for it in items) else "PASS"
    return GateResult(status, tuple(items), failed_lint, failed_cites)
