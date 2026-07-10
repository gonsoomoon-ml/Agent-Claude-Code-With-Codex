"""relevance — 종합지(broad) 소스에서 AI 관련 기사만 통과시키는 사전 필터(주=Haiku 판정자, 폴백=키워드).

curate 단계(요약·검증 *전*)에서 적용 → 비-AI 기사를 author/certifier 전에 컷 = 비용 절감.
소스별 opt-in: Source.require_ai=True 인 소스(예 aitimes 종합지 피드)에만 적용 — 전용 소스(OpenAI 블로그 등)는 미적용.
- v2(production 주 판정자): llm_relevance = Haiku LLM-as-Judge(relevance_bedrock 이 주입) — 의미 판정.
- v1 키워드(is_ai_relevant) = 폴백 전용 + 테스트/로컬(AWS-free) 결정론 기본값. recall 우선(장애 시 AI 기사 보존).
  ★ 동결 — 정밀도 튜닝 금지. 오탐 교정은 주 판정자(Haiku)의 몫이고, 폴백에 필요한 덕목은 recall 뿐
  (실측 recall 8/8, 2026-07-10 aws-kr-tech 실피드). 키워드를 또 고치고 있다면 신호를 잘못 읽은 것.
"""
from __future__ import annotations

import re
from collections.abc import Callable

from .. import _debug

# (title, text) -> AI 관련 여부. 기본 구현 = is_ai_relevant(키워드); production = Haiku 판정자.
RelevanceFn = Callable[[str, str], bool]

# 한글 키워드 — 부분일치(한글이라 case 무관). ★ 동결(폴백 전용) — 정밀도 튜닝 금지, recall 만 중요.
_KO_KEYWORDS = (
    "인공지능", "생성형", "생성 AI", "머신러닝", "기계학습", "딥러닝", "신경망",
    "거대언어", "초거대", "언어모델", "파운데이션 모델", "에이전트", "챗봇",
    "자율주행", "로봇", "로보틱스", "휴머노이드", "반도체", "온디바이스",  # '데이터센터' 제거: 범용 인프라 용어 오탐원
    "오픈소스 모델", "클로드", "챗지피티", "제미나이", "딥시크", "엔비디아", "앤트로픽", "오픈에이아이",
)
# 영문/약어 — 단어 경계로만(‘Shanghai’·‘email’ 부분일치 오탐 방지), 대소문자 무시.
_EN_KEYWORDS = (
    "AI", "AGI", "LLM", "LLMs", "GPT", "ML", "NLP", "RAG", "GPU", "HBM", "NPU",
    "Claude", "ChatGPT", "Gemini", "OpenAI", "Anthropic", "NVIDIA", "DeepSeek",
    "Llama", "Grok", "Copilot", "Transformer", "Sora",
)
_EN_RE = re.compile(r"\b(" + "|".join(re.escape(w) for w in _EN_KEYWORDS) + r")\b", re.IGNORECASE)
# 매체 푸터 제거 — 예: aitimes 발췌 끝 "Powered by AItimes AI Solution" 의 'AI' 가 모든 기사를 통과시키는 오탐 방지.
_FOOTER_RE = re.compile(r"(?i)\bpowered by\b.*", re.S)


def is_ai_relevant(title: str, text: str = "") -> bool:
    """제목+발췌에 AI 신호가 하나라도 있으면 True(recall 우선). require_ai 소스 필터용.

    발췌의 매체 푸터(Powered by …)는 제거 후 검사 — 매체명/푸터의 'AI' 가 필터를 무력화하는 것 방지.
    """
    body = _FOOTER_RE.sub("", text or "")
    blob = f"{title or ''}\n{body}"
    if any(k in blob for k in _KO_KEYWORDS):
        return True
    return bool(_EN_RE.search(blob))


# ── Haiku LLM-as-Judge (v2) ────────────────────────────────────────────────
# 키워드 부분일치는 8000자 본문에 광의 키워드 하나만 스쳐도 통과(오탐)하고, 'AI가'·무키워드
# 기사를 떨군다(누락). 의미 판정으로 정밀도·recall 을 동시에 올린다. **사전 필터**라
# decorrelation 무관 — certify 증거에 흘러들지 않음(설계 = card-layering-analysis 상류 컷).
_JUDGE_SYSTEM = (
    "You are a strict news classifier. Decide whether the article is about "
    "artificial intelligence — AI, machine learning, LLMs, AI hardware "
    "(GPUs, NPUs, AI semiconductors, AI datacenters), or the AI industry and its "
    "companies. A general IT/cloud/database/networking article that is not about AI "
    "is NOT relevant. Answer with exactly one word: YES or NO."
)
_LEAD_CHARS = 1500  # 제목+리드로 주제 판별 충분 → 전문 대비 저비용


def llm_relevance(title: str, text: str, *, invoke: Callable[[str, str], str]) -> bool:
    """LLM 판정자. invoke=(system,user)->str. 예외/모호 응답 시 키워드 폴백(non-silent warn).

    한 기사 판정 실패가 브리핑 전체를 죽이면 안 됨(card-isolation 인시던트 교훈) → 항상 키워드로 degrade.
    """
    user = f"Title: {title or ''}\n\n{(text or '')[:_LEAD_CHARS]}"
    try:
        ans = (invoke(_JUDGE_SYSTEM, user) or "").upper()
    except Exception as err:  # throttle/timeout/기타 장애 → 키워드 폴백
        _debug.warn("relevance llm", f"{type(err).__name__}: {err} → 키워드 폴백")
        return is_ai_relevant(title, text)
    if "YES" in ans:
        return True
    if "NO" in ans:
        return False
    _debug.warn("relevance llm", f"모호한 응답 {ans!r} → 키워드 폴백")
    return is_ai_relevant(title, text)
