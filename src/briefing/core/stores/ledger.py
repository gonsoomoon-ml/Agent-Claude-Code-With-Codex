"""ledger — run 기록(시간·사용자 인덱스). Diff-Since-Last·감사 등 durable history 의 토대.

★ card cache 가 "재계산 방지"라면, ledger 는 "history 조회"다. (user_id, run_date)로 인덱스해서
  '최근 N일 동안 user X 가 검증한 항목 전부'를 뽑을 수 있게 한다. **드라이버 레벨 — gate·trust 와 무관.**
- 각 엔트리 = {run_date, user_id, source_id, card_key, decision, headline}.
  원문·URL·날짜는 source_store(source_id 로 join), 검증 카드는 card cache(card_key 로 join) — *중복 저장하지 않는다*.
- run_date 는 **호출자가 주입**한다(결정론 — source_store.fetched_at 과 같은 철학). v1 = 로컬 JSONL, v1.5 = DDB(PK=user, SK=run_date#source_id).
- ★ 멱등 파리티: 같은 (user, run_date, source_id)를 다시 기록해도 *한 건*으로 본다 — DynamoLedger 는 put 으로 덮어쓰고,
  LocalLedger 는 append-only 로 쌓되 query 에서 (run_date, source_id) 마지막 줄만 남겨 두 backend 의 결과를 맞춘다.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol


class Ledger(Protocol):
    """run history 인터페이스 — 로컬 JSONL(v1)과 DynamoDB(v1.5)가 둘 다 만족한다."""

    def append(self, run_date: str, user_id: str, source_id: str, card_key: str,
               decision: str, headline: str) -> None: ...
    def query(self, user_id: str, since_date: str = "") -> list[dict]: ...


class NullLedger:
    """ledger 를 끈 버전 — 기록·조회 모두 no-op(명시적으로 off 할 때)."""

    def append(self, run_date: str, user_id: str, source_id: str, card_key: str,
               decision: str, headline: str) -> None:
        return None

    def query(self, user_id: str, since_date: str = "") -> list[dict]:
        return []


class LocalLedger:
    """로컬 JSONL ledger — user 당 파일 하나(`{user_id}.jsonl`), 한 줄 = 한 (user, source) 처리 기록(append-only)."""

    def __init__(self, root: str) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, user_id: str) -> Path:
        return self.root / f"{user_id}.jsonl"

    def append(self, run_date: str, user_id: str, source_id: str, card_key: str,
               decision: str, headline: str) -> None:
        """한 기록을 JSONL 끝에 한 줄 추가한다(append-only — 빠르고 크래시에 안전). 중복 정리는 query 가 읽을 때 한다."""
        rec = {
            "run_date": run_date, "user_id": user_id, "source_id": source_id,
            "card_key": card_key, "decision": decision, "headline": headline,
        }
        with self._path(user_id).open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def query(self, user_id: str, since_date: str = "") -> list[dict]:
        """user 의 run 기록을 돌려준다(since_date 이상만; ISO 날짜는 사전식=시간순). Diff-Since-Last·감사가 호출한다.

        ★ 멱등 파리티: 같은 (run_date, source_id)가 재실행으로 여러 줄 쌓여도 *마지막 줄만* 남긴다 —
          DynamoLedger 의 put 덮어쓰기와 같은 의미. 결과는 (run_date, source_id) 정렬 = DDB SK 오름차순과 일치.
        """
        p = self._path(user_id)
        if not p.exists():
            return []
        by_key: dict[tuple[str, str], dict] = {}
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            rec = json.loads(line)
            if since_date and rec.get("run_date", "") < since_date:
                continue
            by_key[(rec.get("run_date", ""), rec.get("source_id", ""))] = rec  # 마지막 줄이 이긴다 = dynamo put 덮어쓰기
        return [by_key[k] for k in sorted(by_key)]  # (run_date, source_id) 정렬 — DDB SK 오름차순과 일치
