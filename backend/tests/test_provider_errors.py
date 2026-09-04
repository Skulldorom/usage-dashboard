"""Tests for the generic provider error model, sanitization, and classification."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import httpx
import pytest

from app.providers.errors import (
    AUTHENTICATION,
    NETWORK,
    PARSE_ERROR,
    RATE_LIMIT,
    SCHEMA_CHANGED,
    TIMEOUT,
    UPSTREAM_HTTP,
    ProviderError,
    classify_exception,
    classify_http_status,
    redact_text,
    sanitize_url,
    truncate,
)
from app.providers.codex import CodexAdapter


# ---------------------------------------------------------------------------
# HTTP status classification
# ---------------------------------------------------------------------------


def test_classify_http_status_categories():
    assert classify_http_status(401) == (AUTHENTICATION, False)
    assert classify_http_status(403) == (AUTHENTICATION, False)
    assert classify_http_status(404) == (UPSTREAM_HTTP, False)
    assert classify_http_status(408) == (TIMEOUT, True)
    assert classify_http_status(429) == (RATE_LIMIT, True)
    assert classify_http_status(500)[0] == UPSTREAM_HTTP
    assert classify_http_status(503)[0] == UPSTREAM_HTTP


def test_classify_http_status_5xx_is_retryable():
    assert classify_http_status(500)[1] is True
    assert classify_http_status(503)[1] is True


# ---------------------------------------------------------------------------
# Sanitization / redaction
# ---------------------------------------------------------------------------


def test_redact_text_strips_bearer_token():
    assert redact_text("Authorization: Bearer abcdef1234567890") == "Authorization: Bearer [REDACTED]"


def test_redact_text_strips_api_keys_and_refresh_tokens():
    text = "refresh_token=xyz-secret-token123 api_key=sk-ant-abcdef123456"
    redacted = redact_text(text)
    assert "xyz-secret-token123" not in redacted
    assert "sk-ant-abcdef123456" not in redacted


def test_redact_text_strips_cookies():
    redacted = redact_text("Set-Cookie: session=abc123secret; Path=/")
    assert "abc123secret" not in redacted


def test_sanitize_url_redacts_query_params():
    url = "https://api.example.com/usage?api_key=sk-1234567890&foo=bar"
    sanitized = sanitize_url(url)
    assert "sk-1234567890" not in sanitized
    assert "api_key=[REDACTED]" in sanitized


def test_truncate_bounds_long_bodies():
    long_body = "x" * 5000
    truncated = truncate(long_body)
    assert len(truncated) <= 1024 + 40  # budget + ellipsis suffix
    assert "[truncated" in truncated


def test_provider_error_to_dict_is_sanitized():
    err = ProviderError(
        category=SCHEMA_CHANGED,
        message="OpenAI returned Codex usage data in an unsupported format.",
        http_status=200,
        stage="parse_response",
        retryable=False,
        response_body='{"secret": "sk-1234567890"}',
    )
    d = err.to_dict()
    assert d["category"] == SCHEMA_CHANGED
    assert "sk-1234567890" not in d["message"]
    # to_dict never exposes the response body or raw payloads.
    assert "response_body" not in d


# ---------------------------------------------------------------------------
# Exception classification
# ---------------------------------------------------------------------------


def _http_error(status: int, body: str = "", content_type: str = "application/json"):
    request = httpx.Request("GET", "https://api.example.com/usage")
    response = httpx.Response(status, text=body, request=request, headers={"content-type": content_type})
    return httpx.HTTPStatusError("boom", request=request, response=response)


def test_classify_exception_http_status_error_preserves_context():
    err = classify_exception(_http_error(429, '{"detail":"Too Many Requests"}'), stage="fetch_usage")
    assert err.category == RATE_LIMIT
    assert err.http_status == 429
    assert err.retryable is True
    assert err.stage == "fetch_usage"
    assert err.response_body == '{"detail":"Too Many Requests"}'


def test_classify_exception_redacts_token_in_response_body():
    err = classify_exception(_http_error(401, '{"access_token":"sk-1234567890"}'), stage="fetch_usage")
    assert err.category == AUTHENTICATION
    assert "sk-1234567890" not in err.response_body


def test_classify_exception_timeout_and_connect():
    timeout = classify_exception(httpx.ReadTimeout("timed out"), stage="fetch_usage")
    assert timeout.category == TIMEOUT
    assert timeout.retryable is True

    connect = classify_exception(httpx.ConnectError("refused"), stage="fetch_usage")
    assert connect.category == NETWORK


def test_classify_exception_json_decode_error():
    err = classify_exception(json.JSONDecodeError("bad", "doc", 0), stage="parse_response")
    assert err.category == PARSE_ERROR


def test_classify_exception_passes_through_provider_error():
    original = ProviderError(category=RATE_LIMIT, message="rate limited", stage="fetch_usage")
    out = classify_exception(original, stage="other")
    assert out is original


# ---------------------------------------------------------------------------
# Codex-specific classification
# ---------------------------------------------------------------------------


def _codex_secret() -> str:
    return json.dumps({"access_token": "access-token", "refresh_token": "refresh-token"})


async def _fetch_with_status(status: int, body: str = "{}", content_type: str = "application/json"):
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, text=body, headers={"content-type": content_type})

    adapter = CodexAdapter(_codex_secret(), transport=httpx.MockTransport(handler))
    return await adapter.fetch_usage()


@pytest.mark.asyncio
async def test_codex_access_token_rejected_is_authentication():
    with pytest.raises(ProviderError) as exc_info:
        await _fetch_with_status(401, '{"error":"invalid_token"}')
    err = exc_info.value
    assert err.category == AUTHENTICATION
    assert err.stage == "fetch_usage"
    assert err.http_status == 401
    assert err.retryable is False


@pytest.mark.asyncio
async def test_codex_rate_limit_is_classified():
    with pytest.raises(ProviderError) as exc_info:
        await _fetch_with_status(429, '{"detail":"Too Many Requests"}')
    assert exc_info.value.category == RATE_LIMIT


@pytest.mark.asyncio
async def test_codex_endpoint_not_found_is_upstream_http():
    with pytest.raises(ProviderError) as exc_info:
        await _fetch_with_status(404, "not found")
    assert exc_info.value.category == UPSTREAM_HTTP


@pytest.mark.asyncio
async def test_codex_unexpected_schema_is_schema_changed():
    with pytest.raises(ProviderError) as exc_info:
        await _fetch_with_status(200, '{"unexpected": "envelope"}')
    err = exc_info.value
    assert err.category == SCHEMA_CHANGED
    assert "unsupported format" in err.message


@pytest.mark.asyncio
async def test_codex_non_json_response_is_invalid_response():
    with pytest.raises(ProviderError) as exc_info:
        await _fetch_with_status(200, "<html>not json</html>", content_type="text/html")
    assert exc_info.value.category == "invalid_response"
