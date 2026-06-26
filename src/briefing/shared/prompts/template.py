"""prompt 템플릿 로더 — .md 템플릿 로드 + 브레이스-안전 변수 주입.

(aws-samples/sample-deep-insight 의 `prompts/template.py` 패턴 차용 — 단 footgun 회피.)
그들은 `str.format(**ctx)` 로 `{VAR}` 를 치환하지만, 그러면 *임의 내용*(기사 원문·코드·JSON)에 든
리터럴 `{`/`}` 가 파이프라인을 깬다(KeyError/ValueError). 우리는 **`string.Template`($VAR)+safe_substitute** 로:
- 리터럴 `{`·`}`·미상 `$var` 는 *그대로* 둠(크래시 없음).
- **큐레이션된 변수(CURRENT_DATE 등)만** 주입. *source 원문은 템플릿에 넣지 않는다* — claude -p 의 user prompt 인자로 별도.
"""
from __future__ import annotations

import string
from pathlib import Path

_PROMPTS_DIR = Path(__file__).parent


def load_template(name: str) -> str:
    """`{name}.md` 템플릿 로드(이 디렉토리 기준). 없으면 FileNotFoundError(시끄럽게)."""
    return (_PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")


def render(template: str, **vars: str) -> str:
    """브레이스-안전 변수 주입 — `string.Template`($VAR, safe_substitute).

    리터럴 `{`·`}` 와 미상 `$var` 는 그대로 둔다(footgun 회피).
    ⚠️ **변하는 값(날짜 등)은 여기 넣지 말 것** — system 프롬프트는 *캐시 프리픽스*라 static 유지해야
       prompt caching 이 산다. volatile 값은 user 메시지로 → author.build_user_prompt().
    """
    return string.Template(template).safe_substitute(vars)


def apply_prompt_template(name: str, **vars: str) -> str:
    """load_template + render (Deep Insight 의 apply_prompt_template 역할, 단 브레이스-안전·static)."""
    return render(load_template(name), **vars)
