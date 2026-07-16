import pytest

from app.providers.anthropic import AnthropicAdapter
from app.providers.custom_http import CustomHTTPAdapter
from app.providers.deepseek import DeepSeekAdapter
from app.providers.firecrawl import FirecrawlAdapter
from app.providers.openai import OpenAIAdapter
from app.providers.openrouter import OpenRouterAdapter

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

def test_anthropic_parser_sums_nested_usage_records():
    usage = AnthropicAdapter.parse_usage({"data": [{"results": [{"input_tokens": 10, "output_tokens": 5, "cache_creation_tokens": 2, "cache_read_tokens": 3, "num_requests": 4}]}]})
    assert usage.status == "healthy"
    assert any(m.label == "input_tokens" and m.value == 10 and m.unit == "tokens" for m in usage.metrics)
    assert any(m.label == "num_requests" and m.value == 4 and m.unit == "requests" for m in usage.metrics)

def test_openrouter_parser_extracts_credit_usage():
    usage = OpenRouterAdapter.parse_usage({"data": {"label": "main", "limit_remaining": 45.2, "usage_daily": 2.15, "usage_weekly": 12.8, "usage_monthly": 55, "limit": 100}})
    assert usage.status == "healthy"
    assert any(m.label == "limit_remaining" and m.value == 45.2 and m.maximum == 100 for m in usage.metrics)
    assert any(m.label == "usage_monthly" and m.value == 55 for m in usage.metrics)

def test_custom_http_parser_extracts_configured_json_paths():
    config = {"metrics": [{"label": "remaining", "path": "$.credits.remaining", "unit": "credits", "maximum_path": "$.credits.limit"}]}
    usage = CustomHTTPAdapter.parse_usage({"credits": {"remaining": 7, "limit": 10}}, config)
    assert usage.status == "healthy"
    assert usage.metrics[0].value == 7
    assert usage.metrics[0].maximum == 10

def test_custom_http_rejects_credentials_in_url():
    with pytest.raises(ValueError, match="credentials"):
        CustomHTTPAdapter._validated_config({"path": "/usage", "metrics": [{"label": "used", "path": "$.used"}]}, "https://token@example.com")
