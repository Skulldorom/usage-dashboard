import httpx
import pytest

from app.providers.errors import AUTHENTICATION, CONFIGURATION, INVALID_RESPONSE, RATE_LIMIT, SCHEMA_CHANGED, ProviderError
from app.providers.minimax import MiniMaxAdapter


def metrics_by_label(usage):
    return {metric.label: metric for metric in usage.metrics}


def current_response(groups=None):
    return {
        "model_remains": groups or [{
            "model_name": "general",
            "current_interval_total_count": 0,
            "current_interval_usage_count": 0,
            "current_interval_remaining_percent": 63,
            "current_interval_status": 1,
            "current_weekly_total_count": 0,
            "current_weekly_usage_count": 0,
            "current_weekly_remaining_percent": 96,
            "current_weekly_status": 1,
            "end_time": 1782399600000,
            "weekly_end_time": 1782691200000,
        }],
        "base_resp": {"status_code": 0, "status_msg": "success"},
    }


def test_parser_uses_remaining_percentages_and_normalizes_resets():
    usage = MiniMaxAdapter.parse_usage(current_response())

    metrics = metrics_by_label(usage)
    assert usage.status == "healthy"
    assert metrics["five_hour_remaining_percent"].value == 63
    assert metrics["five_hour_used_percent"].value == 37
    assert metrics["weekly_remaining_percent"].value == 96
    assert metrics["weekly_used_percent"].value == 4
    assert metrics["five_hour_reset_at"].value == "2026-06-25T15:00:00+00:00"
    assert metrics["weekly_reset_at"].value == "2026-06-29T00:00:00+00:00"
    assert metrics["exhausted"].value is False


def test_parser_uses_general_without_aggregating_other_resource_groups():
    response = current_response([
        {"model_name": "video", "current_interval_remaining_percent": 10, "current_interval_status": 2},
        {"model_name": "general", "current_interval_remaining_percent": 75, "current_interval_status": 1, "current_weekly_remaining_percent": 50, "current_weekly_status": 1},
    ])
    usage = MiniMaxAdapter.parse_usage(response)
    metrics = metrics_by_label(usage)

    assert usage.status == "healthy"
    assert metrics["five_hour_used_percent"].value == 25
    assert len(metrics["resource_groups"].value) == 2
    assert metrics["resource_groups"].value[0]["five_hour_used_percent"] == 90


def test_parser_handles_exhausted_and_unlimited_statuses():
    exhausted = MiniMaxAdapter.parse_usage(current_response([{
        "model_name": "general", "current_interval_remaining_percent": 0, "current_interval_status": 2,
    }]))
    unlimited = MiniMaxAdapter.parse_usage(current_response([{
        "model_name": "general", "current_interval_total_count": 0, "current_interval_usage_count": 0,
        "current_interval_remaining_percent": 0, "current_interval_status": 3,
    }]))

    assert exhausted.status == "degraded"
    assert metrics_by_label(exhausted)["exhausted"].value is True
    assert unlimited.status == "healthy"
    assert metrics_by_label(unlimited)["exhausted"].value is False


def test_parser_tolerates_optional_fields_and_unknown_resource_group():
    usage = MiniMaxAdapter.parse_usage(current_response([{
        "model_name": "future-resource", "current_interval_remaining_percent": 45,
    }]))
    metrics = metrics_by_label(usage)

    assert usage.status == "healthy"
    assert metrics["five_hour_used_percent"].value == 55
    assert "weekly_used_percent" not in metrics
    assert "five_hour_reset_at" not in metrics


@pytest.mark.parametrize(
    ("payload", "category"),
    [
        ({"base_resp": {"status_code": 2062, "status_msg": "no active token plan subscription"}}, CONFIGURATION),
        ({"base_resp": {"status_code": 1234, "status_msg": "invalid subscription key"}}, AUTHENTICATION),
        ({"base_resp": {"status_code": 1234, "status_msg": "unknown failure"}}, INVALID_RESPONSE),
        ({}, SCHEMA_CHANGED),
    ],
)
def test_parser_rejects_business_and_unusable_responses(payload, category):
    with pytest.raises(ProviderError) as error:
        MiniMaxAdapter.parse_usage(payload)
    assert error.value.category == category


@pytest.mark.asyncio
@pytest.mark.parametrize(("status_code", "category"), [(401, AUTHENTICATION), (403, AUTHENTICATION), (429, RATE_LIMIT)])
async def test_fetch_classifies_http_authentication_and_rate_limits(monkeypatch, status_code, category):
    def handler(request):
        return httpx.Response(status_code, request=request, json={"message": "not authorized"})

    original = httpx.AsyncClient
    monkeypatch.setattr("app.providers.minimax.httpx.AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))
    with pytest.raises(ProviderError) as error:
        await MiniMaxAdapter("subscription-key").fetch_usage()
    assert error.value.category == category


@pytest.mark.asyncio
async def test_fetch_rejects_malformed_json(monkeypatch):
    def handler(request):
        return httpx.Response(200, request=request, content=b"not json", headers={"content-type": "application/json"})

    original = httpx.AsyncClient
    monkeypatch.setattr("app.providers.minimax.httpx.AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))
    with pytest.raises(ProviderError) as error:
        await MiniMaxAdapter("subscription-key").fetch_usage()
    assert error.value.category == INVALID_RESPONSE
