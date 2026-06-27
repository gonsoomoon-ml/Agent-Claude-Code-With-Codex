"""DDB 스모크 — 로컬 머신에서 *실제* DynamoDB(또는 무료 DynamoDB Local)에 cache·ledger 왕복 검증.

선행(실 AWS, 과금): 테이블을 CloudFormation 으로 생성 — ★ region 명시(us-east-1; CLI 기본값에 끌려가지 말 것):
  aws cloudformation deploy --template-file infra/ddb.yaml --stack-name briefing-ddb --region us-east-1
실행:
  AWS_REGION=us-east-1 uv run python scripts/ddb_smoke.py             # 실 AWS (env: AWS creds; region=us-east-1)
  DDB_ENDPOINT_URL=http://localhost:8000 uv run python scripts/ddb_smoke.py   # 무료 에뮬레이터

PAY_PER_REQUEST 라 idle ≈ $0, 이 스모크 몇 건은 수십원 미만.
"""
import json
import os

from briefing.shared.harness.author import Claim, DraftCard
from briefing.shared.stores.cache import card_key
from briefing.shared.harness.certifier import CertVerdict
from briefing.shared.stores.dynamo import DynamoCardCache, DynamoLedger, DynamoSourceStore
from briefing.shared.gate import GatedCard

region = os.getenv("AWS_REGION", "us-east-1")
endpoint = os.getenv("DDB_ENDPOINT_URL", "")
where = endpoint or f"실 AWS ({region})"
cache = DynamoCardCache(os.getenv("CACHE_TABLE", "briefing-card-cache"), region, endpoint)
ledger = DynamoLedger(os.getenv("LEDGER_TABLE", "briefing-ledger"), region, endpoint)
store = DynamoSourceStore(os.getenv("SOURCE_TABLE", "briefing-source-store"), region, endpoint)
print(f"대상: {where}")

# ── ⓪ source-store 왕복 (freeze → get; media 캡처) ──
fs = store.freeze(url="https://www.aitimes.com/news/articleView.html?idxno=1",
                  title="예시 기사", raw_text="에이전트가 검증을 통과했다.",
                  fetched_at="2026-06-27T00:00:00Z", media="AI Times")
got_src = store.get_source(fs.source_id)
print(f"source.freeze → media={fs.media!r} · source_id={fs.source_id[:12]}…")
print("source.get(왕복):", "OK 무손실" if got_src == fs else f"MISMATCH {got_src}")

# ── ① card cache 왕복 (put → get == 원본?) ──
g = GatedCard(
    DraftCard("S1", "헤드라인", "요약", "왜 중요", (Claim("C1", "직원이 100명이다.", "arithmetic", "core"),)),
    (CertVerdict("C1", "VERIFIED", "ev", "deterministic"),), "PUBLISH", 1)
k = card_key("S1", "engineer", "", "model-x")
print("cache.get(미스 예상):", cache.get(k))
cache.put(k, g)
got = cache.get(k)
print("cache.get(히트):", "OK 무손실" if got == g else f"MISMATCH {got}")

# ── ② ledger append/query (시간 필터) ──
ledger.append("2026-06-20", "smoke-user", "S1", k, "PUBLISH", "월요일 기사")
ledger.append("2026-06-27", "smoke-user", "S2", "k2", "QUARANTINE", "금요일 기사")
rows = ledger.query("smoke-user")
recent = ledger.query("smoke-user", since_date="2026-06-25")
print("ledger.query(전체):", json.dumps(rows, ensure_ascii=False))
print("ledger.query(06-25 이후):", json.dumps(recent, ensure_ascii=False))

ok = got_src == fs and got == g and len(rows) == 2 and len(recent) == 1
print("✓ DDB 스모크 통과" if ok else "✗ 실패")
