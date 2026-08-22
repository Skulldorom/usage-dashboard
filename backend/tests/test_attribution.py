"""Unit tests for Hermes attribution math (app.analytics.attribution)."""

from __future__ import annotations

from app.analytics.attribution import (
    attribute,
    normalize_provider_id,
    provider_metric_labels,
)


def test_attribute_computes_pct_and_unattributed():
    result = attribute(40.0, 31.0)
    assert result["provider_total"] == 40.0
    assert result["hermes_observed"] == 31.0
    assert result["attribution_pct"] == 77.5
    assert result["unattributed"] == 9.0


def test_attribute_never_double_counts():
    # The critical invariant: unattributed = total - observed, never total + observed.
    result = attribute(40.0, 31.0)
    assert result["unattributed"] == 40.0 - 31.0
    assert result["unattributed"] != 40.0 + 31.0


def test_attribute_without_provider_total():
    result = attribute(None, 31.0)
    assert result["provider_total"] is None
    assert result["attribution_pct"] is None
    assert result["unattributed"] is None
    assert result["hermes_observed"] == 31.0


def test_attribute_without_hermes():
    result = attribute(40.0, None)
    assert result["provider_total"] == 40.0
    assert result["hermes_observed"] is None
    assert result["attribution_pct"] is None


def test_attribute_zero_provider_total_avoids_division():
    result = attribute(0.0, 0.0)
    assert result["attribution_pct"] is None


def test_normalize_provider_id():
    assert normalize_provider_id(" Anthropic ") == "anthropic"
    assert normalize_provider_id(None) is None
    assert normalize_provider_id("") is None


def test_provider_metric_labels_maps_aliases():
    assert provider_metric_labels("cost") == ("cost", "cost_30d", "spend")
    assert provider_metric_labels("requests") == ("requests", "num_requests")
    assert provider_metric_labels("input_tokens") == ("input_tokens",)
    assert provider_metric_labels("unknown_metric") == ("unknown_metric",)
