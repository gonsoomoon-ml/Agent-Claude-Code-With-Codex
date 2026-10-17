"""판정자(LLM-as-judge) — Bedrock Converse 클라이언트, 한국어 판정 프롬프트, 스키마 파서, 판정자 검증, 대체 규칙(설계 §8, §14-3).

판정자는 발행 경로 밖의 측정 도구라 codex 를 거치지 않고 Converse 로 직접 부른다(호출당 하니스 토큰 0).
요약 후보가 모두 Claude 이므로 판정자는 다른 계열(GPT)이고, 판정이 갈리면 제3계열이 가린다.
파서는 스키마를 어기면 ValueError — converse_json 이 오류 문구를 덧붙여 1회 재시도한다.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable

from briefing.core.verification.certifier import _last_json_object

from .metrics import split_sentences

JUDGES = {"astra": "us.openai.gpt-6-astra", "sol61": "global.openai.gpt-6.1-sol"}
THIRD = {"grok": "global.xai.grok-4.7", "kimi": "global.moonshotai.kimi-k3", "glm": "global.zai.glm-5.3",
         "nova": "us.amazon.nova-premier-v1:0"}
_WINNER_TO_JUDGE = {"gpt-6-astra": "astra", "gpt-6.1-sol": "sol61"}

KEYFACT_CATEGORIES = ("새 사실", "수치", "변화", "단서", "배경", "발언")
FIDELITY_LABELS = ("부풀림-범위", "부풀림-단계", "부풀림-한정어", "부풀림-인과", "부풀림-권고", "부풀림-확신도",
                   "지나친 흐림", "귀속 누락", "의견→사실", "인용 불일치", "사실 오류")
DETECTION_MIN = 0.80
FALSE_FLAG_MAX = 0.10
_OMISSION = "뒤쪽 사실 삭제"


@dataclass
class JudgeCall:
    obj: dict | None
    raw: str
    usage: dict
    latency_ms: int
    error: str | None


@dataclass
class KeyFact:
    id: str
    text: str
    quote: str
    position: float | None
    tercile: str | None
    category: str
    ai_related: bool


@dataclass
class PlantedSummary:
    item_id: str
    source_id: str
    summary: str
    defect: str | None
    sentence_idx: int | None
    removed_fact: str | None


@dataclass
class JudgeGate:
    detection: float
    false_flag_rate: float
    passed: bool


class GateStop(Exception):
    """판정자 검증에서 쓸 수 있는 GPT 판정자가 없다 — 채점(유료)을 시작하지 않고 사용자에게 묻는다."""


def _bedrock():
    import boto3

    return boto3.client("bedrock-runtime", region_name="us-east-1")


def _call(client, model_id: str, system: str, user: str, max_tokens: int) -> tuple[str, dict, int]:
    resp = client.converse(modelId=model_id, system=[{"text": system}],
                           messages=[{"role": "user", "content": [{"text": user}]}],
                           inferenceConfig={"maxTokens": max_tokens})
    text = "".join(b["text"] for b in resp["output"]["message"]["content"] if "text" in b)
    return text, resp.get("usage") or {}, int((resp.get("metrics") or {}).get("latencyMs", 0))


def converse_json(model_id: str, system: str, user: str, *, max_tokens: int = 4000, client=None,
                  validate: Callable[[dict], object] | None = None) -> JudgeCall:
    """JSON 하나를 받는다. JSON 이 없거나 validate 가 ValueError 면 오류 문구를 덧붙여 1회 재시도."""
    client = client or _bedrock()
    usage: dict = {}
    latency, raw, err = 0, "", None
    prompt = user
    for _ in range(2):
        try:
            raw, u, ms = _call(client, model_id, system, prompt, max_tokens)
        except Exception as exc:                                   # 쓰로틀·네트워크 — 1회 재시도 후 기록
            err = f"호출 실패: {exc}"
            prompt = user
            continue
        latency += ms
        for k, v in u.items():
            usage[k] = usage.get(k, 0) + v
        obj = _last_json_object(raw)
        if obj is None:
            err = "JSON object 없음"
        else:
            try:
                if validate:
                    validate(obj)
                return JudgeCall(obj, raw, usage, latency, None)
            except ValueError as exc:
                err = f"스키마 위반: {exc}"
        prompt = f"{user}\n\n[이전 응답 오류: {err}] 설명 없이 JSON object 하나만, 지정한 스키마를 지켜 다시 출력하라."
    return JudgeCall(None, raw, usage, latency, err)


# ── 프롬프트 ──
_GROUND = "판단 근거는 아래 원문뿐이다. 배경지식으로 보충하지 마라. 설명 없이 JSON object 하나만 출력한다."

_KEYFACTS_SYS = f"""너는 뉴스·블로그 요약 평가를 위한 '핵심 사실 목록'을 만드는 평가자다. {_GROUND}
원문을 읽고, 이 글을 요약할 때 담겨야 할 핵심 사실을 원자 단위(사실 하나, 등장 주체 2–3개 이하)로 5–15개 뽑아라.
category 는 다음 중 하나: 새 사실(무엇이 새로 발표·출시·변경됐나와 그 주체), 수치(성능·가격·규모·시점·이용 조건),
변화(이전 대비 달라진 점), 단서(유보·반론·한계·미해결 쟁점), 배경, 발언(누가 무엇을 말했나).
quote 는 그 사실의 근거가 되는 원문 구절을 글자 그대로 20–80자 옮긴 것이다(번역·요약 금지).
ai_related 는 그 사실이 AI(모델·에이전트·학습·추론 등)에 관한 것인지다.
스키마: {{"facts": [{{"id": "K1", "text": "한국어 한 문장", "quote": "원문 그대로", "category": "...", "ai_related": true}}]}}"""

_REVIEW_SYS = f"""너는 핵심 사실 목록을 검토하는 평가자다. {_GROUND}
목록에서 빠진 중요한 사실, 둘로 나눠야 할 사실, 원문과 다른 사실을 지적하라. 문제가 없으면 빈 목록을 낸다.
스키마: {{"missing": ["…"], "split": ["K3"], "wrong": ["K5"]}}"""

_ALIGN_SYS = f"""너는 요약이 핵심 사실을 담았는지 판정하는 평가자다. {_GROUND}
각 핵심 사실(id)에 대해 요약이 그 사실을 담았으면 true, 아니면 false 를 준다. 부분적으로만 담았으면 false 다.
또한 요약의 첫 문장(0번)이 이 글에서 새로 일어난 단 하나의 사실(주체+행위)을 진술하는지 first_sentence_is_new_fact 로 답한다.
스키마: {{"covered": {{"K1": true, "K2": false}}, "first_sentence_is_new_fact": true}}"""

_FIDELITY_SYS = f"""너는 요약이 원문의 뜻을 그대로 옮겼는지 문장 단위로 판정하는 평가자다. {_GROUND}
문제가 있는 문장만 idx(0부터)로 적고, labels 는 아래에서 고른다. 문제가 없는 문장은 적지 않는다.
- 부풀림-범위: 특정 벤치마크·조건·대상·기간의 결과를 일반화했다
- 부풀림-단계: 발표·계획·프리뷰·베타·발의·소송 제기를 출시·시행·판결 등 다음 단계로 올렸다
- 부풀림-한정어: '최대·약·이상·이하·평균·일부'를 뺐다
- 부풀림-인과: 원문이 연관으로 쓴 관계를 인과로 썼다
- 부풀림-권고: 원문이 보고한 결과를 '~해야 한다'는 권고로 바꿨다
- 부풀림-확신도: 원문의 가능·추정·유보를 단정으로 바꿨다
- 지나친 흐림: 원문이 단정한 것을 '~로 보인다·~할 전망' 등으로 약하게 썼다
- 귀속 누락: 원문이 누군가의 말·주장으로 쓴 것을 요약이 사실처럼 썼다
- 의견→사실: 의견·한쪽 입장을 사실처럼 썼다
- 인용 불일치: 따옴표 안 문구가 원문(또는 그 정확한 번역)과 다르다
- 사실 오류: 수치·날짜·주체·대상 등이 원문과 다르거나, 원문에 없는 내용을 썼다
evidence 에는 근거가 되는 원문 구절을 짧게 옮긴다.
스키마: {{"sentences": [{{"idx": 0, "labels": ["귀속 누락"], "evidence": "원문 구절"}}]}}"""

_BYPASS_SYS = """너는 '확인 목록'이 요약의 사실을 빠짐없이 덮는지 판정하는 평가자다.
요약 문장들과 확인 목록(claims)을 비교해, 요약에 진술됐지만 어떤 claim 으로도 덮이지 않는 사실을 한국어 짧은 구절로 나열하라.
숫자·날짜·고유명사는 따로 검사하므로 그 외의 사실(무엇을 했나, 단계, 귀속, 단서)에 집중한다. 모두 덮이면 빈 목록이다.
설명 없이 JSON object 하나만 출력한다. 스키마: {"uncovered": ["…"]}"""

_PAIRWISE_SYS = f"""너는 같은 기사의 두 요약 중 어느 쪽이 독자에게 더 나은지 고르는 평가자다. {_GROUND}
기준(중요한 순서): 원문의 뜻을 그대로 옮겼나(부풀림·지나친 흐림·귀속 누락이 없나) → 중요한 사실을 담았나 → 짧고 읽기 쉬운가.
유보 표현이 있다는 이유만으로 불리하게 보지 마라. 원문에 유보가 있으면 유보를 지킨 쪽이 낫다.
스키마: {{"better": "first" | "second" | "tie", "reason": "한 문장"}}"""


def _numbered(sentences: list[str]) -> str:
    return "\n".join(f"[{i}] {s}" for i, s in enumerate(sentences))


def keyfacts_messages(source_text: str) -> tuple[str, str]:
    return _KEYFACTS_SYS, f"<원문>\n{source_text}\n</원문>"


def review_messages(source_text: str, facts: list[KeyFact]) -> tuple[str, str]:
    listing = "\n".join(f"{f.id} ({f.category}): {f.text}" for f in facts)
    return _REVIEW_SYS, f"<원문>\n{source_text}\n</원문>\n\n<핵심 사실 목록>\n{listing}\n</핵심 사실 목록>"


def align_messages(source_text: str, facts: list[KeyFact], sentences: list[str]) -> tuple[str, str]:
    listing = "\n".join(f"{f.id}: {f.text}" for f in facts)
    return _ALIGN_SYS, (f"<원문>\n{source_text}\n</원문>\n\n<핵심 사실>\n{listing}\n</핵심 사실>\n\n"
                        f"<요약 문장>\n{_numbered(sentences)}\n</요약 문장>")


def fidelity_messages(source_text: str, sentences: list[str]) -> tuple[str, str]:
    return _FIDELITY_SYS, f"<원문>\n{source_text}\n</원문>\n\n<요약 문장>\n{_numbered(sentences)}\n</요약 문장>"


def bypass_messages(sentences: list[str], claims: list[str]) -> tuple[str, str]:
    listing = "\n".join(f"- {c}" for c in claims)
    return _BYPASS_SYS, f"<요약 문장>\n{_numbered(sentences)}\n</요약 문장>\n\n<확인 목록>\n{listing}\n</확인 목록>"


def pairwise_messages(source_text: str, first: str, second: str) -> tuple[str, str]:
    return _PAIRWISE_SYS, f"<원문>\n{source_text}\n</원문>\n\n<첫째 요약>\n{first}\n</첫째 요약>\n\n<둘째 요약>\n{second}\n</둘째 요약>"


# ── 파서(스키마를 어기면 ValueError) ──
def parse_keyfacts(obj: dict, source_text: str) -> list[KeyFact]:
    facts = obj.get("facts")
    if not isinstance(facts, list) or not facts:
        raise ValueError("facts 가 비었거나 목록이 아님")
    out, ids = [], set()
    for f in facts:
        fid, cat = f.get("id"), f.get("category")
        if not fid or fid in ids or not f.get("text") or cat not in KEYFACT_CATEGORIES or not isinstance(f.get("ai_related"), bool):
            raise ValueError(f"핵심 사실 스키마 위반: {json.dumps(f, ensure_ascii=False)[:120]}")
        ids.add(fid)
        quote = str(f.get("quote") or "")
        at = source_text.find(quote) if quote else -1
        pos = at / max(len(source_text), 1) if at >= 0 else None
        tercile = None if pos is None else ("앞" if pos < 1 / 3 else "중" if pos < 2 / 3 else "뒤")
        out.append(KeyFact(fid, f["text"], quote, pos, tercile, cat, f["ai_related"]))
    return out


def parse_align(obj: dict, fact_ids: list[str], n_sentences: int) -> tuple[dict[str, bool], bool]:
    covered, first_new = obj.get("covered"), obj.get("first_sentence_is_new_fact")
    if not isinstance(covered, dict) or set(covered) != set(fact_ids) or not all(isinstance(v, bool) for v in covered.values()):
        raise ValueError("covered 는 모든 핵심 사실 id 를 bool 로 가져야 함")
    if not isinstance(first_new, bool) or n_sentences < 1:
        raise ValueError("first_sentence_is_new_fact(bool) 없음")
    return dict(covered), first_new


def parse_fidelity(obj: dict, n_sentences: int) -> dict[int, list[str]]:
    rows = obj.get("sentences")
    if not isinstance(rows, list):
        raise ValueError("sentences 가 목록이 아님")
    out: dict[int, list[str]] = {}
    for r in rows:
        idx, labels = r.get("idx"), r.get("labels")
        if not isinstance(idx, int) or not 0 <= idx < n_sentences:
            raise ValueError(f"문장 번호 범위 밖: {idx}")
        if not isinstance(labels, list) or any(lab not in FIDELITY_LABELS for lab in labels):
            raise ValueError(f"없는 라벨: {labels}")
        if labels:
            out[idx] = list(labels)
    return out


def parse_bypass(obj: dict) -> list[str]:
    items = obj.get("uncovered")
    if not isinstance(items, list) or not all(isinstance(x, str) for x in items):
        raise ValueError("uncovered 는 문자열 목록이어야 함")
    return items


def parse_pairwise(obj: dict) -> str:
    better = obj.get("better")
    if better not in ("first", "second", "tie"):
        raise ValueError(f"better 값 이상: {better}")
    return better


# ── 판정자 검증과 대체 규칙 ──
def score_gate(flags: dict[str, dict[int, list[str]]], uncovered: dict[str, set[str]], items: list[PlantedSummary], *,
               adjudicated_ok: set[tuple[str, int]]) -> JudgeGate:
    """검출률 = 심은 결함 하나 단위, 오탐률 = 결함 없는 문장 단위(원문 확인 결과 맞는 지적은 뺌)."""
    detected = defects = clean = false_flags = 0
    for it in items:
        item_flags = flags.get(it.item_id, {})
        n = len(split_sentences(it.summary))
        if it.defect == _OMISSION:
            defects += 1
            detected += it.removed_fact in uncovered.get(it.item_id, set())
        elif it.defect:
            defects += 1
            detected += bool(item_flags.get(it.sentence_idx))
        for idx in range(n):
            if it.defect and it.defect != _OMISSION and idx == it.sentence_idx:
                continue
            clean += 1
            false_flags += bool(item_flags.get(idx)) and (it.item_id, idx) not in adjudicated_ok
    detection = detected / defects if defects else 0.0
    false_rate = false_flags / clean if clean else 0.0
    eps = 1e-9
    return JudgeGate(detection, false_rate, detection >= DETECTION_MIN - eps and false_rate <= FALSE_FLAG_MAX + eps)


def select_judges(stage_b_winner: str, gates: dict[str, JudgeGate], third_ranking: list[str]) -> tuple[str, str, str]:
    """(주 판정, 교차 판정, 가림). Stage B 승자와 같은 모델은 판정에서 빼고(§14-3), 기준 미달은 다음 통과자로 바꾼다."""
    excluded = _WINNER_TO_JUDGE.get(stage_b_winner)
    order = [j for j in ["astra", "sol61", *third_ranking] if j != excluded]
    passing = [j for j in order if gates.get(j) and gates[j].passed]
    if not any(j in JUDGES for j in passing) or len(passing) < 3:
        raise GateStop(f"쓸 수 있는 판정자 부족: 통과 {passing}")
    return passing[0], passing[1], passing[2]
