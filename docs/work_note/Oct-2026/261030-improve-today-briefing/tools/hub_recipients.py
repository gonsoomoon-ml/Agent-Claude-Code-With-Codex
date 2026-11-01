"""Partnerships 허브 카드(10-28 run)가 7명 ledger 에 모두 있는지(읽기 전용: briefing-users scan + ledger query)."""
import boto3
from briefing.core.config import load_settings
from briefing.core.stores.backends import make_stores

SID = "ee87ab4339761c914fe56ffe2490c8422562c29e85540a50d8a3191fbc04f191"  # /news/partnerships 동결본
RD = "2026-10-28"
ddb = boto3.resource("dynamodb", region_name="us-east-1")
users = [i["user_id"] for i in ddb.Table("briefing-users").scan(ProjectionExpression="user_id")["Items"]]
store, cache, ledger = make_stores(load_settings())
hit = 0
for uid in users:
    rows = [r for r in ledger.query(uid, RD) if r.get("run_date") == RD and r.get("source_id") == SID]
    hit += bool(rows)
    print(f"{uid[:8]}… {'있음 ' + rows[0].get('decision', '') if rows else '없음'}")
print(f"\n사용자 {len(users)}명 중 {hit}명의 {RD} ledger 에 Partnerships 카드")
