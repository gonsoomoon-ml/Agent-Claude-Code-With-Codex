"""author — 작성자/생성자 = **headless Claude Code(`claude -p`)**. 개인화 = base 계약(고정) + lens + per-user skill.md.

★ 진짜 듀얼 하니스: author=`claude -p`(Claude Code), certifier=`codex exec`(Codex) — 둘 다 별도 subprocess(대칭).
- **Skill 이 Claude Code 의 유일 레버**("왜 두 하니스인가"의 답). Strands 는 author 가 아니다(향후 curation 전담).
- **런타임 격리(비협상):** `claude -p` 는 **clean(빈) dir 에서 실행** — repo `CLAUDE.md`/`AGENTS.md` 자동 로드 금지.
  `--system-prompt` 로 build_system_prompt 가 *유일* 통제(repo 아키텍처 컨텍스트 오염 0).
- Bedrock 라우팅 = *호출 env*(claude 기본 설정엔 없음): `bedrock_author_env()`(스모크 검증된 조합).
- author 는 *동결본 read 만*. 자기 채점 금지 — certifier 직접 호출 안 함(gate 가 함). **certifier 를 import 안 함**(불변식).
- 출력 = 카드별 {headline, summary, why_it_matters, claims[]}; claims 는 원자적(검증 단위). JSON 파서는 순수(테스트가능).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from datetime import date

from .. import _debug
from ..config import Settings, UserConfig
from ..lenses import resolve_lens
from ..prompts import apply_prompt_template
from ..stores.source_store import FrozenSource

_AUTHOR_TIMEOUT_S = 240  # `claude -p` 한 카드(1회 호출) 작성 타임아웃(초). 느리지만-완료되는 호출 여유
# (180→240, 2026-07-01 인시던트 후). ★ pipeline 이 카드별로 이 실패를 격리하므로 초과 카드는 자기만 드롭
# (배치 전체 중단 아님) → 상향이 안전. 정상 author 는 30~90s 라 happy-path wall-clock 엔 영향 없음.

# author 가 emit 해야 하는 JSON 계약 (static → 캐시 프리픽스 안전). 변수·날짜 없음.
_OUTPUT_CONTRACT = (
    "## 출력 형식 (JSON only)\n"
    "다음 JSON object *하나*만 출력하라(코드펜스·여는 설명 금지):\n"
    '{"headline": "...", "summary": "...", "why_it_matters": "...", '
    '"claims": [{"id": "C1", "text": "...", "claim_type": "arithmetic|entailment", '
    '"importance": "core|supporting"}]}\n'
    "claims 는 원자적(독립 검증 단위). 숫자/날짜/% 포함이면 claim_type=arithmetic, 그 외 entailment. 애매하면 arithmetic.\n"
    "importance: headline 또는 why_it_matters 를 직접 뒷받침하면 core, 그 외 supporting."
)


@dataclass(frozen=True)
class Claim:
    id: str
    text: str
    claim_type: str                 # "entailment" | "arithmetic"
    importance: str = "supporting"  # "core"(headline/why 직접 뒷받침) | "supporting" — graceful degradation 용


@dataclass(frozen=True)
class DraftCard:
    source_id: str
    headline: str
    summary: str
    why_it_matters: str       # PROFILE(역할·관심)에 묶인 영향 — 가장 검증이 필요한 줄
    claims: tuple[Claim, ...]


def bedrock_author_env(settings: Settings) -> dict[str, str]:
    """`claude -p` 를 Bedrock 로 라우팅하는 env (스모크 검증된 조합) — author 의 *주* 경로.

    claude 의 기본 설정엔 Bedrock 라우팅이 없으므로 *호출 시* 주입한다(codex 가 자기 config 로 상주하는 것과 대조).
    """
    return {
        **os.environ,
        "CLAUDE_CODE_USE_BEDROCK": "1",
        "ANTHROPIC_MODEL": settings.author_model_id,   # inference-profile prefix (global./us.)
        "AWS_REGION": settings.region,
        "ENABLE_TOOL_SEARCH": "false",
    }


def build_system_prompt(*, lens_guidance: str, skill_md: str) -> str:
    """author *system* 프롬프트 (= prompt-caching 프리픽스) = base(static) + lens + skill + 출력 계약(static).

    ★ **static 유지** — 변하는 값(날짜·source)은 여기 *안* 넣는다(캐시 hit 보존). 날짜·원문 = build_user_prompt().
    lens·skill·계약은 raw 연결(템플릿 치환 X) — 내용에 `{`·`}`·`$` 가 있어도 안전.
    """
    parts = [apply_prompt_template("author_system")]  # static base (변수 없음)
    if lens_guidance.strip():
        parts.append("## 요약 관점(lens)\n" + lens_guidance.strip())
    if skill_md.strip():
        parts.append("## 독자 개인화(skill)\n" + skill_md.strip())
    parts.append(_OUTPUT_CONTRACT)
    return "\n\n".join(parts)


def build_user_prompt(source: FrozenSource, *, today: str | None = None) -> str:
    """claude/agent 의 *user 메시지* (= 캐시 안 되는 동적 turn) = 오늘 날짜 + 동결 원문 + 지시.

    날짜·source 같은 *변하는 내용*은 여기(캐시 프리픽스 밖)에 둔다 → system 캐싱 보존. source.text 는 f-string(브레이스 안전).
    """
    today = today or date.today().isoformat()
    return (
        f"오늘 날짜: {today} (상대 날짜는 이 기준; 원문에 없는 날짜 생성 금지).\n\n"
        f"다음 동결 원문을 요약하고 원자적 claims 를 추출하라:\n\n{source.text}"
    )


def draft_card(source: FrozenSource, user: UserConfig, settings: Settings) -> DraftCard:
    """동결본 1건 → headless `claude -p`(base + lens + skill) → 초안 카드 + 원자적 claims.

    system(캐시 프리픽스, static) = build_system_prompt(lens, skill) + user(동적) = build_user_prompt(source).
    ★ certifier 는 lens·skill 을 절대 안 본다(불변식 #4). source 는 user turn → 브레이스 안전.
    """
    system_prompt = build_system_prompt(
        lens_guidance=resolve_lens(user.lens).guidance, skill_md=user.skill_md
    )
    text = _run_author(system_prompt, build_user_prompt(source), settings)
    return _to_draft_card(source.source_id, _parse_card_json(text))


def revise_claims(
    source: FrozenSource,
    user: UserConfig,
    settings: Settings,
    *,
    prior: DraftCard,
    failed_ids: tuple[str, ...],
) -> DraftCard:
    """Maker-Checker 재도출 — 실패한 claim(`failed_ids`)만 source 에서 다시 도출 (gate 가 호출).

    ★ decorrelation 보존: 피드백 = `failed_ids`(*어떤* claim 이 실패했는지)만 — certifier 의 *이유/정답* 은 안 줌.
    author 는 자기 이전 claims + 동결본을 다시 보고 실패분만 재도출; 통과 claim 은 유지(thrashing 방지).
    """
    system_prompt = build_system_prompt(
        lens_guidance=resolve_lens(user.lens).guidance, skill_md=user.skill_md
    )
    text = _run_author(system_prompt, _build_revise_prompt(source, prior, failed_ids), settings)
    return _to_draft_card(source.source_id, _parse_card_json(text))


# ───────────────────────── headless `claude -p` 호출 (Claude Code, clean dir, Bedrock env) ─────────────────────────

def _run_author(system_prompt: str, user_prompt: str, settings: Settings) -> str:
    """headless `claude -p`(Claude Code) on Bedrock → 최종 답변 텍스트.

    **clean dir 에서 실행**(repo CLAUDE.md/AGENTS.md 미로드) + `--system-prompt`(build_system_prompt 가 *유일* 통제,
    Claude Code 기본 프롬프트 대체) + Bedrock env 주입(`bedrock_author_env`). 모델 = ANTHROPIC_MODEL(env).
    certifier(`codex exec`)와 대칭 — 둘 다 별도 프로세스 + clean dir + stdin 닫음.
    """
    _debug.dprint(
        "author → claude -p",
        f"clean dir · --system-prompt({len(system_prompt)}c) · user({len(user_prompt)}c) · "
        f"model={settings.author_model_id}",
    )
    clean_dir = tempfile.mkdtemp(prefix="author-clean-")  # 빈 dir → repo 컨텍스트 미상속(격리)
    t0 = time.monotonic()
    try:
        proc = subprocess.run(
            [
                "claude", "-p",
                "--system-prompt", system_prompt,
                "--output-format", "json",
                user_prompt,
            ],
            cwd=clean_dir,
            capture_output=True,
            text=True,
            timeout=_AUTHOR_TIMEOUT_S,
            env=bedrock_author_env(settings),
            stdin=subprocess.DEVNULL,
            check=False,
        )
    finally:
        shutil.rmtree(clean_dir, ignore_errors=True)
    _debug.dprint("author ⊣ claude -p",
                  f"rc={proc.returncode} · {int((time.monotonic() - t0) * 1000)}ms · stdout={len(proc.stdout)}c", "dim")
    if proc.returncode != 0:
        raise RuntimeError(f"claude -p rc={proc.returncode}: {proc.stderr.strip()[:200]}")
    return _extract_claude_result(proc.stdout)


def _extract_claude_result(stdout: str) -> str:
    """`claude -p --output-format json` → `.result`(최종 텍스트). envelope JSON 아니면 stdout 그대로."""
    try:
        obj = json.loads(stdout)
    except (ValueError, TypeError):
        return stdout
    if isinstance(obj, dict) and "result" in obj:
        return str(obj["result"])
    return stdout


def _build_revise_prompt(
    source: FrozenSource, prior: DraftCard, failed_ids: tuple[str, ...], *, today: str | None = None
) -> str:
    """재도출 user turn — 실패 claim *표시*만(최소 피드백) + 자기 이전 claims + 동결본. certifier 추론 미포함."""
    failed = set(failed_ids)
    prior_lines = "\n".join(
        f'- {c.id} [{"재도출 필요" if c.id in failed else "유지"}]: {c.text}' for c in prior.claims
    )
    today = today or date.today().isoformat()
    return (
        f"오늘 날짜: {today} (원문에 없는 날짜 생성 금지).\n\n"
        "이전 초안의 일부 claim 이 독립 검증에 실패했다. **실패로 표시된 claim 만** 원문에서 다시 도출하고 "
        "'유지' claim 은 그대로 둬라(왜 실패인지는 주어지지 않는다 — 원문만 다시 보라).\n\n"
        f"이전 claims:\n{prior_lines}\n\n"
        f"동일 JSON 형식으로 전체 카드를 다시 출력하라. 동결 원문:\n\n{source.text}"
    )


# ───────────────────────── 순수 파서 (테스트 가능 — AWS·CLI 불필요) ─────────────────────────

def _parse_card_json(text: str) -> dict:
    """author 출력 텍스트에서 카드 JSON object 추출 (코드펜스·여는 설명에 견고). 실패 시 fail-loud."""
    obj = _last_json_object(text)
    if obj is None:
        raise ValueError("author 출력에서 JSON 카드 object 를 찾지 못함")
    return obj


def _to_draft_card(source_id: str, data: dict) -> DraftCard:
    """파싱된 dict → DraftCard. claim_type 은 두 허용값으로 정규화(그 외 → entailment)."""
    claims = tuple(
        Claim(
            id=str(c["id"]),
            text=str(c["text"]),
            claim_type="arithmetic" if str(c.get("claim_type")) == "arithmetic" else "entailment",
            importance="core" if str(c.get("importance")) == "core" else "supporting",
        )
        for c in data.get("claims", [])
    )
    return DraftCard(
        source_id=source_id,
        headline=str(data.get("headline", "")).strip(),
        summary=str(data.get("summary", "")).strip(),
        why_it_matters=str(data.get("why_it_matters", "")).strip(),
        claims=claims,
    )


def _last_json_object(text: str) -> dict | None:
    """noisy 텍스트에서 *마지막으로 파싱되는* JSON object 추출. (certifier 의 동형 헬퍼 — import 차단 위해 중복.)"""
    candidates: list[str] = []
    depth = 0
    start = -1
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}" and depth > 0:
            depth -= 1
            if depth == 0 and start >= 0:
                candidates.append(text[start : i + 1])
    for cand in reversed(candidates):
        try:
            obj = json.loads(cand)
        except (ValueError, TypeError):
            continue
        if isinstance(obj, dict):
            return obj
    return None
