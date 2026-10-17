"""가격과 비용 계산 — 단위는 $/1M 토큰. 확인하지 않은 가격은 verified=False 로 끝까지 따라다닌다('미확인' 표기).

Task 7 은 자료형·2차 출처 가격·codex 비용만 두고, Task 11 이 공식 가격 조회·Cost Explorer·카드당 비용을 더한다.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from .common import EXP_ROOT

PRICES_PATH = EXP_ROOT / "results" / "prices.json"   # Task 11 이 공식 가격으로 쓴다


@dataclass(frozen=True)
class Price:
    input: float
    output: float
    cache_read: float | None
    verified: bool
    source: str
    cache_write: float | None = None   # codex 0.163.0 이 cache_write_input_tokens 를 보고한다(Task 1). 모르면 입력 단가.


_SECONDARY = "2차 출처(2026-10, Bedrock 미확인)"
FALLBACK_PRICES: dict[str, Price] = {
    "gpt-6-astra": Price(10.0, 50.0, None, False, _SECONDARY),
    "gpt-6-sol": Price(2.0, 10.0, None, False, _SECONDARY),
    "gpt-6.1-sol": Price(2.0, 10.0, None, False, _SECONDARY),
    "gpt-6-luna": Price(0.10, 0.50, None, False, _SECONDARY),
    "gpt-5.5": Price(5.0, 30.0, None, False, _SECONDARY),
}


def load_prices(path: Path | None = None) -> dict[str, Price]:
    """확인된 가격 파일(Task 11)이 있으면 그 값으로 덮고, 없는 모델은 2차 출처(verified=False)를 유지한다."""
    path = path or PRICES_PATH
    prices = dict(FALLBACK_PRICES)
    if path.exists():
        for key, fields in json.loads(path.read_text(encoding="utf-8")).items():
            prices[key] = Price(**fields)
    return prices


def card_cost(record: dict, prices: dict[str, Price], verifier: str) -> tuple[float, bool]:
    """카드 1장 비용 = 요약 AI envelope 실비용 합 + 검증 AI 토큰 비용. bool = 검증 가격이 확인된 값인가."""
    author = sum(r.get("cost_usd") or 0.0 for r in record.get("author_runs", []))
    calls = record.get("codex_calls", [])
    if not calls:
        return author, True
    price = prices.get(verifier) or FALLBACK_PRICES[verifier]
    return author + sum(codex_cost(c.get("usage") or {}, price) for c in calls), price.verified


def project(cost_per_card: float, cards_per_day: float = 19.0) -> dict[str, float]:
    """하루·월(30일) 환산 — 사실층은 사용자끼리 공유하므로 수신자 수와 무관(최근 30일 고유 기사 약 19건/일)."""
    day = cost_per_card * cards_per_day
    return {"day": day, "month": day * 30}


_USAGE_MODEL = re.compile(r"^([A-Z0-9]+)-([a-z]+\.[a-z0-9.\-]+?)-mantle-")


def split_by_model(rows: list[dict], *, region: str | None = None) -> dict[str, float]:
    """Cost Explorer USAGE_TYPE 행 → {provider.model: 금액}. 예: 'USE1-anthropic.claude-sonnet-5-mantle-…'.
    모델을 읽을 수 없는 옛 형식('USE1-Claude4.6Sonnet-…')은 '기타'. region 을 주면 그 지역 접두어만."""
    out: dict[str, float] = {}
    for r in rows:
        ut = r["usage_type"]
        if region and not ut.startswith(f"{region}-"):
            continue
        m = _USAGE_MODEL.match(ut)
        key = m.group(2) if m else "기타"
        out[key] = out.get(key, 0.0) + float(r["amount"])
    return out


_PRICE_KIND = re.compile(r"_(input|output|cache_read|cache_write)_tokens_(global_standard|standard)-Units$")


def parse_price_items(items: list[str], *, scope: str, source: str) -> Price | None:
    """AmazonBedrockFoundationModels 가격 항목(JSON 문자열) → Price($/1M). long_ctx·1h·batch 는 무시. 입·출력이 없으면 None."""
    found: dict[str, float] = {}
    for raw in items:
        item = json.loads(raw)
        m = _PRICE_KIND.search(item["product"]["attributes"].get("usagetype", ""))
        if not m or m.group(2) != scope:
            continue
        for term in item["terms"].get("OnDemand", {}).values():
            for dim in term["priceDimensions"].values():
                per = float(dim["pricePerUnit"]["USD"]) * (1000.0 if dim.get("unit", "").lower().startswith("1k") else 1.0)
                found[m.group(1)] = per
    if "input" not in found or "output" not in found:
        return None
    return Price(found["input"], found["output"], found.get("cache_read"), True, source, found.get("cache_write"))


# 가격 목록의 모델 이름 — 검증 AI 는 codex(mantle) 지역 호출이라 'standard', 요약 AI 는 global 프로필이라 'global_standard'.
PRICE_LIST_NAMES: dict[str, tuple[str, str]] = {
    "gpt-6-astra": ("OpenAI GPT-6 Astra", "standard"), "gpt-6-sol": ("OpenAI GPT-6 Sol", "standard"),
    "gpt-6.1-sol": ("OpenAI GPT-6.1 Sol", "standard"), "gpt-6-luna": ("OpenAI GPT-6 Luna", "standard"),
    "gpt-5.5": ("OpenAI GPT-5.5", "standard"),
    "global.anthropic.claude-sonnet-5": ("Claude Sonnet 5", "global_standard"),
    "global.anthropic.claude-sonnet-5-5": ("Claude Sonnet 5.5", "global_standard"),
    "global.anthropic.claude-opus-5-5": ("Claude Opus 5.5", "global_standard"),
    "global.anthropic.claude-haiku-5-5": ("Claude Haiku 5.5", "global_standard"),
}


def fetch_bedrock_prices(keys: list[str], *, client=None) -> dict[str, Price]:
    """가격 목록 API(us-east-1)에서 확인된 가격만 돌려준다 — 없는 모델은 빠진다(호출자가 2차 출처로 채움)."""
    import datetime

    import boto3

    client = client or boto3.client("pricing", region_name="us-east-1")
    source = f"AWS Price List API {datetime.date.today().isoformat()}"
    out = {}
    for key in keys:
        name, scope = PRICE_LIST_NAMES[key]
        items, token = [], None
        while True:
            kw = {"ServiceCode": "AmazonBedrockFoundationModels", "MaxResults": 100,
                  "Filters": [{"Type": "TERM_MATCH", "Field": "regionCode", "Value": "us-east-1"},
                              {"Type": "TERM_MATCH", "Field": "model", "Value": name}]}
            if token:
                kw["NextToken"] = token
            resp = client.get_products(**kw)
            items += resp.get("PriceList", [])
            token = resp.get("NextToken")
            if not token:
                break
        price = parse_price_items(items, scope=scope, source=source)
        if price:
            out[key] = price
    return out


def cost_explorer_bedrock(start: str, end: str, *, client=None) -> list[dict]:
    """Cost Explorer — Bedrock 서비스 청구액·사용량을 USAGE_TYPE 별로(요청당 $0.01)."""
    import boto3

    client = client or boto3.client("ce", region_name="us-east-1")
    resp = client.get_cost_and_usage(
        TimePeriod={"Start": start, "End": end}, Granularity="MONTHLY", Metrics=["UnblendedCost", "UsageQuantity"],
        Filter={"Dimensions": {"Key": "SERVICE", "Values": ["Amazon Bedrock Service", "Amazon Bedrock"]}},
        GroupBy=[{"Type": "DIMENSION", "Key": "USAGE_TYPE"}])
    rows = []
    for period in resp["ResultsByTime"]:
        for g in period["Groups"]:
            rows.append({"usage_type": g["Keys"][0], "amount": float(g["Metrics"]["UnblendedCost"]["Amount"]),
                         "quantity": float(g["Metrics"]["UsageQuantity"]["Amount"]),
                         "unit": g["Metrics"]["UsageQuantity"].get("Unit", "")})
    return rows


def codex_cost(usage: dict, price: Price, *, reasoning_in_output: bool = True) -> float:
    """codex `turn.completed.usage` → 달러. 캐시 읽기·쓰기 단가를 모르면 입력 단가로 센다(보수적)."""
    total_in = usage.get("input_tokens", 0) or 0
    cached = usage.get("cached_input_tokens", 0) or 0
    written = usage.get("cache_write_input_tokens", 0) or 0
    out = usage.get("output_tokens", 0) or 0
    if not reasoning_in_output:
        out += usage.get("reasoning_output_tokens", 0) or 0
    uncached = max(total_in - cached - written, 0)
    read_rate = price.input if price.cache_read is None else price.cache_read
    write_rate = price.input if price.cache_write is None else price.cache_write
    return (uncached * price.input + cached * read_rate + written * write_rate + out * price.output) / 1e6


def main(argv: list[str] | None = None) -> None:
    """공식 가격(results/prices.json)과 최근 기간 Bedrock 실제 청구(results/costs.json)를 기록한다."""
    import argparse

    ap = argparse.ArgumentParser(prog="costs")
    ap.add_argument("--since", required=True)
    ap.add_argument("--until", required=True)
    args = ap.parse_args(argv)
    verified = fetch_bedrock_prices(list(PRICE_LIST_NAMES))
    PRICES_PATH.parent.mkdir(parents=True, exist_ok=True)
    PRICES_PATH.write_text(json.dumps({k: p.__dict__ for k, p in verified.items()}, ensure_ascii=False, indent=2), encoding="utf-8")
    rows = cost_explorer_bedrock(args.since, args.until)
    by_model = {r: split_by_model(rows, region=r) for r in sorted({x["usage_type"].split("-")[0] for x in rows})}
    tokens: dict[str, dict[str, float]] = {}
    for x in rows:
        m = _USAGE_MODEL.match(x["usage_type"])
        if m and m.group(1) == "USE1":
            kind = "output" if "output-tokens" in x["usage_type"] else "input"
            per = 1000.0 if x["unit"].lower().startswith("1k") else 1.0
            tokens.setdefault(m.group(2), {}).setdefault(kind, 0.0)
            tokens[m.group(2)][kind] += x["quantity"] * per
    gpt55 = tokens.get("openai.gpt-5.5", {})
    p55 = load_prices().get("gpt-5.5", FALLBACK_PRICES["gpt-5.5"])
    list_equiv = (gpt55.get("input", 0) * p55.input + gpt55.get("output", 0) * p55.output) / 1e6
    out = {"period": [args.since, args.until], "verified_prices": sorted(verified), "by_region_model": by_model,
           "use1_tokens": tokens,
           "gpt55_list_price_equivalent": {"usd": list_equiv, "price_verified": p55.verified, "price_source": p55.source},
           "notes": ["공용 계정 — Bedrock 청구는 프로젝트별로 나뉘지 않는다. 브리핑 런타임은 us-east-1(USE1)만 쓴다.",
                     "OpenAI(mantle) 사용 유형은 사용량은 기록되지만 이 계정에서 청구액 $0 — 이유 미확인."]}
    (PRICES_PATH.parent / "costs.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"verified_prices": sorted(verified), "USE1": by_model.get("USE1", {}),
                      "gpt55_tokens": gpt55, "gpt55_list_equiv_usd": round(list_equiv, 2)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
