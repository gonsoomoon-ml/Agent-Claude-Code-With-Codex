"""author — Claude Code headless(`claude -p`) 작성자. 개인화 = base 계약(고정) + lens + per-user skill.md.

설계 = **Design B** (design/architecture/four-component-analysis.md): **author = `claude -p`** (별도 하니스).
- **Skill 이 author 의 유일 레버**(개인화 워크플로) — "왜 두 하니스인가"의 답. Strands 는 author 가 아니다(fabric 전담, 요약 금지).
- Bedrock 라우팅은 *호출 env* 가 소유(claude 기본 설정엔 없음): `CLAUDE_CODE_USE_BEDROCK=1` · `ANTHROPIC_MODEL=AUTHOR_MODEL_ID` · `AWS_REGION`. (headless on Bedrock = 스모크 검증됨.)
- author 는 *동결본 read 만*(자기 source originate 금지). 자기 채점 금지 — certifier 직접 호출 안 함(gate 가 함).
- 출력 = 카드별 {headline, summary, why_it_matters, claims[]}; claims 는 원자적(검증 단위).
- *근접-중복 클러스터링(thread-identity)은 상류 fabric 관심* — draft_card 는 *대표 동결본 1건* 당.
  (정확 중복은 source_store 해시가 처리; 근접 중복은 미구현 orphan.)
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date

from .config import Settings, UserConfig
from .prompts import apply_prompt_template
from .source_store import FrozenSource


@dataclass(frozen=True)
class Claim:
    id: str
    text: str
    claim_type: str  # "entailment" | "arithmetic"


@dataclass(frozen=True)
class DraftCard:
    source_id: str
    headline: str
    summary: str
    why_it_matters: str       # PROFILE(역할·관심)에 묶인 영향 — 가장 검증이 필요한 줄
    claims: tuple[Claim, ...]


def bedrock_author_env(settings: Settings) -> dict[str, str]:
    """`claude -p` 를 Bedrock 로 라우팅하는 env (스모크 테스트로 검증된 조합).

    claude 의 기본 설정엔 Bedrock 라우팅이 없으므로 *호출 시* 주입한다(codex 가 자기 config 로 상주하는 것과 대조).
    """
    return {
        **os.environ,
        "CLAUDE_CODE_USE_BEDROCK": "1",
        "ANTHROPIC_MODEL": settings.author_model_id,   # inference-profile prefix (global./us.)
        "AWS_REGION": settings.region,
        "ENABLE_TOOL_SEARCH": "false",                 # Bedrock 가 tool def 선로드(MCP 사용 시 필수)
    }


def build_system_prompt(*, lens_guidance: str, skill_md: str) -> str:
    """author *system* 프롬프트 (= prompt-caching 프리픽스) = base(author_system.md, static) + lens + skill.

    ★ **static 유지** — 변하는 값(날짜·source)은 여기 *안* 넣는다(캐시 hit 보존). 날짜·원문 = build_user_prompt().
    lens·skill 은 raw 연결(템플릿 치환 X) — 사용자 내용에 `{`·`}`·`$` 가 있어도 안전.
    """
    parts = [apply_prompt_template("author_system")]  # static base (변수 없음)
    if lens_guidance.strip():
        parts.append("## 요약 관점(lens)\n" + lens_guidance.strip())
    if skill_md.strip():
        parts.append("## 독자 개인화(skill)\n" + skill_md.strip())
    return "\n\n".join(parts)


def build_user_prompt(source: FrozenSource, *, today: str | None = None) -> str:
    """claude -p 의 *user 메시지* (= 캐시 안 되는 동적 turn) = 오늘 날짜 + 동결 원문 + 지시.

    날짜·source 같은 *변하는 내용*은 여기(캐시 프리픽스 밖)에 둔다 → system 캐싱 보존.
    source.text 는 f-string 삽입(템플릿 치환 X)이라 브레이스 안전.
    """
    today = today or date.today().isoformat()
    return (
        f"오늘 날짜: {today} (상대 날짜는 이 기준; 원문에 없는 날짜 생성 금지).\n\n"
        f"다음 동결 원문을 요약하고 원자적 claims 를 추출하라:\n\n{source.text}"
    )


def draft_card(source: FrozenSource, user: UserConfig, settings: Settings) -> DraftCard:
    """동결본 1건 → `claude -p`(base + lens + skill) → 초안 카드 + 원자적 claims.

    프롬프트 = **system(캐시 프리픽스, static)** build_system_prompt(lens_guidance=…, skill_md=user.skill_md)
             + **user(동적, 캐시 X)** build_user_prompt(source)  ← 날짜+원문.
    ★ certifier 는 lens·skill 을 절대 안 본다(불변식 #4). source 는 user turn(템플릿 X) → 브레이스 안전.
      대략: subprocess.run(["claude","-p","--system-prompt", build_system_prompt(...),
                     "--output-format","json", build_user_prompt(source)], env=bedrock_author_env(settings)).
    """
    raise NotImplementedError("claude -p author (base + lens + skill) — 구현 예정")


def revise_claims(
    source: FrozenSource,
    user: UserConfig,
    settings: Settings,
    *,
    prior: DraftCard,
    failed_ids: tuple[str, ...],
) -> DraftCard:
    """Maker-Checker 재도출 — 실패한 claim(`failed_ids`)만 source 에서 다시 도출 (gate 가 호출).

    ★ decorrelation 보존: 피드백 = `failed_ids`(*어떤* claim 이 검증 실패했는지)만 — certifier 의 *이유/정답* 은 안 줌.
    author 는 source(이미 가진 동결본)를 다시 읽어 그 claim 들을 재도출; 통과 claim 은 유지(thrashing 방지).
    이렇게 라운드 간에도 author 가 certifier 를 *흉내내지* 못함('teaching to the test' 회피).
    """
    raise NotImplementedError("claude -p revise (실패 claim 재도출, 최소 피드백) — 구현 예정")
