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

@pytest.mark.parametrize(
    "base_url",
    [
        "http://127.0.0.1",
        "http://localhost",
        "http://169.254.169.254",
        "http://10.0.0.1",
        "http://172.16.0.1",
        "http://192.168.1.1",
        "http://[::1]",
        "http://[fc00::1]",
        "http://[fe80::1]",
    ],
)
def test_custom_http_rejects_private_and_internal_hosts(base_url):
    with pytest.raises(ValueError, match="host|IP"):
        CustomHTTPAdapter._validated_config({"path": "/usage", "metrics": [{"label": "used", "path": "$.used"}]}, base_url)


def test_custom_http_rejects_hostname_resolving_to_private_ip(monkeypatch):
    def fake_getaddrinfo(*args, **kwargs):
        return [(None, None, None, "", ("10.0.0.5", 443))]

    monkeypatch.setattr("app.providers.custom_http.socket.getaddrinfo", fake_getaddrinfo)

    with pytest.raises(ValueError, match="private or internal"):
        CustomHTTPAdapter._validated_config({"path": "/usage", "metrics": [{"label": "used", "path": "$.used"}]}, "https://api.example.com")


def test_custom_http_allows_hostname_resolving_to_public_ip(monkeypatch):
    def fake_getaddrinfo(*args, **kwargs):
        return [(None, None, None, "", ("8.8.8.8", 443))]

    monkeypatch.setattr("app.providers.custom_http.socket.getaddrinfo", fake_getaddrinfo)

    config = CustomHTTPAdapter._validated_config({"path": "/usage", "metrics": [{"label": "used", "path": "$.used"}]}, "https://api.example.com")

    assert config["url"] == "https://api.example.com/usage"


def test_custom_http_allowlist_bypasses_internal_host_rejection(monkeypatch):
    monkeypatch.setattr("app.providers.custom_http.settings.custom_http_allowed_hosts_raw", "localhost")

    config = CustomHTTPAdapter._validated_config({"path": "/usage", "metrics": [{"label": "used", "path": "$.used"}]}, "http://localhost")

    assert config["url"] == "http://localhost/usage"
