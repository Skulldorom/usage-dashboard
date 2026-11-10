from datetime import datetime

import httpx
import pytest

from app.providers.anthropic import AnthropicAdapter
from app.providers.custom_http import CustomHTTPAdapter
from app.providers.deepseek import DeepSeekAdapter
from app.providers.firecrawl import FirecrawlAdapter
from app.providers.openai import OpenAIAdapter
from app.providers.opencode_go import OpenCodeGoAdapter
from app.providers.openrouter import OpenRouterAdapter


def test_firecrawl_parser_uses_credit_endpoint_values_and_usage_percent():
    usage = FirecrawlAdapter.parse_usage(
        {
            "success": True,
            "data": {
                "remainingCredits": 841,
                "planCredits": 1000,
                "planName": "Free",
                "billingPeriodEnd": "2026-08-14T00:00:00Z",
            },
        },
        {"success": True, "periods": [{"totalCredits": 159}]},
    )
    assert usage.status == "healthy"
    assert usage.summary == "841 credits remaining. Free plan: 1,000 credits being refreshed on Aug 14, 2026"
    assert any(m.label == "credits_remaining" and m.value == 841 and m.maximum is None for m in usage.metrics)
    assert any(m.label == "credits_used" and m.value == 159 and m.maximum == 1000 for m in usage.metrics)
    assert any(m.label == "usage_percent" and m.value == 15.9 and m.unit == "%" for m in usage.metrics)
    assert not any("token" in m.label for m in usage.metrics)


def test_deepseek_parser_prefers_usd():
    usage = DeepSeekAdapter.parse_usage(
        {
            "is_available": True,
            "balance_infos": [
                {"currency": "USD", "total_balance": "12.50", "granted_balance": "2.50", "topped_up_balance": "10.00"}
            ],
        }
    )
    assert usage.status == "healthy"
    assert any(m.label == "total_balance" and m.value == 12.5 and m.unit == "USD" for m in usage.metrics)


def test_openai_parser_sums_costs():
    usage = OpenAIAdapter.parse_usage(
        {
            "data": [
                {"results": [{"amount": {"value": 0.25, "currency": "usd"}}]},
                {"results": [{"amount": {"value": 0.75, "currency": "usd"}}]},
            ]
        }
    )
    assert usage.metrics[0].value == 1.0


def test_anthropic_parser_sums_nested_usage_records():
    usage = AnthropicAdapter.parse_usage(
        {
            "data": [
                {
                    "results": [
                        {
                            "input_tokens": 10,
                            "output_tokens": 5,
                            "cache_creation_tokens": 2,
                            "cache_read_tokens": 3,
                            "num_requests": 4,
                        }
                    ]
                }
            ]
        }
    )
    assert usage.status == "healthy"
    assert any(m.label == "input_tokens" and m.value == 10 and m.unit == "tokens" for m in usage.metrics)
    assert any(m.label == "num_requests" and m.value == 4 and m.unit == "requests" for m in usage.metrics)


def test_anthropic_parser_and_native_history_include_billed_cost():
    raw = {
        "usage": {
            "data": [{"starting_at": "2026-09-01T00:00:00Z", "results": [{"input_tokens": 10, "num_requests": 1}]}]
        },
        "cost": {
            "data": [
                {
                    "starting_at": "2026-09-01T00:00:00Z",
                    "ending_at": "2026-09-02T00:00:00Z",
                    "results": [{"amount": "125"}, {"amount": "25"}],
                }
            ]
        },
    }
    usage = AnthropicAdapter.parse_usage(raw)
    assert any(m.label == "daily_cost" and m.value == 1.5 and m.unit == "USD" for m in usage.metrics)
    native = AnthropicAdapter.native_observations(raw)
    assert any(item["metric"] == "daily_cost" and item["value"] == 1.5 and item["unit"] == "USD" for item in native)


@pytest.mark.asyncio
async def test_anthropic_cost_enrichment_failure_preserves_usage(monkeypatch):
    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, url, **_kwargs):
            request = httpx.Request("GET", url)
            if url.endswith("/cost_report"):
                return httpx.Response(403, json={"error": "forbidden"}, request=request)
            return httpx.Response(
                200, json={"data": [{"results": [{"input_tokens": 10, "num_requests": 1}]}]}, request=request
            )

    monkeypatch.setattr("app.providers.anthropic.httpx.AsyncClient", lambda **_kwargs: FakeClient())
    usage = await AnthropicAdapter("sk-ant-admin-test").fetch_usage()
    assert usage.status == "healthy"
    assert any(metric.label == "input_tokens" and metric.value == 10 for metric in usage.metrics)
    assert not any(metric.label == "daily_cost" for metric in usage.metrics)


@pytest.mark.asyncio
async def test_anthropic_usage_failure_still_fails_provider(monkeypatch):
    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, url, **_kwargs):
            request = httpx.Request("GET", url)
            status = 200 if url.endswith("/cost_report") else 401
            return httpx.Response(status, json={}, request=request)

    monkeypatch.setattr("app.providers.anthropic.httpx.AsyncClient", lambda **_kwargs: FakeClient())
    with pytest.raises(httpx.HTTPStatusError):
        await AnthropicAdapter("invalid").fetch_usage()


def test_openrouter_parser_extracts_credit_usage():
    usage = OpenRouterAdapter.parse_usage(
        {
            "data": {
                "label": "main",
                "limit_remaining": 45.2,
                "usage_daily": 2.15,
                "usage_weekly": 12.8,
                "usage_monthly": 55,
                "limit": 100,
            }
        }
    )
    assert usage.status == "healthy"
    assert any(m.label == "limit_remaining" and m.value == 45.2 and m.maximum == 100 for m in usage.metrics)
    assert any(m.label == "usage_monthly" and m.value == 55 for m in usage.metrics)


def test_opencode_go_parser_extracts_windows_and_models():
    usage = OpenCodeGoAdapter.parse_usage(
        {
            "data": {
                "plan_type": "Go",
                "windows": {
                    "five_hour": {"usage": 4, "limit": 12, "remaining": 8, "reset_at": "2026-09-01T16:00:00Z"},
                    "weekly": {"usage": 15, "limit": 30, "remaining": 15, "reset_at": "2026-09-07T00:00:00Z"},
                    "monthly": {"usage": 50, "limit": 60, "remaining": 10, "reset_at": "2026-09-30T00:00:00Z"},
                },
                "models": [{"id": "kimi-k2.7-code", "usage": 100}],
            }
        }
    )
    assert usage.status == "healthy"
    assert any(m.label == "weekly_remaining" and m.value == 15 for m in usage.metrics)
    assert any(m.label == "models_used" for m in usage.metrics)


def test_custom_http_parser_extracts_configured_json_paths():
    config = {
        "metrics": [
            {"label": "remaining", "path": "$.credits.remaining", "unit": "credits", "maximum_path": "$.credits.limit"}
        ]
    }
    usage = CustomHTTPAdapter.parse_usage({"credits": {"remaining": 7, "limit": 10}}, config)
    assert usage.status == "healthy"
    assert usage.metrics[0].value == 7
    assert usage.metrics[0].maximum == 10


def test_custom_http_rejects_credentials_in_url():
    with pytest.raises(ValueError, match="credentials"):
        CustomHTTPAdapter._validated_config(
            {"path": "/usage", "metrics": [{"label": "used", "path": "$.used"}]}, "https://token@example.com"
        )


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
        CustomHTTPAdapter._validated_config(
            {"path": "/usage", "metrics": [{"label": "used", "path": "$.used"}]}, base_url
        )


def test_custom_http_rejects_hostname_resolving_to_private_ip(monkeypatch):
    def fake_getaddrinfo(*args, **kwargs):
        return [(None, None, None, "", ("10.0.0.5", 443))]

    monkeypatch.setattr("app.providers.custom_http.socket.getaddrinfo", fake_getaddrinfo)

    with pytest.raises(ValueError, match="private or internal"):
        CustomHTTPAdapter._validated_config(
            {"path": "/usage", "metrics": [{"label": "used", "path": "$.used"}]}, "https://api.example.com"
        )


def test_custom_http_allows_hostname_resolving_to_public_ip(monkeypatch):
    def fake_getaddrinfo(*args, **kwargs):
        return [(None, None, None, "", ("8.8.8.8", 443))]

    monkeypatch.setattr("app.providers.custom_http.socket.getaddrinfo", fake_getaddrinfo)

    config = CustomHTTPAdapter._validated_config(
        {"path": "/usage", "metrics": [{"label": "used", "path": "$.used"}]}, "https://api.example.com"
    )

    assert config["url"] == "https://api.example.com/usage"


def test_custom_http_allowlist_bypasses_internal_host_rejection(monkeypatch):
    monkeypatch.setattr("app.providers.custom_http.settings.custom_http_allowed_hosts_raw", "localhost")

    config = CustomHTTPAdapter._validated_config(
        {"path": "/usage", "metrics": [{"label": "used", "path": "$.used"}]}, "http://localhost"
    )

    assert config["url"] == "http://localhost/usage"


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"data": {"total_credits": "0.3", "total_usage": "0.2"}}, 0.1),
        ({"data": {"total_credits": "0", "total_usage": "0"}}, 0.0),
        ({"data": {"total_credits": "1", "total_usage": "2"}}, -1.0),
    ],
)
def test_openrouter_account_credits_uses_decimal_balance_arithmetic(payload, expected):
    usage = OpenRouterAdapter.parse_account_usage(payload)
    metrics = {metric.label: metric.value for metric in usage.metrics}
    assert metrics["account_credit_balance"] == expected


@pytest.mark.parametrize(
    "payload",
    [
        {"data": {}},
        {"data": {"total_credits": 1}},
        {"data": {"total_credits": "no", "total_usage": 0}},
        {"data": {"total_credits": "NaN", "total_usage": 0}},
        {"data": {"total_credits": "Infinity", "total_usage": 0}},
        {"data": {"total_credits": True, "total_usage": 0}},
    ],
)
def test_openrouter_account_credits_rejects_invalid_totals(payload):
    with pytest.raises(ValueError, match="finite total_credits or total_usage"):
        OpenRouterAdapter.parse_account_usage(payload)


@pytest.mark.asyncio
async def test_openrouter_account_mode_uses_fixed_credits_endpoint_without_redirects(monkeypatch):
    calls, client_options = [], []

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, url, **kwargs):
            calls.append((url, kwargs))
            return httpx.Response(
                200, json={"data": {"total_credits": 1, "total_usage": 0.25}}, request=httpx.Request("GET", url)
            )

    def client_factory(**kwargs):
        client_options.append(kwargs)
        return FakeClient()

    monkeypatch.setattr("app.providers.openrouter.httpx.AsyncClient", client_factory)
    usage = await OpenRouterAdapter("management-secret", extra={"monitoring_mode": "account_wide"}).fetch_usage()
    assert calls[0] == (
        "https://openrouter.ai/api/v1/credits",
        {"headers": {"Authorization": "Bearer management-secret", "Accept": "application/json"}},
    )
    assert calls[1][0] == "https://openrouter.ai/api/v1/activity"
    assert client_options == [{"timeout": 20.0, "follow_redirects": False}]
    assert usage.metrics[0].value == 0.75


@pytest.mark.parametrize(
    "base_url",
    [
        "http://openrouter.ai/api/v1",
        "https://evil.example/api/v1",
        "https://user:pass@openrouter.ai/api/v1",
        "https://openrouter.ai:443/api/v1",
        "https://openrouter.ai/api/v1?target=evil",
        "https://openrouter.ai/api/v1#evil",
    ],
)
def test_openrouter_account_mode_rejects_untrusted_base_url(base_url):
    with pytest.raises(ValueError, match="Management credentials may only be sent"):
        OpenRouterAdapter("secret", base_url=base_url, extra={"monitoring_mode": "account_wide"})


def test_openrouter_individual_mode_preserves_custom_base_url_support():
    adapter = OpenRouterAdapter("secret", base_url="https://openrouter-proxy.example/api/v1")
    assert adapter.base_url == "https://openrouter-proxy.example/api/v1"


def test_openrouter_rejects_unknown_monitoring_mode():
    with pytest.raises(ValueError, match="monitoring_mode"):
        _ = OpenRouterAdapter("secret", extra={"monitoring_mode": "unknown"}).account_wide


def test_openrouter_native_observations_preserve_empty_and_zero_metrics():
    observations = OpenRouterAdapter.native_observations(
        {
            "activity": {
                "data": [
                    {
                        "date": "2026-11-09",
                        "usage": 0,
                        "requests": 3,
                        "prompt_tokens": 0,
                        "completion_tokens": 12,
                        "reasoning_tokens": None,
                        "workspace_id": "ws_1",
                    }
                ]
            }
        }
    )
    values = {item["metric"]: item["value"] for item in observations}
    assert values == {
        "openrouter_account_spend": 0.0,
        "openrouter_account_requests": 3.0,
        "openrouter_account_prompt_tokens": 0.0,
        "openrouter_account_completion_tokens": 12.0,
    }
    assert all(item["scope"] == "ws_1" for item in observations)


def test_openrouter_sanitize_activity_rejects_float_overflow():
    with pytest.raises(ValueError, match="no valid rows"):
        OpenRouterAdapter._sanitize_activity({"data": [{"date": "2026-11-09", "usage": "1e10000"}]})


def test_openrouter_native_observations_reject_incomplete_current_utc_day(monkeypatch):
    class CurrentTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 11, 10, 12, tzinfo=tz)

    monkeypatch.setattr("app.providers.openrouter.datetime", CurrentTime)
    observations = OpenRouterAdapter.native_observations(
        {"activity": {"data": [{"date": "2026-11-10T00:00:00Z", "usage": 1}]}}
    )
    assert observations == []
