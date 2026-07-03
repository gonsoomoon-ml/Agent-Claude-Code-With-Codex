"""relevance — 종합지(broad) 소스에서 AI 관련 기사만 통과시키는 결정론 키워드 필터(v1).

curate 단계(요약·검증 *전*)에서 적용 → 비-AI 기사를 author/certifier 전에 컷 = 비용 절감.
recall 우선: 제목+발췌에 AI 신호가 하나라도 있으면 keep(진짜 AI 기사를 떨구는 쪽이 더 나쁨).
소스별 opt-in: Source.require_ai=True 인 소스(예 aitimes 종합지 피드)에만 적용 — 전용 소스(OpenAI 블로그 등)는 미적용.
키워드는 tunable(여기 상수). 부족하면 v2 에서 LLM 분류기로 승급(설계 토론 기록).
"""
from __future__ import annotations

import re

# 한글 키워드 — 부분일치(case 무관 의미 없음, 한글). recall 우선이라 넉넉히.
_KO_KEYWORDS = (
    "인공지능", "생성형", "생성 AI", "머신러닝", "기계학습", "딥러닝", "신경망",
    "거대언어", "초거대", "언어모델", "파운데이션 모델", "에이전트", "챗봇",
    "자율주행", "로봇", "로보틱스", "휴머노이드", "반도체", "데이터센터", "온디바이스",
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
