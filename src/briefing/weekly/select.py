"""씨앗 선정 — 한 주 카드 목록 → Seed(씨앗 · 수렴 글 · 보강 한 줄 · 영역 라벨 · 깔때기). README §5 · §9 2번.

LLM(데일리 author 와 같은 headless `claude -p`, clean dir)이 고르고, **코드가 하드 게이트 1 을 다시 확인한다**(fail-closed):
씨앗 · support 는 프론티어 발행처(Anthropic > Google > OpenAI)이고 카드 캐시 hit(검증된 claims 있음)여야 한다. 아니면 그 호는
"씨앗 없음"이 된다 — 조용히 다른 카드로 바꾸지 않는다(데일리 top_picks 의 원칙: LLM 은 라벨, 배분은 코드).
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from ..core.authoring import author as _author
from ..core.retrieval.sources import catalog_keys, resolve_sources
from .collect import WeekCard, week_range

FRONTIER = ("Anthropic", "Google", "OpenAI")      # 카탈로그 category · 우선순위 순
_PROMPT = Path(__file__).resolve().parent / "prompts" / "select_system.md"
_SUMMARY_CHARS, _WHY_CHARS = 500, 200


@dataclass(frozen=True)
class Candidate:
    card: int
    area: str
    mechanism: bool
    aws_path: bool
    note: str


@dataclass(frozen=True)
class Seed:
    seed: int | None                      # WeekCard.n — None = 이번 주 아이디어 없음
    support: tuple[int, ...]              # 수렴 프론티어 글(≤1)
    aws_line: int | None                  # ② 한 줄 보강층
    mechanism: str
    experiment: str
    candidates: tuple[Candidate, ...]
    not_chosen: tuple[tuple[int, str], ...]
    reason: str

    @property
    def none(self) -> bool:
        return self.seed is None

    @property
    def cards(self) -> tuple[int, ...]:
        """기사에 들어가는 카드 번호(씨앗 → 수렴 → 보강)."""
        return tuple(n for n in (self.seed, *self.support, self.aws_line) if n is not None)

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)


def media_category(cards: list[WeekCard]) -> dict[int, str]:
    """카드 번호 → 카탈로그 category(발행처 묶음). 카탈로그에 없는 media 는 ""."""
    by_name = {s.name: s.category for s in resolve_sources(catalog_keys())}
    return {c.n: by_name.get(c.media, "") for c in cards}


def build_select_system_prompt() -> str:
    return _PROMPT.read_text(encoding="utf-8")


def build_select_user_prompt(cards: list[WeekCard], issue_date: str) -> str:
    lo, hi = week_range(issue_date)
    lines = [f"발행일 {issue_date}(토). 한 주 = run_date {lo} ~ {hi}. 카드 {len(cards)}장(데일리 PUBLISH, 같은 원문은 첫 날만).",
             "아래 목록에서 씨앗을 고르고 지정된 JSON 하나로 답하라.", ""]
    for c in cards:
        miss = "" if c.cached else " (캐시 miss — claims 없음)"
        lines.append(f"### #{c.n} [{c.run_date}] {c.media} — {c.title or c.headline}{miss}")
        lines.append(f"url: {c.url}")
        if c.cached:
            lines.append(f"요약: {c.summary[:_SUMMARY_CHARS]}")
            if c.why:
                lines.append(f"왜 중요한가: {c.why[:_WHY_CHARS]}")
            lines.append(f"검증된 claims: {len(c.verified_ids)}/{len(c.claims)}")
        lines.append("")
    return "\n".join(lines)


def parse_seed(text: str) -> Seed:
    obj = _author._last_json_object(text)
    if obj is None:
        raise ValueError("선정자 출력에서 JSON object 를 찾지 못함")

    def _int(v):
        return int(v) if isinstance(v, (int, float, str)) and str(v).strip().lstrip("#").isdigit() else None

    cands = tuple(Candidate(card=_int(c.get("card")) or 0, area=str(c.get("area", "")), mechanism=bool(c.get("mechanism")),
                            aws_path=bool(c.get("aws_path")), note=str(c.get("note", "")))
                  for c in obj.get("candidates", []) if isinstance(c, dict))
    support = tuple(n for n in (_int(x) for x in obj.get("support", []) or []) if n is not None)
    not_chosen = tuple((_int(x.get("card")) or 0, str(x.get("why", ""))) for x in obj.get("not_chosen", []) or []
                       if isinstance(x, dict))
    return Seed(seed=_int(obj.get("seed")), support=support, aws_line=_int(obj.get("aws_line")),
                mechanism=str(obj.get("mechanism", "")).strip(), experiment=str(obj.get("experiment", "")).strip(),
                candidates=cands, not_chosen=not_chosen, reason=str(obj.get("reason", "")).strip())


def enforce(seed: Seed, cards: list[WeekCard]) -> Seed:
    """하드 게이트 1 + 캐시 hit 를 코드가 확인한다. 위반은 '씨앗 없음'(이유 기록) — 다른 카드로 바꾸지 않는다."""
    by_n = {c.n: c for c in cards}
    cat = media_category(cards)

    def _ok_frontier(n: int | None) -> bool:
        return n in by_n and by_n[n].cached and cat.get(n, "") in FRONTIER

    reason = seed.reason
    s = seed.seed
    if s is not None and not _ok_frontier(s):
        why = ("카드 없음" if s not in by_n else "캐시 miss(claims 없음)" if not by_n[s].cached
               else f"발행처 {by_n[s].media!r}({cat.get(s) or '미분류'}) 는 프론티어 1차가 아님")
        reason = f"선정 #{s} 거부 — 하드 게이트 1: {why}. " + reason
        s = None
    support = tuple(n for n in seed.support if n != s and _ok_frontier(n))[:1]
    aws = seed.aws_line
    if aws is not None and (aws == s or aws in support or aws not in by_n or not by_n[aws].cached
                            or cat.get(aws, "") in FRONTIER):
        aws = None
    return Seed(seed=s, support=support if s is not None else (), aws_line=aws if s is not None else None,
                mechanism=seed.mechanism, experiment=seed.experiment, candidates=seed.candidates,
                not_chosen=seed.not_chosen, reason=reason)


def select(cards: list[WeekCard], issue_date: str, settings, *, model_id: str = "", effort: str | None = None,
           run_author=None, recorder=None) -> Seed:
    """한 주 카드 → Seed. `run_author` 주입 가능(테스트 = fake); 기본 = 데일리 `_run_author`(clean dir · Bedrock env)."""
    run = run_author or _author._run_author
    text = run(build_select_system_prompt(), build_select_user_prompt(cards, issue_date), settings,
               model_id=model_id, effort=effort, recorder=recorder)
    return enforce(parse_seed(text), cards)
