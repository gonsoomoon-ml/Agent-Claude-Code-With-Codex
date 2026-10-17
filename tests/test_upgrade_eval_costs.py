"""업그레이드 비교 실험 — 비용 테스트: 카드당 비용·환산·Cost Explorer 사용 유형 분류·가격 목록 파싱."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from upgrade_eval import costs  # noqa: E402


def test_card_cost_and_unverified_flag():
    rec = {"author_runs": [{"cost_usd": 0.12}, {"cost_usd": 0.03}],
           "codex_calls": [{"usage": {"input_tokens": 1_000_000, "cached_input_tokens": 0, "output_tokens": 0}}]}
    cost, verified = costs.card_cost(rec, {"gpt-6-sol": costs.Price(2.0, 10.0, None, False, "2차")}, "gpt-6-sol")
    assert cost == pytest.approx(0.15 + 2.0) and verified is False


def test_card_cost_without_codex_calls_is_verified():
    rec = {"author_runs": [{"cost_usd": 0.10}], "codex_calls": []}
    assert costs.card_cost(rec, {}, "gpt-6-sol") == (pytest.approx(0.10), True)


def test_project():
    assert costs.project(0.5) == {"day": pytest.approx(9.5), "month": pytest.approx(285.0)}


def test_split_by_model_real_usage_types():
    rows = [{"usage_type": "USE1-anthropic.claude-sonnet-5-mantle-output-tokens-global-standard", "amount": 3.0},
            {"usage_type": "USE1-anthropic.claude-sonnet-5-mantle-cache-read-tokens-global-standard", "amount": 0.5},
            {"usage_type": "USE1-openai.gpt-5.5-mantle-input-tokens-standard", "amount": 0.0},
            {"usage_type": "USW2-anthropic.claude-opus-5-mantle-input-tokens-standard", "amount": 2.0},
            {"usage_type": "USE1-Claude4.6Sonnet-output-tokens", "amount": 1.0}]
    assert costs.split_by_model(rows) == {"anthropic.claude-sonnet-5": 3.5, "openai.gpt-5.5": 0.0,
                                          "anthropic.claude-opus-5": 2.0, "기타": 1.0}
    assert costs.split_by_model(rows, region="USE1") == {"anthropic.claude-sonnet-5": 3.5, "openai.gpt-5.5": 0.0, "기타": 1.0}


def _price_item(model, usagetype, usd):
    return json.dumps({"product": {"attributes": {"model": model, "usagetype": usagetype, "regionCode": "us-east-1"}},
                       "terms": {"OnDemand": {"x": {"priceDimensions": {"y": {"pricePerUnit": {"USD": usd}, "unit": "1M tokens"}}}}}})


def test_parse_price_items_picks_scope_and_ignores_long_context():
    items = [_price_item("OpenAI GPT-6 Astra", "USE1-MP:USE1_input_tokens_standard-Units", "11.0"),
             _price_item("OpenAI GPT-6 Astra", "USE1-MP:USE1_input_tokens_global_standard-Units", "10.0"),
             _price_item("OpenAI GPT-6 Astra", "USE1-MP:USE1_output_tokens_standard-Units", "55.0"),
             _price_item("OpenAI GPT-6 Astra", "USE1-MP:USE1_cache_read_tokens_standard-Units", "1.1"),
             _price_item("OpenAI GPT-6 Astra", "USE1-MP:USE1_input_tokens_long_ctx_standard-Units", "22.0")]
    p = costs.parse_price_items(items, scope="standard", source="test")
    assert (p.input, p.output, p.cache_read, p.cache_write, p.verified) == (11.0, 55.0, 1.1, None, True)
    assert costs.parse_price_items(items, scope="global_standard", source="test") is None   # 출력 단가가 없으면 불완전


def test_author_cost_uses_verified_list_price_over_cli_estimate():
    # CLI 2.1.195 는 Sonnet 5 비용을 옛 단가표로 1.57배 높게 보고했다(Stage A 실측) — 확인된 단가가 있으면 사용량으로 다시 계산
    usage = {"input_tokens": 1_000_000, "output_tokens": 100_000, "cache_read_input_tokens": 1_000_000,
             "cache_creation_input_tokens": 1_000_000}
    rec = {"model_id": "m", "author_runs": [{"cost_usd": 9.99, "usage": usage}], "codex_calls": []}
    verified = {"m": costs.Price(2.0, 10.0, 0.2, True, "공식", cache_write=2.5)}
    assert costs.card_cost(rec, verified, "gpt-6-sol") == (pytest.approx(2.0 + 1.0 + 0.2 + 2.5), True)
    unverified = {"m": costs.Price(2.0, 10.0, 0.2, False, "2차", cache_write=2.5)}
    assert costs.card_cost(rec, unverified, "gpt-6-sol")[0] == pytest.approx(9.99)   # 미확인 단가면 CLI 보고값을 쓴다
