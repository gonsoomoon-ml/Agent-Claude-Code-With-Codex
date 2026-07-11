"""relevance_bedrock — Haiku LLM-as-Judge 를 boto3 `bedrock-runtime` **Converse**(모델 중립 API)로 호출.

relevance judge 는 사전 필터(decorrelation 무관)라 모델 계약이 "YES/NO 분류"뿐 → 네이티브 포맷
(invoke_model + anthropic_version JSON)이 아니라 중립 API 가 설계 의도와 일치. 모델 교체(예: 더 싼
judge 실험) = `RELEVANCE_MODEL_ID` env 변경만, 코드 무변경. ↔ author/certifier 는 모델 행동 특성이
계약의 일부라 네이티브 하니스(`claude -p`·`codex exec`) 유지 — 계약 강도에 맞춘 추상화 선택.

IAM 은 기존 `bedrock:InvokeModel` 이 Converse 도 커버(같은 액션) → 새 권한·새 의존성 0.
`_client` 는 테스트가 monkeypatch 로 갈아끼우는 시임(네트워크 격리).
"""
from __future__ import annotations

from ..config import Settings
from .relevance import RelevanceFn, llm_relevance
from .selection import SelectFn, llm_select


def _client(region: str):
    """boto3 bedrock-runtime 클라이언트. lazy import(로컬/테스트에서 boto3 없이 sources 모듈 import 가능)."""
    import boto3
    return boto3.client("bedrock-runtime", region_name=region)


def make_bedrock_relevance(settings: Settings) -> RelevanceFn:
    """settings → (title, text)->bool 판정자. Haiku Converse 호출을 llm_relevance 에 주입.

    converse/파싱 실패는 llm_relevance 안에서 키워드로 폴백(non-silent) — 여기선 조립만.
    """
    client = _client(settings.region)
    model_id = settings.relevance_model_id

    def _invoke(system: str, user: str) -> str:
        resp = client.converse(
            modelId=model_id,
            system=[{"text": system}],
            messages=[{"role": "user", "content": [{"text": user}]}],
            inferenceConfig={"maxTokens": 8, "temperature": 0},
        )
        return resp["output"]["message"]["content"][0]["text"]

    return lambda title, text: llm_relevance(title, text, invoke=_invoke)


def make_bedrock_select(settings: Settings) -> SelectFn:
    """settings → (candidates,k)->선택 판정자. 같은 Haiku·Converse 배관 — maxTokens 만 인덱스 JSON 용으로 여유.

    converse/파싱 실패는 llm_select 안에서 최신순(latest_k)으로 폴백(non-silent) — 여기선 조립만.
    """
    client = _client(settings.region)
    model_id = settings.relevance_model_id

    def _invoke(system: str, user: str) -> str:
        resp = client.converse(
            modelId=model_id,
            system=[{"text": system}],
            messages=[{"role": "user", "content": [{"text": user}]}],
            inferenceConfig={"maxTokens": 64, "temperature": 0},
        )
        return resp["output"]["message"]["content"][0]["text"]

    return lambda articles, k: llm_select(articles, k, invoke=_invoke)
