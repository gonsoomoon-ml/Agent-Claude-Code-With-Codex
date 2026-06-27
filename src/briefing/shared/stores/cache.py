"""cache — 공유 결과 캐시 (③ DB v1: 로컬 파일; v1.5: DynamoDB 가 같은 `CardCache` Protocol).

★ 목적: 다른 사용자가 *같은 (source, lens, skill, author_model)* 에 대해 비싼 파이프라인을 재실행하지 않게 —
  cache hit 면 `claude -p`(author) + `codex`(certifier) 둘 다 skip.
- 키 = sha256(source_id | lens | skill_md | author_model_id). source_id 는 content-addressed → 기사가 바뀌면 키도 바뀜(자동 무효화).
- **gate(SOP)는 캐시를 모른다(순수 유지).** 캐시 조회는 *드라이버(run_briefing) 레벨 메모이제이션* — trust 경계·decorrelation 무관.
- v1.5: `DynamoCardCache`(같은 Protocol) — boto3 `create-table`(PAY_PER_REQUEST) + `get/put_item` + native TTL.
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

    같은 (동결 출처, 렌즈, skill, 작성 모델) → 같은 카드(결정론) → 재사용 안전. 하나라도 다르면 다른 키(miss).
    """
    raw = f"{source_id}|{lens}|{skill_md}|{author_model_id}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class CardCache(Protocol):
    """카드 캐시 인터페이스 — 로컬 파일(v1) / DynamoDB(v1.5) 가 둘 다 만족."""

    def get(self, key: str) -> GatedCard | None: ...
    def put(self, key: str, card: GatedCard) -> None: ...


class NullCardCache:
    """캐시 비활성 — 항상 miss(명시적 off 용). 동작 변화 0."""

    def get(self, key: str) -> GatedCard | None:
        return None

    def put(self, key: str, card: GatedCard) -> None:
        return None


def _serialize(card: GatedCard) -> dict:
    """GatedCard(전부 frozen dataclass) → JSON-안전 dict (asdict 재귀로 Claim·CertVerdict 도 dict)."""
    return {
        "card": asdict(card.card),
        "verdicts": [asdict(v) for v in card.verdicts],
        "decision": card.decision,
        "attempts": card.attempts,
    }


def _deserialize(d: dict) -> GatedCard:
    """dict → GatedCard (Claim·CertVerdict 재구성)."""
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
    """로컬 파일 카드 캐시 (key→json). SourceStore 패턴 mirror; DDB 는 같은 Protocol 로 교체(v1.5)."""

    def __init__(self, root: str) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        return self.root / f"{key}.json"

    def get(self, key: str) -> GatedCard | None:
        p = self._path(key)
        if not p.exists():
            return None
        return _deserialize(json.loads(p.read_text(encoding="utf-8")))

    def put(self, key: str, card: GatedCard) -> None:
        self._path(key).write_text(
            json.dumps(_serialize(card), ensure_ascii=False, indent=2), encoding="utf-8"
        )
