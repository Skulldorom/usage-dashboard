from app.providers.deepseek import DeepSeekAdapter
from app.providers.firecrawl import FirecrawlAdapter
from app.providers.openai import OpenAIAdapter

def test_firecrawl_parser():
    usage = FirecrawlAdapter.parse_usage({"success": True, "data": {"remainingTokens": 1000, "planTokens": 5000}}, {"success": True, "periods": [{"totalCredits": 42}]})
    assert usage.status == "healthy"
    assert any(m.label == "used_tokens" and m.value == 4000 for m in usage.metrics)

def test_deepseek_parser_prefers_usd():
    usage = DeepSeekAdapter.parse_usage({"is_available": True, "balance_infos": [{"currency": "USD", "total_balance": "12.50", "granted_balance": "2.50", "topped_up_balance": "10.00"}]})
    assert usage.status == "healthy"
    assert any(m.label == "total_balance" and m.value == 12.5 and m.unit == "USD" for m in usage.metrics)

def test_openai_parser_sums_costs():
    usage = OpenAIAdapter.parse_usage({"data": [{"results": [{"amount": {"value": 0.25, "currency": "usd"}}]}, {"results": [{"amount": {"value": 0.75, "currency": "usd"}}]}]})
    assert usage.metrics[0].value == 1.0
