"""Unit tests for Hermes attribution math (app.analytics.attribution)."""

from __future__ import annotations

from app.analytics.attribution import (
    attribute,
    normalize_provider_id,
    provider_metric_labels,
)


def test_partial_hermes_less_than_provider():
    result = attribute(40.0, 31.0)
    assert result["status"] == "partial"
    assert result["attributed"] == 31.0
    assert result["unattributed"] == 9.0
    assert result["overage"] == 0.0
    assert result["attribution_pct"] == 77.5


def test_matched_hermes_equals_provider():
    result = attribute(40.0, 40.0)
    assert result["status"] == "matched"
    assert result["attributed"] == 40.0
    assert result["unattributed"] == 0.0
    assert result["overage"] == 0.0
    assert result["attribution_pct"] == 100.0


def test_over_observed_hermes_exceeds_provider():
    result = attribute(40.0, 48.0)
    assert result["status"] == "over_observed"
    assert result["attributed"] == 40.0
    assert result["unattributed"] == 0.0
    assert result["overage"] == 8.0


def test_over_observed_pct_capped_at_100():
    result = attribute(10.0, 1000.0)
    assert result["attribution_pct"] == 100.0
    assert result["status"] == "over_observed"


def test_unattributed_never_negative():
    result = attribute(10.0, 1000.0)
    assert result["unattributed"] == 0.0
    assert result["unattributed"] >= 0


def test_provider_total_zero_with_hermes():
    result = attribute(0.0, 5.0)
    assert result["status"] == "over_observed"
    assert result["attribution_pct"] is None
    assert result["overage"] == 5.0


def test_provider_total_zero_both_zero():
    result = attribute(0.0, 0.0)
    assert result["status"] == "matched"
    assert result["attribution_pct"] is None


def test_hermes_only():
    result = attribute(None, 31.0)
    assert result["status"] == "hermes_only"
    assert result["provider_total"] is None
    assert result["hermes_observed"] == 31.0
    assert result["attribution_pct"] is None


def test_provider_only():
    result = attribute(40.0, None)
    assert result["status"] == "provider_only"
    assert result["provider_total"] == 40.0
    assert result["hermes_observed"] is None
    assert result["attribution_pct"] is None


def test_both_unavailable():
    result = attribute(None, None)
    assert result["status"] == "unavailable"
    assert result["provider_total"] is None
    assert result["hermes_observed"] is None


def test_never_double_counts():
    # attributed + unattributed always equals the authoritative provider total,
    # never provider_total + hermes_observed.
    result = attribute(40.0, 31.0)
    assert result["attributed"] + result["unattributed"] == 40.0
    assert result["attributed"] != 40.0 + 31.0


def test_normalize_provider_id():
    assert normalize_provider_id(" Anthropic ") == "anthropic"
    assert normalize_provider_id(None) is None
    assert normalize_provider_id("") is None


def test_provider_metric_labels_maps_aliases():
    assert provider_metric_labels("cost") == ("cost", "cost_30d", "spend")
    assert provider_metric_labels("requests") == ("requests", "num_requests")
    assert provider_metric_labels("input_tokens") == ("input_tokens",)
    assert provider_metric_labels("unknown_metric") == ("unknown_metric",)
