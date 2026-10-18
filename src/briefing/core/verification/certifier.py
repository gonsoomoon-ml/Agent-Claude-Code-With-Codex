"""certifier — Codex(`codex exec`) 독립 인증자. 최소 컨텍스트, BLOCK권만.

불변식 (design/architecture/four-component-analysis.md §6):
- **gate 가 호출** (author 아님). certifier 는 *tool-starved* — 화이트리스트 4필드 envelope 만 받음:
  {source_excerpt, claim_text, claim_type, schema}. narration/reasoning/confidence 는 *존재 자체* 금지.
- 다른 모델 계열(decorrelation) + 결정론 코어(산술=샌드박스 코드, 함의=`codex exec`).
- certifier 모델은 **codex 자신의 설정**(`~/.codex/config.toml`: model_provider=amazon-bedrock, model)이 소유 —
  우리 .env 가 아님. certify() 는 *사용된 모델 출처를 결과에 기록*(provenance)만 하고 설정하지 않는다.

옵션 B (all-Strands 런타임 + subprocess certifier): author/큐레이션이 Strands 라도 **certifier 는 별도 프로세스**
로 남아 *물리* 격리 + cross-family 를 보존한다. 이 모듈은 envelope *외* 어떤 author 산출도 받지 않는다(누설 0).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import tomllib
from dataclasses import dataclass, field
from typing import Literal

from .. import _debug
from . import numeric

Verdict = Literal["VERIFIED", "DEMOTED", "BLOCKED"]

# `codex exec` 명령 — codex 는 모델을 자기 config 로 소유(우리가 안 정함). 환경별로 플래그 조정 가능한 seam.
# --skip-git-repo-check: clean(비-git) dir 에서 실행하므로 필수(decorrelation 격리의 대가).
# --json: 이벤트 줄로 받아 최종 답과 토큰 사용량을 함께 읽는다(F5 — 비용 실측). 입력(envelope)은 그대로.
_CODEX_CMD: tuple[str, ...] = ("codex", "exec", "--skip-git-repo-check", "--json")
_CODEX_TIMEOUT_S = 120

# 숫자 토큰(천단위 콤마·소수·퍼센트 허용) — 산술 결정론 재도출용.
_NUM_RE = re.compile(r"\d[\d,]*(?:\.\d+)?%?")

# 서수를 원문의 *맨숫자* 로 정당화해 주는 하한 — 아래 _certify_arithmetic 참조.
_ORD_NUMERIC_MIN = 10


@dataclass(frozen=True)
class Envelope:
    """certifier 에 주는 *유일* 입력 (화이트리스트 4필드)."""
    source_excerpt: str
    claim_text: str
    claim_type: str
    schema: str


@dataclass(frozen=True)
class CertVerdict:
    claim_id: str
    verdict: Verdict
    evidence: str    # certifier 가 가리킨 원문 근거 구절
    # 검증 출처 provenance: "deterministic"(산술) | "deterministic→codex"(산술이 막고 codex 2차 판정이 확인)
    #                      | "codex"(함의) | "codex-error"(폴백)
    model: str = ""
    # codex 토큰 사용량(turn.completed.usage) — 그 run 의 비용 기록용(F5). 비교·캐시 형식에서는 뺀다.
    usage: dict = field(default_factory=dict, compare=False, repr=False)


def certify(claim_id: str, envelope: Envelope) -> CertVerdict:
    """envelope 1건 → per-claim verdict. **claim_type 으로 디스패치**("결정론 게이트=신뢰" 헤드라인).

    - `arithmetic` → **결정론 코드**(source 에서 숫자 재추출·대조, byte-stable) — verdict 가 LLM 이 아니라 *코드*.
      코드가 BLOCKED 면 codex 2차 판정(`_second_opinion`)을 한 번 더 받는다 — 단 뒤집힌 한국어 분수는 코드가 최종.
    - `entailment` → **`codex exec`**(다른 계열, clean dir, envelope-only) — fail-closed.
    불변식: ① envelope 4필드 *외* 아무것도 codex 프롬프트에 안 넣음(누설 0 — `_build_codex_prompt` 가 강제),
            ② **codex 는 clean dir 에서 실행** — repo `CLAUDE.md`/`AGENTS.md` 자동 로드 금지(decorrelation).
    """
    if envelope.claim_type == "arithmetic":
        det = _certify_arithmetic(claim_id, envelope)
        if det.verdict != "BLOCKED" or numeric.inverted_ko_fraction(envelope.claim_text):
            return det
        return _second_opinion(claim_id, envelope, det)
    return _certify_entailment(claim_id, envelope)


def _second_opinion(claim_id: str, envelope: Envelope, det: CertVerdict) -> CertVerdict:
    """숫자 검사가 막은 claim 을 codex 에게 한 번 더 판정받는다(F2, 2026-10-18).

    **왜:** 숫자가 말로 쓰인 같은 뜻('Pope Leo XIV'↔'레오 14세'·'the year before'(2025)↔'2024년'·나열한 이름 수)은
    코드가 원리적으로 못 본다. 30일 운영에서 숫자 검사가 막은 claim 64건 중 숫자가 틀린 것은 0건이었다.
    codex 는 같은 envelope 만 본다 — 코드 판정은 보여주지 않는다(독립성; 보여주면 그쪽으로 기운다).
    숫자 claim 이라 codex 지시에는 '같은 값만 인정' 엄격 규칙이 붙는다(`_NUMERIC_RULES`).
    codex 가 VERIFIED 일 때만 통과, DEMOTED(판단 불가)·BLOCKED·오류는 코드 판정대로 BLOCKED(fail-closed).
    """
    v = _certify_entailment(claim_id, envelope)
    if v.verdict == "VERIFIED":
        return CertVerdict(claim_id, "VERIFIED", f"{det.evidence} → codex 확인: {v.evidence}",
                           "deterministic→codex", v.usage)
    return CertVerdict(claim_id, "BLOCKED", f"{det.evidence} · codex {v.verdict}: {v.evidence}",
                       "deterministic", v.usage)


# ───────────────────────── 산술: 결정론 재도출 (LLM 아님, byte-stable) ─────────────────────────

def _numbers(text: str) -> set[str]:
    """숫자 토큰을 정규화(콤마 제거)해 집합으로. '417,166,008'→'417166008', '45%'→'45%'.

    ★ *라우팅*용 표층 스캔(gate.reroute_claim_types·_interp_lint 와 공유) — 검증 대조는
    `numeric.scan`(값 기반)이 한다. 이 둘을 섞지 말 것: 여기서 '8' 이 안 보인다고 BLOCK 하면
    영어 원문의 'eight' 를 놓친다(= 2026-07-17 이전의 위양성 100%).
    """
    return {m.group().replace(",", "") for m in _NUM_RE.finditer(text)}


def _certify_arithmetic(claim_id: str, envelope: Envelope) -> CertVerdict:
    """source 에서 수치를 재추출해 claim 의 수치와 **값으로** 대조 (byte-stable, 다른 모델 불필요).

    ★ **문자열이 아니라 값을 비교한다** — 원문은 영어("eight months"·"four trillion"·"October"),
    claim 은 한국어("8개월"·"4조"·"10월")라 표층 대조는 원리적으로 실패한다(2026-07-17 실측:
    BLOCKED 243/243 전부 이 위양성). 정규화·자릿수 보존은 `numeric.scan` 이 담당.

    정책(fail-closed, *절대 거짓 VERIFIED 금지*):
      - claim 의 모든 수치가 source 에 (값으로) 있음 → VERIFIED.
      - 수량·월·서수가 source 에 없음 → **BLOCKED**(날조 가능성 — 자동 발행 금지).
      - 퍼센트만 없음 → **DEMOTED**(원문 수치에서 *파생*됐을 수 있음 — '(미확인)' 라벨로 남김).
    한계(v1): 공식 재계산(45% = 417M/926M)은 안 함 — 값 *존재* 대조까지. (formula 재계산은 후속.)
    """
    claim = numeric.scan(envelope.claim_text)
    if claim.empty():
        return CertVerdict(claim_id, "DEMOTED", "검증할 숫자 토큰이 claim 에 없음", "deterministic")
    src = numeric.scan(envelope.source_excerpt)
    # 네임스페이스별로 대조 — 월 7('July')이 수량 7 을 정당화하면 안 된다(numeric 불변식).
    # 문맥 숫자('100만 개당'·'3배'·'2위'·'2분기')는 원문 values *또는* 같은 문맥 칸('per million'·'triple'·
    # 'ranks second'·'the second quarter')으로 확인한다(F2). 넓히기만 한다 — 지금 values 로 통과하던 것은 그대로,
    # 문맥 칸은 같은 문맥의 숫자만 인증한다('per million' 이 '100만 달러'를 인증하면 안 된다 — SY09).
    missing = {v for v in claim.plain if not numeric.contains(v, src.values)}
    for kind, vals in claim.ctx.items():
        pool = src.values | src.ctx.get(kind, set())
        missing |= {v for v in vals if not numeric.contains(v, pool)}
    missing_val = sorted(missing)
    missing_mon = sorted(m for m in claim.months if m not in src.months)
    # 서수는 원문의 서수로 정당화된다. 예외: **큰 수(≥_ORD_NUMERIC_MIN)** 는 원문의 맨숫자도 인정 —
    # 한국어 '제109조'(법조문)·'제3차'류를 영어 원문은 'Article 109' 로 쓴다(실측).
    # ★ 작은 서수까지 수량으로 정당화하면 원문의 흔한 수사가 없는 서수를 인증한다:
    #   'one of three co-chairs'(수량 3)가 '제3자 감사'(서수 3)를 VERIFIED 로 만든다(적대 검증에서 실증).
    #   법조문 번호는 실질적으로 두 자리 이상이라 이 하한이 동치는 지키고 누수는 막는다.
    missing_ord = sorted(o for o in claim.ordinals
                         if o not in src.ordinals
                         and not (o >= _ORD_NUMERIC_MIN and numeric.contains(float(o), src.values)))
    missing_pct = sorted(p for p in claim.percents if not numeric.contains(p, src.percents))
    if not (missing_val or missing_mon or missing_ord or missing_pct):
        return CertVerdict(claim_id, "VERIFIED", "claim 의 모든 수치가 원문에 존재(값 대조)", "deterministic")
    if missing_val or missing_mon or missing_ord:
        detail = ", ".join(
            f"{label}={vals}" for label, vals in
            (("수량", missing_val), ("월", missing_mon), ("서수", missing_ord)) if vals
        )
        return CertVerdict(claim_id, "BLOCKED", f"원문에 없는 수치: {detail}", "deterministic")
    return CertVerdict(claim_id, "DEMOTED", f"원문에 없는 퍼센트(파생 추정): {missing_pct}", "deterministic")


# ───────────────────────── 함의: codex exec (다른 계열, clean dir, envelope-only) ─────────────────────────

# 숫자 claim(codex 2차 판정) 전용 엄격 지시 — codex 는 '논리적으로 뒷받침되나'를 봐서 숫자에 관대했다(실측):
# 근사('약 12'≈11)·범위 함의('800k까지'⟹'70만까지')·잘못 쓴 숫자의 선의 해석·괄호 속 영어 숫자만 대조(10배 오류 통과).
# 이 지시로 그 유형은 두 모델(GPT-5.5·Luna) 모두 전부 잡았다. ★예시 숫자는 측정 사례와 다르게 둔다(시험 유출 방지).
_NUMERIC_RULES = (
    "The claim contains numbers. Check EVERY number in it (counts, amounts, dates, years, ranks, fractions, "
    "ratios, and numbers inside parentheses) against the excerpt. A number is supported only if the excerpt "
    "gives the SAME value, possibly written another way: in words instead of digits, in another language or "
    "scale word (e.g. '1.2 billion' = 12억, '250k' = 25만), through a unit conversion (e.g. 'half a day' = 12시간), "
    "as an ordinal or rank (e.g. 'finished third' = 3위), relative to another value the excerpt states "
    "(e.g. 'two years after 2020' = 2022), or as the number of items the excerpt explicitly lists.\n"
    "NOT supported: a nearby or rounded different value (e.g. 'about 50' when the excerpt says 48); a value "
    "that only follows from a bound (e.g. 'within 10 days' or 'by May 31' when the excerpt says 'within 7 days' "
    "or 'by May 15'); a malformed number read charitably. In Korean, 'N분의 M' means M/N (e.g. '4분의 3' = 0.75, "
    "but '3분의 4' = 1.33). If the claim states one quantity twice (e.g. a Korean number with an English one in "
    "parentheses), both must match the excerpt.\n"
    "If any number is not supported in this strict sense, do NOT answer VERIFIED: answer BLOCKED when the "
    "excerpt gives a different value, otherwise DEMOTED.\n"
)


def _build_codex_prompt(envelope: Envelope) -> str:
    """envelope 4필드 *만* 으로 certify 프롬프트 조립 — narration/lens/skill/user 등 누설 0 (구조적 강제).

    source_excerpt + claim_text + schema 를 쓰고, claim_type 은 판정 기준을 고르는 데만 쓴다(숫자 claim 이면
    `_NUMERIC_RULES` 추가 — codex 2차 판정 경로). 외부 지식 금지 지시.
    """
    return (
        "You are an independent verifier. Using ONLY the source excerpt below, decide whether it "
        "ENTAILS the claim. Do not use any outside knowledge. If the excerpt does not clearly support "
        "the claim, do NOT verify it.\n"
        + (_NUMERIC_RULES if envelope.claim_type == "arithmetic" else "")
        + f"Respond with ONE JSON object and nothing else, matching this schema: {envelope.schema}\n"
        "verdict ∈ {VERIFIED (excerpt entails claim), DEMOTED (not determinable from excerpt), "
        "BLOCKED (excerpt contradicts claim)}.\n\n"
        f"<source_excerpt>\n{envelope.source_excerpt}\n</source_excerpt>\n\n"
        f"<claim>\n{envelope.claim_text}\n</claim>\n"
    )


def _run_codex(prompt: str, *, timeout: int = _CODEX_TIMEOUT_S) -> str:
    """`codex exec` 를 **clean(빈) dir** 에서 실행 → stdout. 빈 dir = AGENTS.md/CLAUDE.md 자동 로드 0(decorrelation).

    codex 는 자기 `~/.codex/config.toml` 로 모델/provider 를 소유 — env 로 안 주입. 실패는 호출자가 fail-closed 처리.
    """
    _debug.dprint("certifier → codex exec", f"clean dir · prompt({len(prompt)}c) · timeout={timeout}s")
    clean_dir = tempfile.mkdtemp(prefix="certify-clean-")  # 빈 dir → repo 컨텍스트 미상속
    t0 = time.monotonic()
    try:
        proc = subprocess.run(
            [*_CODEX_CMD, prompt],
            cwd=clean_dir,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ},
            stdin=subprocess.DEVNULL,  # 프롬프트는 argv 로 — codex 가 stdin 대기하지 않게 닫음
            check=False,
        )
    finally:
        shutil.rmtree(clean_dir, ignore_errors=True)
    _debug.dprint("certifier ⊣ codex exec",
                  f"rc={proc.returncode} · {int((time.monotonic() - t0) * 1000)}ms · stdout={len(proc.stdout)}c", "dim")
    if proc.returncode != 0:
        raise RuntimeError(f"codex exec rc={proc.returncode}: {proc.stderr.strip()[:200]}")
    return proc.stdout


def _parse_codex_events(stdout: str) -> tuple[str, dict]:
    """`codex exec --json` 이벤트 줄 → (마지막 agent_message 텍스트, 마지막 turn.completed usage).

    최종 답 이벤트가 없으면 stdout 전체를 돌려준다(평문 출력·오류 — 호출자의 `_last_json_object` 가 fail-closed 로 처리).
    0.142.2·0.163.0 실제 출력으로 검증한 실험 U3 파서와 같은 규칙(tests/fixtures/codex_json_sample_*.jsonl).
    """
    final, usage = None, {}
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        item = event.get("item")
        if event.get("type") == "item.completed" and isinstance(item, dict) and item.get("type") == "agent_message":
            final = item.get("text")
        elif event.get("type") == "turn.completed":
            usage = event.get("usage") or {}
    return (final if isinstance(final, str) else stdout), usage


def codex_model_id() -> str:
    """codex 가 쓰는 검증 모델 id — codex 자신의 설정(`$CODEX_HOME` 또는 `~/.codex` 의 config.toml)의 `model`.

    우리는 정하지 않고 읽기만 한다(비용 단가를 고르는 데만 쓴다). 못 읽으면 빈 문자열.
    """
    home = os.environ.get("CODEX_HOME") or os.path.join(os.path.expanduser("~"), ".codex")
    try:
        with open(os.path.join(home, "config.toml"), "rb") as f:
            return str(tomllib.load(f).get("model", ""))
    except (OSError, ValueError):   # 파일 없음·TOML 오류(TOMLDecodeError 는 ValueError)
        return ""


def _last_json_object(text: str) -> dict | None:
    """noisy stdout 에서 *마지막으로 파싱되는* JSON object 추출 (codex 로그/추론 뒤의 최종 답)."""
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


def _certify_entailment(claim_id: str, envelope: Envelope) -> CertVerdict:
    """함의 — `codex exec`(다른 계열, clean dir, envelope-only). **fail-closed: 오류·미상은 절대 VERIFIED 아님.**

    cross-lingual(영어 원문 ↔ 한국어 claim)도 envelope 에 둘 다 담아 codex 가 직접 판정.
    참고: gpt-oss 류는 reasoningContent 뒤에 text 블록을 반환 → `_last_json_object` 로 마지막 JSON 흡수.
    """
    prompt = _build_codex_prompt(envelope)
    try:
        stdout = _run_codex(prompt)
    except Exception as exc:  # noqa: BLE001 — 어떤 실패든 보수적으로 (fail-closed)
        return CertVerdict(claim_id, "DEMOTED", f"certifier 미가용(보수적 미확인): {exc}", "codex-error")
    text, usage = _parse_codex_events(stdout)
    obj = _last_json_object(text)
    if obj is None:
        return CertVerdict(claim_id, "DEMOTED", "certifier 출력 파싱 불가(보수적 미확인)", "codex", usage)
    verdict = str(obj.get("verdict", "")).upper()
    if verdict not in ("VERIFIED", "DEMOTED", "BLOCKED"):
        return CertVerdict(claim_id, "DEMOTED", f"미상 verdict: {verdict!r}", "codex", usage)
    evidence = str(obj.get("evidence", ""))[:500]
    return CertVerdict(claim_id, verdict, evidence, "codex", usage)  # type: ignore[arg-type]
