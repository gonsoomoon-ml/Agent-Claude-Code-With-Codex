"""ledger — run 기록 (시간·사용자 인덱스). weekly summary·Diff-Since-Last 의 토대.

★ card cache = "재계산 방지", ledger = "history 조회". (user_id, run_date) 로 인덱스해
  '이번 주 user X 의 검증 항목 전부'를 뽑을 수 있게 한다. **드라이버 레벨(gate·trust 무관).**
- 각 엔트리 = {run_date, user_id, source_id, card_key, decision, headline}.
  원문/URL/날짜는 source_store(source_id 로 join), 검증 카드는 card cache(card_key 로 join) — *중복 저장 안 함*.
- run_date 는 **호출자 주입**(결정론 — source_store.fetched_at 과 동일 철학). v1 로컬 JSONL; v1.5 DDB GSI(user, date).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol


class Ledger(Protocol):
    """run history 인터페이스 — 로컬 JSONL(v1) / DynamoDB GSI(v1.5) 가 둘 다 만족."""

    def append(self, run_date: str, user_id: str, source_id: str, card_key: str,
               decision: str, headline: str) -> None: ...
    def query(self, user_id: str, since_date: str = "") -> list[dict]: ...


class NullLedger:
    """ledger 비활성 — 기록·조회 0 (명시적 off)."""

    def append(self, run_date: str, user_id: str, source_id: str, card_key: str,
               decision: str, headline: str) -> None:
        return None

    def query(self, user_id: str, since_date: str = "") -> list[dict]:
        return []


class LocalLedger:
    """로컬 JSONL ledger — user 당 한 파일(`{user_id}.jsonl`), 한 줄 = 한 (user, source) 처리 기록."""

    def __init__(self, root: str) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, user_id: str) -> Path:
        return self.root / f"{user_id}.jsonl"

    def append(self, run_date: str, user_id: str, source_id: str, card_key: str,
               decision: str, headline: str) -> None:
        rec = {
            "run_date": run_date, "user_id": user_id, "source_id": source_id,
            "card_key": card_key, "decision": decision, "headline": headline,
        }
        with self._path(user_id).open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def query(self, user_id: str, since_date: str = "") -> list[dict]:
        """user 의 run 기록 (since_date 이상만; ISO 날짜는 사전식=시간순). weekly summary 가 호출."""
        p = self._path(user_id)
        if not p.exists():
            return []
        out: list[dict] = []
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            rec = json.loads(line)
            if since_date and rec.get("run_date", "") < since_date:
                continue
            out.append(rec)
        return out
