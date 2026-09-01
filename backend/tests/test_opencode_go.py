import pytest

from app.providers.opencode_go import OpenCodeGoAdapter, _canonical_model_id, _extract_model_usage, _extract_windows


def test_parser_extracts_all_three_windows():
    usage = OpenCodeGoAdapter.parse_usage(
        {
            "data": {
                "plan_type": "Go",
                "windows": {
                    "five_hour": {"usage": 3.5, "limit": 12, "remaining": 8.5, "reset_at": "2026-09-01T16:00:00Z"},
                    "weekly": {"usage": 10, "limit": 30, "remaining": 20, "reset_at": "2026-09-07T00:00:00Z"},
                    "monthly": {"usage": 25, "limit": 60, "remaining": 35, "reset_at": "2026-09-30T00:00:00Z"},
                },
                "use_balance": False,
            }
        }
    )
    assert usage.status == "healthy"
    assert "$8.50/12 5h" in usage.summary
    by_label = {m.label: m for m in usage.metrics}
    assert by_label["five_hour_usage"].value == 3.5
    assert by_label["five_hour_remaining"].value == 8.5
    assert by_label["five_hour_remaining"].maximum == 12
    assert by_label["five_hour_limit"].value == 12
    assert by_label["weekly_remaining"].value == 20
    assert by_label["monthly_remaining"].value == 35
    assert by_label["balance_fallback_enabled"].value is False
    assert by_label["exhausted"].value is False


def test_parser_computes_remaining_when_missing():
    usage = OpenCodeGoAdapter.parse_usage(
        {
            "data": {
                "five_hour_usage": 9.0,
                "weekly_usage": 12.0,
                "monthly_usage": 40.0,
            }
        }
    )
    by_label = {m.label: m for m in usage.metrics}
    assert by_label["five_hour_remaining"].value == 3.0
    assert by_label["weekly_remaining"].value == 18.0
    assert by_label["monthly_remaining"].value == 20.0


def test_parser_flags_exhausted_when_remaining_zero():
    usage = OpenCodeGoAdapter.parse_usage(
        {
            "data": {
                "windows": {
                    "five_hour": {"usage": 12, "limit": 12, "remaining": 0},
                    "weekly": {"usage": 30, "limit": 30, "remaining": 0},
                    "monthly": {"usage": 60, "limit": 60, "remaining": 0},
                },
                "use_balance": True,
            }
        }
    )
    assert usage.status == "degraded"
    by_label = {m.label: m for m in usage.metrics}
    assert by_label["exhausted"].value is True
    assert by_label["balance_fallback_enabled"].value is True


def test_parser_extracts_per_model_usage_and_limits():
    usage = OpenCodeGoAdapter.parse_usage(
        {
            "data": {
                "models": [
                    {"id": "kimi-k2.7-code", "usage": 500},
                    {"id": "deepseek-v4-pro", "used": 5200},
                ]
            }
        }
    )
    by_label = {m.label: m for m in usage.metrics}
    models = by_label["models_used"].value
    assert len(models) == 2
    assert models[0]["model"] == "kimi-k2.7-code"
    assert models[0]["monthly_limit"] == 6750
    assert models[0]["monthly_remaining"] == 6250
    assert models[1]["model"] == "deepseek-v4-pro"
    assert models[1]["monthly_remaining"] == 0
    assert by_label["exhausted"].value is True


def test_parser_tolerates_unknown_models():
    usage = OpenCodeGoAdapter.parse_usage(
        {"data": {"models": [{"id": "unknown-model", "usage": 42}]}}
    )
    by_label = {m.label: m for m in usage.metrics}
    models = by_label["models_used"].value
    assert models[0]["model"] == "unknown-model"
    assert "monthly_limit" not in models[0]


def test_parser_empty_response_still_healthy():
    usage = OpenCodeGoAdapter.parse_usage({})
    assert usage.status == "healthy"
    assert "fetched" in usage.summary


def test_extract_windows_fills_default_limits():
    windows = _extract_windows({"usage": 5})
    assert windows["monthly"]["limit"] == 60
    assert windows["monthly"]["remaining"] == 55


def test_extract_model_usage_from_dict_and_list():
    assert _extract_model_usage({"models": {"kimi-k2.7-code": 10}}) == {"kimi-k2.7-code": 10}
    assert _extract_model_usage({"models": [{"id": "deepseek-v4-pro", "requests": 99}]}) == {"deepseek-v4-pro": 99}


def test_canonical_model_id_normalization():
    assert _canonical_model_id("Kimi-K2.7-Code") == "kimi-k2.7-code"
    assert _canonical_model_id("deepseek_v4_pro") == "deepseek-v4-pro"
    assert _canonical_model_id("not-a-known-model") is None


def test_metric_names_are_registered():
    assert OpenCodeGoAdapter.id == "opencode-go"
    assert "five_hour_remaining" in OpenCodeGoAdapter.metric_names
    assert "weekly_remaining" in OpenCodeGoAdapter.metric_names
    assert "monthly_remaining" in OpenCodeGoAdapter.metric_names
