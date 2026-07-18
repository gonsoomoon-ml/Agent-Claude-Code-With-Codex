"""author — 작성자/생성자 = **headless Claude Code(`claude -p`)**. 개인화 = base 계약(고정) + lens + per-user skill.md.

★ 진짜 듀얼 하니스: author=`claude -p`(Claude Code), certifier=`codex exec`(Codex) — 둘 다 별도 subprocess(대칭).
- **Skill 이 Claude Code 의 유일 레버**("왜 두 하니스인가"의 답). Strands 는 author 가 아니다(향후 curation 전담).
- **런타임 격리(비협상):** `claude -p` 는 **clean(빈) dir 에서 실행** — repo `CLAUDE.md`/`AGENTS.md` 자동 로드 금지.
  `--system-prompt` 로 build_system_prompt 가 *유일* 통제(repo 아키텍처 컨텍스트 오염 0).
- Bedrock 라우팅 = *호출 env*(claude 기본 설정엔 없음): `bedrock_author_env()`(스모크 검증된 조합).
- author 는 *동결본 read 만*. 자기 채점 금지 — certifier 직접 호출 안 함(gate 가 함). **certifier 를 import 안 함**(불변식).
- 출력 = 카드별 {summary, why_it_matters, claims[]}; **headline 은 안 만든다** — 카드 제목 = 기사 원제목(사실층 앵커=source.title). claims 는 원자적(검증 단위). JSON 파서는 순수(테스트가능).
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
from ..retrieval.sources import MAX_SOURCE_CHARS
from ..stores.source_store import FrozenSource

_AUTHOR_TIMEOUT_S = 360  # `claude -p` 한 카드(1회 호출) 작성 타임아웃(초). 느리지만-완료되는 호출 여유.
# 이력: 180→240(2026-07-01 인시던트)→360(2026-07-18, represent-v3.3 워크로드 재보정).
# ★ 근본 수정은 값이 아니라 v3.3(claims 를 '원문 전체'→'요약 커버리지'로 좁힘, PROMPT_VERSION 참조):
#   v3 의 "claims 원문 전체 빠짐없이"가 밀집 기사에서 24~39 claims 를 뽑아 지연이 240s+ 로 폭증했다.
#   v3.3 순차 실측(동시성 1=프로덕션 조건, 밀집 8,000자): claims 35→10~22, 지연 **완료 전부 119~197s**.
#   즉 정상 기사는 240 밑이지만, 변동(같은 크기가 122s↔실패)이 커 197s+변동 여유로 360 을 둔다.
# ★ 잔여 tail(값으로 못 막음): 초밀집 연구논문(LaTeX 수식 다수 — 예 CARI4D)은 프롬프트 버전 무관하게
#   >360s. 어떤 임계값으로도 못 막으니 그 카드는 격리 드롭(pipeline 카드별 try/except, 2026-07-02 인시던트).
#   → 남은 일 = silent-failure *통지*(드롭을 보이게, 별건 OPEN). 값 상향은 tail 을 못 없앤다.
# ★ 왜 상향이 안전: (1) 카드별 격리 → 초과 카드만 드롭(배치 중단 아님). (2) 스케줄 브리핑 = add_async_task
#   로 최대 8h 세션(agentcore_runtime) → 관측 브리핑 최대 46분 대비 전체 여유 압도적. num_turns=1(루프 없음).

# 프롬프트 계약 버전 — 사실층 캐시 키 성분(계약이 바뀌면 캐시 자동 무효화). card-layering §5.
PROMPT_VERSION = "represent-v3.3"  # v3.3: v3.1(선택 규칙·예산) + claims 를 '원문 전체'→'요약 커버리지'로 좁힘
# (v3.2 = 수치 조건 규칙, 블라인드 A/B 에서 효과 없어 revert — 번호는 changelog 로 건너뜀.)
# v3.3 근거: v3 의 "claims 원문 전체 빠짐없이"가 밀집 기사에서 35~39 claims 를 뽑아 author 지연이 240s+
# (순차 실측)로 폭증·카드 유실. claims 는 *발행물(요약)의 검증 안전망*이지 기사 색인이 아니다 — 요약이 버린
# 사실을 검증할 이유가 없다(독자 미노출). 요약 커버리지로 좁히면 claim 수·지연·certifier 부하가 함께 준다.
# 안전망 불변식 보존: 요약이 진술한 사실은 여전히 전부 claim(요약 사실은 검증 우회 불가).

# author 가 emit 해야 하는 JSON 계약 (static → 캐시 프리픽스 안전). 변수·날짜 없음.
_OUTPUT_CONTRACT = (
    "## 출력 형식 (JSON only)\n"
    "다음 JSON object *하나*만 출력하라(코드펜스·여는 설명 금지):\n"
    '{"summary": "...", "why_it_matters": "...", '
    '"claims": [{"id": "C1", "text": "...", "claim_type": "arithmetic|entailment", '
    '"importance": "core|supporting"}]}\n'
    "summary: 한국어 산문 한 문단(불릿·번호·줄바꿈 금지), **3~5문장**. 첫 문장 = 이 기사에서 새로 일어난 "
    "단 하나의 사실. 도입부만 옮기지 말고 본문 전체에서 고른다. 기사의 결론·논조를 바꾸는 반론·단서가 있으면 "
    "한 절이라도 포함. 원문의 귀속(누가 주장했나)과 유보 표현을 유지. "
    "담을 사실이 3~5문장을 넘으면 분량을 늘리지 말고 무게로 골라 버려라 — 기사를 통째로 옮기지 마라. "
    "'왜 중요한가'는 여기 쓰지 마라.\n"
    "why_it_matters: 한국어 1~3문장 한 단락. summary 를 되풀이하지 말고 독자에게 갖는 의미만. "
    "새 사실·수치·날짜를 도입하지 마라 — summary 와 claims 에 있는 것만 쓴다.\n"
    "제목(headline)은 만들지 마라 — 카드 제목은 기사 원제목을 그대로 쓴다(사실층 앵커, 재프레이밍 금지).\n"
    "claims 는 원자적(독립 검증 단위)이며 **요약이 진술한 모든 사실**을 덮는다 — 요약의 사실은 빠짐없이 "
    "claim 으로(claim 없는 사실은 검증을 우회한다). 요약에 없는 사실은 claim 으로 만들지 마라 — claims 는 "
    "발행물(요약)의 안전망이지 기사 전체의 색인이 아니다. 숫자/날짜/% 포함이면 claim_type=arithmetic, "
    "그 외 entailment. 애매하면 arithmetic.\n"
    "importance: summary 또는 why_it_matters 를 직접 뒷받침하면 core, 그 외 supporting."
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


@dataclass(frozen=True)
class Interpretation:
    """해석층 산출(card-layering §5) — 검증된 사실층 위의 lens 관점 why 한 단락.

    ★ no-new-facts 계약: 검증된 claims/원문에 없는 새 사실·수치 금지 — gate 의 결정론 lint 가 검사.
    based_on = 근거 claim id 인용(필수) — lint 가 VERIFIED 집합 대비 검증.
    """
    why_it_matters: str
    based_on: tuple[str, ...]


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
    **절단 플래그:** 소스의 28.6%가 본문 상한(MAX_SOURCE_CHARS)에서 잘린다 — base 계약의
    "본문 전체를 근거로"가 *물리적으로 없는 뒷부분*에 대한 추측 압력이 되지 않게 잘렸음을 알린다.
    """
    today = today or date.today().isoformat()
    warn = (
        "\n\n(이 원문은 본문 상한에서 **절단**되었다 — 기사의 뒷부분이 없을 수 있다. "
        "없는 결론·후속을 추정하지 마라.)"
        if len(source.text) >= MAX_SOURCE_CHARS
        else ""
    )
    return (
        f"오늘 날짜: {today} (상대 날짜는 이 기준; 원문에 없는 날짜 생성 금지).\n\n"
        f"다음 동결 원문을 요약하고 원자적 claims 를 추출하라. "
        f"요약에 담을 사실은 도입부가 아니라 본문 전체에서 고른다.{warn}\n\n"
        f"{source.text}"
    )


def draft_card(
    source: FrozenSource, user: UserConfig, settings: Settings, *, recorder=None
) -> DraftCard:
    """동결본 1건 → headless `claude -p`(base + lens + skill) → 초안 카드 + 원자적 claims.

    system(캐시 프리픽스, static) = build_system_prompt(lens, skill) + user(동적) = build_user_prompt(source).
    ★ certifier 는 lens·skill 을 절대 안 본다(불변식 #4). source 는 user turn → 브레이스 안전.
    `recorder`(옵션) — `_run_author` 로 그대로 전달(비용 기록).
    """
    system_prompt = build_system_prompt(
        lens_guidance=resolve_lens(user.lens).guidance, skill_md=user.skill_md
    )
    text = _run_author(system_prompt, build_user_prompt(source), settings, recorder=recorder)
    return _to_draft_card(source.source_id, source.title, _parse_card_json(text))


def revise_claims(
    source: FrozenSource,
    user: UserConfig,
    settings: Settings,
    *,
    prior: DraftCard,
    failed_ids: tuple[str, ...],
    recorder=None,
) -> DraftCard:
    """Maker-Checker 재도출 — 실패한 claim(`failed_ids`)만 source 에서 다시 도출 (gate 가 호출).

    ★ decorrelation 보존: 피드백 = `failed_ids`(*어떤* claim 이 실패했는지)만 — certifier 의 *이유/정답* 은 안 줌.
    author 는 자기 이전 claims + 동결본을 다시 보고 실패분만 재도출; 통과 claim 은 유지(thrashing 방지).
    `recorder`(옵션) — `_run_author` 로 그대로 전달(비용 기록).
    """
    system_prompt = build_system_prompt(
        lens_guidance=resolve_lens(user.lens).guidance, skill_md=user.skill_md
    )
    text = _run_author(
        system_prompt, _build_revise_prompt(source, prior, failed_ids), settings, recorder=recorder
    )
    return _to_draft_card(source.source_id, source.title, _parse_card_json(text))


# ───────────────────────── 해석층 (interpretation) — card-layering §5 ─────────────────────────

# 해석층 JSON 계약 (static). 사실층 _OUTPUT_CONTRACT 와 별개 — why 한 단락 + 근거 claim id 인용만.
_INTERP_CONTRACT = (
    "## 출력 형식 (JSON only)\n"
    "다음 JSON object *하나*만 출력하라(코드펜스·여는 설명 금지):\n"
    '{"why_it_matters": "...", "based_on": ["C1", "..."]}\n'
    "based_on = 해석의 근거가 된 claim id 목록(필수, 제공된 검증 claims 중에서만)."
)


def build_interp_system_prompt(*, lens_guidance: str) -> str:
    """해석층 *system* 프롬프트 (static, 캐시 프리픽스) = interp base + lens + 출력 계약.

    ★ v1 은 skill_md 미주입(card-layering 미결 #2 절충: 해석층은 (source, lens) 공유) — 주입 시 공유 소멸.
    lens 는 raw 연결(브레이스-안전).
    """
    parts = [apply_prompt_template("interp_system")]
    if lens_guidance.strip():
        parts.append("## 요약 관점(lens)\n" + lens_guidance.strip())
    parts.append(_INTERP_CONTRACT)
    return "\n\n".join(parts)


def build_interp_user_prompt(
    source: FrozenSource, verified_claims: tuple[Claim, ...], *, today: str | None = None
) -> str:
    """해석층 user 메시지(동적) = 날짜 + **검증된 claims 목록** + 동결 원문.

    해석은 VERIFIED claims 위에서만 — gate 가 seam 에서 이미 걸러 넘겨준다(미검증 claim 미노출).
    """
    today = today or date.today().isoformat()
    claim_lines = "\n".join(f"- {c.id}: {c.text}" for c in verified_claims)
    return (
        f"오늘 날짜: {today} (원문에 없는 날짜·숫자 생성 금지).\n\n"
        f"검증된 사실(claims):\n{claim_lines}\n\n"
        "위 검증된 사실과 아래 동결 원문에 근거해, 독자 관점의 '나에게 왜 중요한가' 한 단락(1~3문장)만 작성하라. "
        f"새 사실·수치 도입 금지.\n\n동결 원문:\n\n{source.text}"
    )


def draft_interpretation(
    source: FrozenSource,
    verified_claims: tuple[Claim, ...],
    user: UserConfig,
    settings: Settings,
    *,
    recorder=None,
) -> Interpretation:
    """검증된 사실층 위에 lens 관점 why 한 단락 생성 — 같은 headless `claude -p`, 짧은 출력.

    루프 없음(Maker-Checker 는 사실층 소유) — 가드(결정론 lint)와 실패 처분(폴백)은 gate.interpret_card 가 소유.
    `recorder`(옵션) — `_run_author` 로 그대로 전달(비용 기록).
    """
    system_prompt = build_interp_system_prompt(lens_guidance=resolve_lens(user.lens).guidance)
    text = _run_author(
        system_prompt, build_interp_user_prompt(source, verified_claims), settings, recorder=recorder
    )
    return _parse_interp(text)


def _parse_interp(text: str) -> Interpretation:
    """해석층 출력 텍스트 → Interpretation (순수 파서, noisy 텍스트에 견고). 실패 시 fail-loud."""
    obj = _last_json_object(text)
    if obj is None:
        raise ValueError("해석층 출력에서 JSON object 를 찾지 못함")
    return Interpretation(
        why_it_matters=str(obj.get("why_it_matters", "")).strip(),
        based_on=tuple(str(x) for x in obj.get("based_on", [])),
    )


# ───────────────────────── headless `claude -p` 호출 (Claude Code, clean dir, Bedrock env) ─────────────────────────

def _run_author(
    system_prompt: str, user_prompt: str, settings: Settings, *, recorder=None
) -> str:
    """headless `claude -p`(Claude Code) on Bedrock → 최종 답변 텍스트.

    **clean dir 에서 실행**(repo CLAUDE.md/AGENTS.md 미로드) + `--system-prompt`(build_system_prompt 가 *유일* 통제,
    Claude Code 기본 프롬프트 대체) + Bedrock env 주입(`bedrock_author_env`). 모델 = ANTHROPIC_MODEL(env).
    certifier(`codex exec`)와 대칭 — 둘 다 별도 프로세스 + clean dir + stdin 닫음.

    `recorder`(옵션, 기본 None) — 주어지면 봉투의 정확한 total_cost_usd 를 기록(`UsageRecorder`).
    role/권한을 모르는 순수 비용 sink — 이 함수는 recorder 가 *무엇을 위한 것인지* 모른다(신뢰 경계).
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
    if recorder is not None:
        recorder.add(_extract_claude_cost(proc.stdout))
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


def _extract_claude_cost(stdout: str) -> float:
    """`claude -p --output-format json` 봉투의 total_cost_usd(정확한 실비용). 봉투 아니면 0.0."""
    try:
        obj = json.loads(stdout)
    except (ValueError, TypeError):
        return 0.0
    if isinstance(obj, dict):
        v = obj.get("total_cost_usd")
        if isinstance(v, (int, float)):
            return float(v)
    return 0.0


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


def _to_draft_card(source_id: str, title: str, data: dict) -> DraftCard:
    """파싱된 dict → DraftCard. **headline = 기사 원제목(title)** — author 는 제목을 안 만든다(사실층 앵커).
    claim_type 은 두 허용값으로 정규화(미상 → arithmetic — 계약 '애매하면 arithmetic')."""
    claims = tuple(
        Claim(
            id=str(c["id"]),
            text=str(c["text"]),
            claim_type="entailment" if str(c.get("claim_type")) == "entailment" else "arithmetic",
            importance="core" if str(c.get("importance")) == "core" else "supporting",
        )
        for c in data.get("claims", [])
    )
    return DraftCard(
        source_id=source_id,
        headline=title,                                    # 기사 원제목(사실층 앵커) — data 의 headline 은 무시
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
