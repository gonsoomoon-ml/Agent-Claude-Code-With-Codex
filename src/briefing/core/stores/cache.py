"""cache — 파이프라인 결과(카드) 캐시 (③ DB v1: 로컬 파일 / v1.5: DynamoDB 가 같은 `CardCache` Protocol).

★ 목적: 비싼 파이프라인(author+certifier)을 재실행하지 않는다 — 2층 키(card-layering §5):
- **사실층** `fact_card_key(source_id|model|prompt_version)` — lens·skill 없음 → **전 사용자 공유**.
- **해석층** `interp_card_key(source_id|lens|fact_key)` — (출처, lens) 코호트 공유; fact_key 연쇄로 자동 무효화.
- source_id 가 content-addressed 라 기사가 바뀌면 두 키 다 바뀐다(자동 무효화). 구 단층 `card_key` 는 호환용.
- **gate(SOP)는 캐시를 모른다(순수하게 유지).** 캐시 조회는 *드라이버(run_briefing) 레벨의 메모이제이션* — trust 경계·decorrelation 과 무관.
- v1.5: `DynamoCardCache`(같은 Protocol) — boto3 로 테이블 생성(PAY_PER_REQUEST) + get/put_item + DDB 기본 TTL.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Protocol

from ..authoring.author import Claim, DraftCard
from ..verification.certifier import CertVerdict
from ..gate import GatedCard


def card_key(source_id: str, lens: str, skill_md: str, author_model_id: str) -> str:
    """(구) 단층 카드 키 = sha256(source_id | lens | skill_md | author_model_id).

    skill_md 가 per-user 라 사용자 간 공유가 사실상 0 이던 키 — 2층화(fact/interp)로 대체됨.
    구 캐시 항목 호환·감사용으로 유지(신규 기록은 fact_card_key/interp_card_key).
    """
    raw = f"{source_id}|{lens}|{skill_md}|{author_model_id}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def fact_card_key(source_id: str, author_model_id: str, prompt_version: str) -> str:
    """사실층 키 = sha256(source_id | author_model_id | prompt_version) — **lens·skill 없음 = 전 사용자 공유**.

    card-layering §5: 검증이 (기사, claims)의 canonical 속성이 되는 지점. prompt_version(작성 계약 개정)이
    바뀌면 자동 무효화 — 구 계약으로 만든 카드가 새 계약인 척 재사용되는 것을 차단.
    """
    raw = f"fact|{source_id}|{author_model_id}|{prompt_version}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def interp_card_key(source_id: str, lens: str, fact_key: str) -> str:
    """해석층 키 = sha256(source_id | lens | fact_key) — (출처, lens) 코호트 공유, skill 미포함(v1).

    fact_key 를 성분으로 포함 → 사실층이 재생성되면 해석층도 자동 무효화(층 간 정합성).
    저장물은 '조립 완료' GatedCard(사실층 + lens why) — 기존 직렬화 그대로 재사용.
    """
    raw = f"interp|{source_id}|{lens}|{fact_key}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class CardCache(Protocol):
    """카드 캐시 인터페이스 — 로컬 파일(v1)과 DynamoDB(v1.5)가 둘 다 만족한다."""

    def get(self, key: str) -> GatedCard | None: ...
    def put(self, key: str, card: GatedCard) -> None: ...


class NullCardCache:
    """캐시를 끈 버전 — 항상 miss(명시적으로 off 할 때). 동작에 영향 0."""

    def get(self, key: str) -> GatedCard | None:
        return None

    def put(self, key: str, card: GatedCard) -> None:
        return None


def _serialize(card: GatedCard) -> dict:
    """GatedCard(전부 frozen dataclass)를 JSON-안전 dict 로 바꾼다(asdict 재귀라 Claim·CertVerdict 도 dict)."""
    return {
        "card": asdict(card.card),
        "verdicts": [asdict(v) for v in card.verdicts],
        "decision": card.decision,
        "attempts": card.attempts,
    }


def _deserialize(d: dict) -> GatedCard:
    """dict 를 GatedCard 로 되살린다(Claim·CertVerdict 재구성).

    ※ 카드 스키마가 바뀌면 옛 캐시 항목에서 KeyError 가 날 수 있다 — 캐시는 disposable(재생성 가능)이라,
      호출하는 get() 이 실패를 miss(None)로 다루는 게 안전하다(리뷰 메모 — 현재는 그대로 raise).
    """
    cd = d["card"]
    draft = DraftCard(
        source_id=cd["source_id"],
        headline=cd["headline"],
        summary=cd["summary"],
        why_it_matters=cd["why_it_matters"],
        claims=tuple(Claim(**c) for c in cd["claims"]),
    )
    verdicts = tuple(CertVerdict(**v) for v in d["verdicts"])
    return GatedCard(draft, verdicts, d["decision"], d["attempts"])


class LocalCardCache:
    """로컬 파일 카드 캐시 (key→json). SourceStore 패턴을 미러; DDB 는 같은 Protocol 로 교체(v1.5)."""

    def __init__(self, root: str) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        return self.root / f"{key}.json"

    def get(self, key: str) -> GatedCard | None:
        p = self._path(key)
        if not p.exists():
            return None
        try:
            return _deserialize(json.loads(p.read_text(encoding="utf-8")))
        except Exception:  # noqa: BLE001 — 손상/구스키마 캐시는 miss 로(캐시는 disposable → fail-open)
            return None

    def put(self, key: str, card: GatedCard) -> None:
        self._path(key).write_text(
            json.dumps(_serialize(card), ensure_ascii=False, indent=2), encoding="utf-8"
        )
