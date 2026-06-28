"""cache — 파이프라인 결과(카드) 캐시 (③ DB v1: 로컬 파일 / v1.5: DynamoDB 가 같은 `CardCache` Protocol).

★ 목적: 다른 사용자가 *같은 (출처, lens, skill, author 모델)* 에 대해 비싼 파이프라인을 다시 돌리지 않게 한다 —
  cache hit 면 `claude -p`(author) + `codex`(certifier) 를 둘 다 건너뛴다.
- 키 = sha256(source_id | lens | skill_md | author_model_id). source_id 가 content-addressed 라 기사가 바뀌면 키도 바뀐다(자동 무효화).
- **gate(SOP)는 캐시를 모른다(순수하게 유지).** 캐시 조회는 *드라이버(run_briefing) 레벨의 메모이제이션* — trust 경계·decorrelation 과 무관.
- v1.5: `DynamoCardCache`(같은 Protocol) — boto3 로 테이블 생성(PAY_PER_REQUEST) + get/put_item + DDB 기본 TTL.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Protocol

from ..harness.author import Claim, DraftCard
from ..harness.certifier import CertVerdict
from ..gate import GatedCard


def card_key(source_id: str, lens: str, skill_md: str, author_model_id: str) -> str:
    """카드 캐시 키 = sha256(source_id | lens | skill_md | author_model_id).

    같은 (동결 출처, 렌즈, skill, 작성 모델)이면 같은 카드(결정론)라 재사용해도 안전하다. 넷 중 하나라도 다르면 키가 달라져 miss.
    """
    raw = f"{source_id}|{lens}|{skill_md}|{author_model_id}"
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
