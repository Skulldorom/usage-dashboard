"""Unit tests for canonical activity dimensions (app.analytics.capabilities)."""

from __future__ import annotations

from app.analytics.capabilities import (
    activity_dimensions,
    activity_metric_labels,
    analytics_spec,
    metric_spec,
)


def _spec(**kwargs):
    return analytics_spec(supported=True, metrics=kwargs)


def test_token_classes_sum_to_single_dimension():
    caps = _spec(
        input_tokens=metric_spec(type_="counter", unit="tokens"),
        output_tokens=metric_spec(type_="counter", unit="tokens"),
        cache_read_tokens=metric_spec(type_="counter", unit="tokens"),
    )
    dims = activity_dimensions(caps)
    assert set(dims) == {"tokens"}
    assert len(dims["tokens"]) == 3


def test_requests_and_tokens_are_distinct_dimensions():
    caps = _spec(
        input_tokens=metric_spec(type_="counter", unit="tokens"),
        num_requests=metric_spec(type_="counter", unit="requests"),
    )
    dims = activity_dimensions(caps)
    assert set(dims) == {"tokens", "requests"}


def test_overlapping_windows_do_not_double_count():
    caps = _spec(
        usage_daily=metric_spec(type_="counter", unit="credits", window="24h"),
        usage_weekly=metric_spec(type_="counter", unit="credits", window="7d"),
        usage_monthly=metric_spec(type_="counter", unit="credits", window="30d", overview=True),
    )
    dims = activity_dimensions(caps)
    assert set(dims) == {"credits"}
    assert [label for label, _ in dims["credits"]] == ["usage_monthly"]


def test_overlapping_windows_without_overview_picks_longest():
    caps = _spec(
        usage_daily=metric_spec(type_="counter", unit="credits", window="24h"),
        usage_weekly=metric_spec(type_="counter", unit="credits", window="7d"),
    )
    dims = activity_dimensions(caps)
    assert [label for label, _ in dims["credits"]] == ["usage_weekly"]


def test_state_metrics_excluded_from_activity():
    caps = _spec(
        total_balance=metric_spec(type_="balance", unit="USD"),
        limit_remaining=metric_spec(type_="remaining", unit="credits"),
        cost_30d=metric_spec(type_="rolling_total", unit="USD"),
        plan=metric_spec(type_="gauge", unit="credits"),
    )
    assert activity_dimensions(caps) == {}


def test_utilization_percent_excluded_from_activity():
    caps = _spec(
        usage_percent=metric_spec(type_="counter", unit="%", utilization=True, maximum=100),
        credits_used=metric_spec(type_="counter", unit="credits"),
    )
    dims = activity_dimensions(caps)
    assert set(dims) == {"credits"}


def test_cost_unit_maps_to_cost_dimension():
    caps = _spec(
        daily_cost=metric_spec(type_="counter", unit="USD"),
    )
    dims = activity_dimensions(caps)
    assert set(dims) == {"cost"}


def test_unknown_unit_excluded():
    caps = _spec(
        some_counter=metric_spec(type_="counter", unit="widgets"),
    )
    assert activity_dimensions(caps) == {}


def test_activity_metric_labels_flattens():
    caps = _spec(
        input_tokens=metric_spec(type_="counter", unit="tokens"),
        output_tokens=metric_spec(type_="counter", unit="tokens"),
    )
    labels = activity_metric_labels(activity_dimensions(caps))
    assert labels == {"tokens": ["input_tokens", "output_tokens"]}
