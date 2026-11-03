"""기사 작성 — Seed + 카드 + 원문 → Draft(md · cites). 데일리 author(`claude -p`, clean dir) 재사용.

재작성(revise)은 게이트가 FAIL 로 돌려준 항목만 작성자에게 보여 준다 — 데일리 maker-checker 와 같은 모양
(확정적 사유만, certifier 의 근거 문장은 주지 않는다 = decorrelation 보존). 횟수 상한은 run.py 가 가진다.
원문은 데일리 동결본(≤20,000자)을 쓰고, 잘린 것만 다시 가져온다(README §8 — 상한 60,000자, robots 는 데일리와 같은 `_http_get`).
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

from ..core.authoring import author as _author
from ..core.retrieval.sources import TRUNCATED_MIN_CHARS, _http_get
from .collect import WeekCard, week_range
from .gate import Cite, GateResult
from .select import Seed

REFETCH_MAX_CHARS = 60_000
_PROMPT = Path(__file__).resolve().parent / "prompts" / "write_system.md"
_TERMS = Path(__file__).resolve().parent / "terms.md"


@dataclass(frozen=True)
class Draft:
    md: str
    cites: tuple[Cite, ...]

    def to_json(self) -> str:
        return json.dumps({"md": self.md, "cites": [asdict(c) for c in self.cites]}, ensure_ascii=False)


def refetch_url(url: str) -> str:
    """원문 다시 가져오기 — 데일리와 같은 GET(robots 존중 · 시간 상한) + trafilatura 본문 추출. 실패 → ""."""
    html = _http_get(url)
    if not html:
        return ""
    import trafilatura  # lazy(무거운 import 회피 — 데일리와 같은 패턴)
    return trafilatura.extract(html, include_comments=False) or ""


def source_text(store, card: WeekCard, *, refetch=None) -> str:
    """동결 원문. 잘린 동결본(상한 근처)이고 refetch 가 주어지면 다시 가져와 더 긴 쪽을 쓴다(상한 60,000자)."""
    try:
        frozen = store.get_source(card.source_id).text
    except KeyError:
        frozen = ""
    if refetch is not None and card.url and len(frozen) >= TRUNCATED_MIN_CHARS:
        try:
            full = refetch(card.url)
        except Exception:  # noqa: BLE001 — 재수집 실패는 동결본으로(기사 생성을 막지 않는다)
            full = ""
        if len(full) > len(frozen):
            return full[:REFETCH_MAX_CHARS]
    return frozen


def terms_block() -> str:
    """terms.md 의 표(FAIL · WARN 행)를 시스템 프롬프트에 붙일 목록으로."""
    rows = []
    for line in _TERMS.read_text(encoding="utf-8").splitlines():
        cols = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cols) >= 4 and cols[3] in ("FAIL", "WARN"):
            rows.append(f"- {cols[0]} → {cols[1]} ({cols[3]}: {cols[2]})")
    return "\n".join(rows)


def build_write_system_prompt() -> str:
    return _PROMPT.read_text(encoding="utf-8") + "\n\n## 쓰지 않을 말 → 쓸 말(lint 9 가 검사 — FAIL 은 발송을 막는다)\n" + terms_block()


def _card_block(role: str, c: WeekCard, text: str) -> str:
    claims = "\n".join(f"- {cl.id}: {cl.text}" for cl in c.claims if cl.id in c.verified_ids) or "- (없음)"
    return (f"### 카드 #{c.n} ({role}) — {c.media} · {c.title or c.headline}\nurl: {c.url}\n"
            f"검증된 사실(claims — ② 의 cites 는 이 id 로만):\n{claims}\n\n요약: {c.summary}\n\n"
            f"동결 원문({len(text):,}자):\n{text}\n")


def build_write_user_prompt(seed: Seed, cards: list[WeekCard], texts: dict[int, str], issue_date: str, *,
                            today: str | None = None) -> str:
    lo, hi = week_range(issue_date)
    by_n = {c.n: c for c in cards}
    head = [f"오늘 날짜: {today or date.today().isoformat()}. 발행일 {issue_date}(토). 기간 줄 = {lo} ~ {hi[5:]}.",
            f"씨앗 = #{seed.seed}. 수렴 글 = {', '.join(f'#{n}' for n in seed.support) or '없음'}. "
            f"② 보강 한 줄 = {f'#{seed.aws_line}' if seed.aws_line else '없음'}.",
            f"메커니즘: {seed.mechanism}", f"실험 한 줄(선정자 제안 — 다듬어도 된다): {seed.experiment}",
            "아래 카드와 원문만으로 기사를 쓰고 지정된 JSON 하나로 답하라.", ""]
    roles = {seed.seed: "씨앗", **{n: "수렴 글" for n in seed.support}}
    if seed.aws_line is not None:
        roles[seed.aws_line] = "보강 한 줄"
    blocks = [_card_block(roles[n], by_n[n], texts.get(n, "")) for n in seed.cards if n in by_n]
    return "\n".join(head) + "\n" + "\n".join(blocks)


def build_revise_user_prompt(prev: Draft, feedback: list[str]) -> str:
    items = "\n".join(f"- {f}" for f in feedback)
    return ("이전 초안(JSON):\n" + prev.to_json() + "\n\n다음 검사가 실패했다. **실패한 것만 고치고** 나머지 문장은 그대로 둔다. "
            "② 문장을 고치면 cites 의 text 도 같이 고친다. 전체를 같은 JSON 형식으로 다시 출력하라.\n" + items)


def parse_draft(text: str) -> Draft:
    obj = _author._last_json_object(text)
    if obj is None or not str(obj.get("md", "")).strip():
        raise ValueError("작성자 출력에서 md 가 든 JSON object 를 찾지 못함")
    cites = tuple(Cite(text=str(c.get("text", "")).strip(), card=int(c.get("card", 0) or 0),
                       claims=tuple(str(x) for x in c.get("claims", []) or []))
                  for c in obj.get("cites", []) or [] if isinstance(c, dict))
    return Draft(md=str(obj["md"]).strip() + "\n", cites=cites)


def feedback_from_gate(result: GateResult) -> list[str]:
    """작성자에게 돌려줄 실패 항목 — 확정적 사유만(GateItem.feedback 우선, certifier 근거 제외)."""
    return [it.feedback or it.msg for it in result.items if it.verdict == "FAIL"]


def write(seed: Seed, cards: list[WeekCard], texts: dict[int, str], issue_date: str, settings, *,
          model_id: str = "", effort: str | None = None, run_author=None, recorder=None, today: str | None = None) -> Draft:
    run = run_author or _author._run_author
    text = run(build_write_system_prompt(), build_write_user_prompt(seed, cards, texts, issue_date, today=today),
               settings, model_id=model_id, effort=effort, recorder=recorder, prompt_via_stdin=True)
    return parse_draft(text)


def revise(prev: Draft, feedback: list[str], settings, *, model_id: str = "", effort: str | None = None,
           run_author=None, recorder=None) -> Draft:
    run = run_author or _author._run_author
    text = run(build_write_system_prompt(), build_revise_user_prompt(prev, feedback), settings,
               model_id=model_id, effort=effort, recorder=recorder, prompt_via_stdin=True)
    return parse_draft(text)


def none_issue_md(seed: Seed, cards: list[WeekCard], issue_date: str) -> str:
    """씨앗 없는 주의 짧은 호(README §5) — 작성자 호출 없음, 게이트도 거치지 않는다."""
    lo, hi = week_range(issue_date)
    by_n = {c.n: c for c in cards}
    lines = ["# 이번 주 아이디어 없음", f"{lo} ~ {hi[5:]} · 프론티어 1차 글 {len(seed.candidates)}편 검토", "",
             "이번 주는 설계 · SDK 수준에서 재현할 메커니즘이 있는 프론티어 랩(Anthropic · Google · OpenAI) 글이 없었다. "
             "다음 주에 다시 찾는다.", ""]
    if seed.reason:
        lines += [seed.reason, ""]
    if seed.candidates or seed.not_chosen:
        lines.append("## 검토한 글")
        notes = dict(seed.not_chosen)
        for cand in seed.candidates:
            c = by_n.get(cand.card)
            if c is None:
                continue
            why = notes.get(cand.card) or cand.note
            lines.append(f"- {c.media} — {c.title or c.headline}" + (f" — {why}" if why else ""))
    return "\n".join(lines) + "\n"
