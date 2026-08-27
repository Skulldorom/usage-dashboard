from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.providers.codex import CodexAdapter, CodexCredentials


def test_codex_parser_reports_session_weekly_review_and_reset_credits_left():
    data = {
        "plan_type": "Pro",
        "rate_limits_by_limit_id": {
            "codex": {
                "limit_reached": False,
                "primary_window": {"used_percent": 42.4, "reset_at": "2026-08-14T12:30:00Z"},
                "secondary_window": {"percent_used": 88, "resets_at": "2026-08-20T00:00:00Z"},
                "rate_limit_reset_credits": {"available_count": 2},
            },
            "code_review": {
                "limit_reached": True,
                "primary_window": {"used_percent": 12, "resetAt": "2026-08-14T14:00:00Z"},
                "secondary_window": {"used_percent": 34, "reset_at": "2026-08-21T00:00:00Z"},
            },
        },
    }

    usage = CodexAdapter.parse_usage(data)

    assert usage.status == "healthy"
    assert usage.summary == "Pro - 57.6% session left, 12% weekly left"
    assert any(m.label == "plan_type" and m.value == "Pro" for m in usage.metrics)
    assert any(m.label == "session_remaining_percent" and m.value == 57.6 and m.unit == "%" and m.maximum == 100 for m in usage.metrics)
    assert any(m.label == "weekly_remaining_percent" and m.value == 12 and m.unit == "%" and m.maximum == 100 for m in usage.metrics)
    assert any(m.label == "session_reset_at" and m.value == "2026-08-14T12:30:00Z" for m in usage.metrics)
    assert any(m.label == "review_session_remaining_percent" and m.value == 88 for m in usage.metrics)
    assert any(m.label == "review_limit_reached" and m.value is True for m in usage.metrics)
    assert any(m.label == "reset_credits_available" and m.value == 2 for m in usage.metrics)


def test_codex_parser_reports_weekly_left_without_session_usage():
    usage = CodexAdapter.parse_usage({
        "plan_type": "Pro",
        "rate_limit": {
            "secondary_window": {"used_percent": 73, "reset_at": "2026-08-20T00:00:00Z"},
        },
    })

    assert usage.status == "healthy"
    assert usage.summary == "Pro - 27% weekly left"
    assert not any(m.label == "session_remaining_percent" for m in usage.metrics)
    assert any(m.label == "weekly_remaining_percent" and m.value == 27 and m.unit == "%" and m.maximum == 100 for m in usage.metrics)


def test_codex_parser_converts_numeric_reset_timestamps_to_iso_utc():
    # Observed current wham/usage response shape: reset_at is a Unix timestamp
    # (seconds since epoch), not a string.
    data = {
        "plan_type": "Pro",
        "rate_limit": {
            "primary_window": {
                "reset_at": 1787836140,
                "used_percent": 100,
                "reset_after_seconds": 7398,
                "limit_window_seconds": 18000,
            },
            "secondary_window": {
                "reset_at": 1788338296,
                "used_percent": 16,
                "reset_after_seconds": 509554,
                "limit_window_seconds": 604800,
            },
        },
    }

    usage = CodexAdapter.parse_usage(data)

    assert usage.status == "healthy"
    assert any(m.label == "session_remaining_percent" and m.value == 0 and m.unit == "%" for m in usage.metrics)
    assert any(m.label == "weekly_remaining_percent" and m.value == 84 and m.unit == "%" for m in usage.metrics)
    assert any(m.label == "session_reset_at" and m.value == "2026-08-27T13:09:00Z" for m in usage.metrics)
    assert any(m.label == "weekly_reset_at" and m.value == "2026-09-02T08:38:16Z" for m in usage.metrics)


def test_codex_parser_accepts_float_unix_reset_timestamps():
    usage = CodexAdapter.parse_usage({
        "plan_type": "Pro",
        "rate_limit": {
            "primary_window": {"used_percent": 20, "reset_at": 1787836140.0},
            "secondary_window": {"used_percent": 10, "reset_at": 1788338296.5},
        },
    })

    assert any(m.label == "session_reset_at" and m.value == "2026-08-27T13:09:00Z" for m in usage.metrics)
    assert any(m.label == "weekly_reset_at" and m.value == "2026-09-02T08:38:16Z" for m in usage.metrics)


def test_codex_parser_omits_reset_metric_when_reset_at_missing():
    usage = CodexAdapter.parse_usage({
        "plan_type": "Pro",
        "rate_limit": {
            "primary_window": {"used_percent": 12},
            "secondary_window": {"used_percent": 88},
        },
    })

    assert any(m.label == "session_remaining_percent" and m.value == 88 for m in usage.metrics)
    assert any(m.label == "weekly_remaining_percent" and m.value == 12 for m in usage.metrics)
    assert not any(m.label == "session_reset_at" for m in usage.metrics)
    assert not any(m.label == "weekly_reset_at" for m in usage.metrics)


def test_codex_parser_rejects_invalid_numeric_reset_values():
    usage = CodexAdapter.parse_usage({
        "plan_type": "Pro",
        "rate_limit": {
            "primary_window": {"used_percent": 40, "reset_at": float("nan")},
            "secondary_window": {"used_percent": 40, "reset_at": float("inf")},
        },
    })

    assert any(m.label == "session_remaining_percent" and m.value == 60 for m in usage.metrics)
    assert any(m.label == "weekly_remaining_percent" and m.value == 60 for m in usage.metrics)
    assert not any(m.label == "session_reset_at" for m in usage.metrics)
    assert not any(m.label == "weekly_reset_at" for m in usage.metrics)

    # Boolean and non-numeric reset values must also be discarded.
    usage = CodexAdapter.parse_usage({
        "plan_type": "Pro",
        "rate_limit": {
            "primary_window": {"used_percent": 40, "reset_at": True},
            "secondary_window": {"used_percent": 40, "reset_at": [1788338296]},
        },
    })
    assert not any(m.label == "session_reset_at" for m in usage.metrics)
    assert not any(m.label == "weekly_reset_at" for m in usage.metrics)


def test_codex_parser_rejects_out_of_range_reset_timestamps():
    usage = CodexAdapter.parse_usage({
        "plan_type": "Pro",
        "rate_limit": {
            "primary_window": {"used_percent": 40, "reset_at": 1e20},
        },
    })

    assert any(m.label == "session_remaining_percent" and m.value == 60 for m in usage.metrics)
    assert not any(m.label == "session_reset_at" for m in usage.metrics)



def test_codex_parser_accepts_weekly_window_aliases_and_string_percentages():
    usage = CodexAdapter.parse_usage({
        "plan_type": "Team",
        "rate_limits_by_limit_id": {
            "codex": {
                "weekly_window": {"usage_percent": "0%", "reset_time": "2026-08-27T00:00:00Z"},
            },
            "code_review": {
                "weekly_window": {"usage_percent": "90%", "reset_at": "2026-08-27T00:00:00Z"},
            },
        },
    })

    assert usage.summary == "Team - 100% weekly left"
    assert any(m.label == "weekly_remaining_percent" and m.value == 100 for m in usage.metrics)
    assert any(m.label == "weekly_reset_at" and m.value == "2026-08-27T00:00:00Z" for m in usage.metrics)
    assert any(m.label == "review_weekly_remaining_percent" and m.value == 10 for m in usage.metrics)


def test_codex_parser_accepts_windows_collection_and_remaining_percent():
    usage = CodexAdapter.parse_usage({
        "plan_type": "Pro",
        "rate_limit": {
            "windows": [
                {"type": "session", "remaining_percent": "88"},
                {"type": "weekly", "remaining_pct": 62.5, "resetAt": "2026-08-28T00:00:00Z"},
            ],
        },
    })

    assert any(m.label == "session_remaining_percent" and m.value == 88 for m in usage.metrics)
    assert any(m.label == "weekly_remaining_percent" and m.value == 62.5 for m in usage.metrics)
    assert any(m.label == "weekly_reset_at" and m.value == "2026-08-28T00:00:00Z" for m in usage.metrics)


def test_codex_parser_leaves_missing_weekly_window_unavailable():
    usage = CodexAdapter.parse_usage({
        "plan_type": "Free",
        "rate_limit": {
            "primary_window": {"used_percent": 12, "reset_at": "2026-08-21T00:00:00Z"},
        },
    })

    assert any(m.label == "session_remaining_percent" for m in usage.metrics)
    assert not any(m.label == "weekly_remaining_percent" for m in usage.metrics)


def test_codex_credentials_require_refresh_token_inside_encrypted_secret():
    credentials = CodexCredentials.from_secret_json(
        '{"access_token":"access-token","refresh_token":"refresh-token","expires_at":"2026-08-14T12:00:00+00:00"}'
    )

    assert credentials.access_token == "access-token"
    assert credentials.refresh_token == "refresh-token"
    assert credentials.to_secret_json().startswith("{")

    with pytest.raises(ValueError, match="JSON OAuth token bundle"):
        CodexCredentials.from_secret_json("access-token-only")

    with pytest.raises(ValueError, match="refresh_token"):
        CodexCredentials.from_secret_json('{"access_token":"access-token"}')

    with pytest.raises(ValueError, match="plaintext extra"):
        CodexCredentials.from_secret_json(
            '{"access_token":"access-token"}',
            extra={"refresh_token": "do-not-store-here"},
        )


@pytest.mark.asyncio
async def test_codex_adapter_refreshes_expiring_access_token_and_reports_update():
    expires_soon = datetime.now(UTC) + timedelta(seconds=30)
    secret = CodexCredentials(
        access_token="old-access",
        refresh_token="refresh-token",
        expires_at=expires_soon,
        account_id="acct_123",
    ).to_secret_json()
    requests = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/oauth/token":
            return httpx.Response(
                200,
                json={"access_token": "new-access", "refresh_token": "new-refresh", "expires_in": 3600},
            )
        assert request.url.host == "chatgpt.com"
        assert request.headers["Authorization"] == "Bearer new-access"
        assert request.headers["ChatGPT-Account-ID"] == "acct_123"
        return httpx.Response(
            200,
            json={
                "plan_type": "Plus",
                "rate_limit": {
                    "primary_window": {"used_percent": 10, "reset_at": "2026-08-14T12:00:00Z"},
                    "secondary_window": {"used_percent": 20, "reset_at": "2026-08-20T00:00:00Z"},
                },
            },
        )

    adapter = CodexAdapter(secret, transport=httpx.MockTransport(handler))

    usage = await adapter.fetch_usage()

    assert usage.status == "healthy"
    updated = adapter.updated_secret
    assert updated is not None
    updated_credentials = CodexCredentials.from_secret_json(updated)
    assert updated_credentials.access_token == "new-access"
    assert updated_credentials.refresh_token == "new-refresh"
    assert updated_credentials.expires_at > datetime.now(UTC) + timedelta(minutes=50)
    assert [request.url.path for request in requests] == ["/oauth/token", "/backend-api/wham/usage"]
