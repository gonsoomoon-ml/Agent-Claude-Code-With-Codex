"""relevance_bedrock — Haiku LLM-as-Judge 를 boto3 `bedrock-runtime` **Converse**(모델 중립 API)로 호출.

라벨 호출(핵심 3·분야, 2026-10-24)은 LABEL_MODEL_ID(Sonnet 5.5) 로 분리 — 관련성 판정(기사마다 호출)은 Haiku 유지.
relevance judge 는 사전 필터(decorrelation 무관)라 모델 계약이 "YES/NO 분류"뿐 → 네이티브 포맷
(invoke_model + anthropic_version JSON)이 아니라 중립 API 가 설계 의도와 일치. 모델 교체(예: 더 싼
judge 실험) = `RELEVANCE_MODEL_ID` env 변경만, 코드 무변경. ↔ author/certifier 는 모델 행동 특성이
계약의 일부라 네이티브 하니스(`claude -p`·`codex exec`) 유지 — 계약 강도에 맞춘 추상화 선택.

IAM 은 기존 `bedrock:InvokeModel` 이 Converse 도 커버(같은 액션) → 새 권한·새 의존성 0.
`_client` 는 테스트가 monkeypatch 로 갈아끼우는 시임(네트워크 격리).
"""
from __future__ import annotations

from ..config import Settings
from .. import _debug
from ..top_picks import LabelFn, llm_labels
from .headlines import HeadlineAreaFn, llm_headline_areas, llm_headline_select
from .relevance import RelevanceFn, llm_relevance
from .selection import SelectFn, llm_select


def _client(region: str):
    """boto3 bedrock-runtime 클라이언트. lazy import(로컬/테스트에서 boto3 없이 sources 모듈 import 가능)."""
    import boto3
    return boto3.client("bedrock-runtime", region_name=region)


def _converse_text(client, model_id: str, system: str, user: str, max_tokens: int) -> str:
    """Converse 1콜 → 첫 텍스트 블록. 판정은 짧은 답(YES/NO·인덱스 JSON)이라 thinking 을 끈다.

    ★ Haiku 5.5(2026-10-17 실측): `temperature` 를 보내면 ValidationException("deprecated"), thinking 이
      기본 on 이라 maxTokens 를 추론(reasoningContent)에 다 써 텍스트가 없다 — 둘 다 예외 → 키워드/최신순
      폴백이라 **판정자가 조용히 꺼진다**. temperature 미지정 + thinking disabled(Haiku 4.5 도 수용) +
      content[0] 고정 대신 텍스트 블록 탐색.
    """
    resp = client.converse(
        modelId=model_id,
        system=[{"text": system}],
        messages=[{"role": "user", "content": [{"text": user}]}],
        inferenceConfig={"maxTokens": max_tokens},
        additionalModelRequestFields={"thinking": {"type": "disabled"}},
    )
    return next(b["text"] for b in resp["output"]["message"]["content"] if "text" in b)


LABEL_MAX_TOKENS = 6000   # 라벨 호출 상한 — 카드마다 객체 1개(26장 ≈ 1,500 토큰) + thinking 이 켜진 모델의 사고분 여유


def label_request_fields(model_id: str) -> dict:
    """라벨 호출의 `additionalModelRequestFields` — 모델별(2026-10-24 스모크로 확정, 스펙 §6.1).

    - Haiku(4.5/5.5): `thinking: disabled` — 켜 두면 maxTokens 를 사고에 다 써 텍스트가 없다(2026-10-17 실측).
    - Sonnet 5.5 / Opus 5.5: `thinking: disabled` 는 **400**(ValidationException). 사고를 끄려면 `between_tools`,
      아니면 adaptive 기본 + 낮은 effort. 어느 쪽이 Bedrock Converse 에서 통하는지는 Task 6 스모크가 정한다 —
      통한 값과 날짜를 아래 주석에 남긴다.
    """
    m = (model_id or "").lower()
    if "sonnet-5-5" in m or "opus-5-5" in m:
        return {"thinking": {"type": "between_tools"}}   # ✓ 2026-10-24 스모크: global.anthropic.claude-sonnet-5-5 Converse 에서 텍스트 "OK" 수신(400 없음)
    return {"thinking": {"type": "disabled"}}


def _converse_label_text(client, model_id: str, system: str, user: str) -> str:
    """라벨 호출 전용 Converse 1콜 → 텍스트 블록(reasoningContent 가 앞에 와도 텍스트를 찾는다). 관련성 헬퍼와 분리."""
    resp = client.converse(
        modelId=model_id,
        system=[{"text": system}],
        messages=[{"role": "user", "content": [{"text": user}]}],
        inferenceConfig={"maxTokens": LABEL_MAX_TOKENS},
        additionalModelRequestFields=label_request_fields(model_id),
    )
    return next(b["text"] for b in resp["output"]["message"]["content"] if "text" in b)


def _label_model(settings: Settings) -> str:
    """라벨 모델 = LABEL_MODEL_ID, 빈 값이면 RELEVANCE_MODEL_ID 상속(config 의 해석 시점 규칙)."""
    return getattr(settings, "label_model_id", "") or settings.relevance_model_id


def make_bedrock_relevance(settings: Settings) -> RelevanceFn:
    """settings → (title, text)->bool 판정자. Haiku Converse 호출을 llm_relevance 에 주입.

    converse/파싱 실패는 llm_relevance 안에서 키워드로 폴백(non-silent) — 여기선 조립만.
    """
    client = _client(settings.region)
    model_id = settings.relevance_model_id

    def _invoke(system: str, user: str) -> str:
        return _converse_text(client, model_id, system, user, 8)

    return lambda title, text: llm_relevance(title, text, invoke=_invoke)


def make_bedrock_select(settings: Settings) -> SelectFn:
    """settings → (candidates,k)->선택 판정자. 같은 Haiku·Converse 배관 — maxTokens 만 인덱스 JSON 용으로 여유.

    converse/파싱 실패는 llm_select 안에서 최신순(latest_k)으로 폴백(non-silent) — 여기선 조립만.
    """
    client = _client(settings.region)
    model_id = settings.relevance_model_id

    def _invoke(system: str, user: str) -> str:
        return _converse_text(client, model_id, system, user, 64)

    return lambda articles, k: llm_select(articles, k, invoke=_invoke)


def make_bedrock_headline_select(settings: Settings):
    """settings → (candidates,k,covered)->선택. 헤드라인 칸 전용 2콜(카드와 같은 사건 제거 → 상한 이하 선별, 제목만).

    실패는 llm_headline_select 안에서 keyword_latest 로 폴백(non-silent) — 여기선 조립만.
    """
    client = _client(settings.region)
    model_id = settings.relevance_model_id

    def _invoke(system: str, user: str) -> str:
        # 두 콜 모두 "짧게 추론 → 마지막 줄 배열"(실측 출력 380~730 토큰) — 상한에 잘리면 폴백이라 넉넉히
        return _converse_text(client, model_id, system, user, 2000)

    return lambda cands, k, covered: llm_headline_select(cands, k, covered, invoke=_invoke)


def make_bedrock_headline_areas(settings: Settings) -> HeadlineAreaFn:
    """settings → titles->분야 목록. 헤드라인 칸 분야 묶음 1콜(선별된 제목만, "짧게 추론 → 마지막 줄 객체").

    모델 = 라벨 모델(LABEL_MODEL_ID; 같은 분야 체계는 같은 판정자 — 2026-10-24 빌더 기본안). 라벨 헬퍼의 모델별
    파라미터를 쓴다. 실패는 llm_headline_areas 안에서 [](소제목 없는 한 목록, non-silent) — 여기선 조립만.
    """
    client = _client(settings.region)
    model_id = _label_model(settings)

    def _invoke(system: str, user: str) -> str:
        return _converse_label_text(client, model_id, system, user)

    return lambda titles: llm_headline_areas(titles, invoke=_invoke)



def make_bedrock_labels(settings: Settings) -> LabelFn:
    """settings → (보이는 카드, 섹션)->완전한 라벨 목록(핵심 3 + 분야, 2026-10-24). 모델 = LABEL_MODEL_ID(Sonnet 5.5).

    불완전·예외는 llm_labels 가 1회 재시도 뒤 LabelIncomplete 로 올린다(호출자 = pipeline.label_cards 가 평평 폴백).
    호출마다 warn 한 줄에 model= 을 남긴다 — 첫 프로덕션 run 에서 LABEL_MODEL_ID 가 컨테이너까지 갔는지 증명(스펙 §6.1).
    """
    client = _client(settings.region)
    model_id = _label_model(settings)

    def _invoke(system: str, user: str) -> str:
        _debug.warn("areas 호출", f"model={model_id} maxTokens={LABEL_MAX_TOKENS}")
        return _converse_label_text(client, model_id, system, user)

    return lambda cards, sections=(): llm_labels(cards, sections, invoke=_invoke)
