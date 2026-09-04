"""Unit tests for the analytics engine (pure functions, no DB)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.analytics.aggregation import bucketize, series_coverage
from app.analytics.capabilities import analytics_spec, metric_spec
from app.analytics.confidence import confidence_level
from app.analytics.forecast import forecast_for_metric, rates_from_deltas, sustainable_pacing
from app.analytics.normalizer import normalize_native, normalize_snapshots
from app.analytics.reset import compute_delta, detect_reset, window_changed
from app.analytics.types import Observation
from app.analytics.utilization import utilization_metric, utilization_observations, utilization_value
from app.providers.anthropic import AnthropicAdapter
from app.providers.openai import OpenAIAdapter


def _snap(checked_at, metrics):
    return {"checked_at": checked_at, "metrics": metrics}


def _metric(label, value, unit=None):
    return {"label": label, "value": value, "unit": unit}


def _obs(metric, value, observed_at, kind="delta", unit=None):
    return Observation(metric=metric, value=value, unit=unit, observed_at=observed_at, kind=kind, source="snapshot")


# --- reset detection -------------------------------------------------------

def test_detect_reset_decreasing_jump_up_is_reset():
    assert detect_reset(5.0, 98.0, direction="decreasing") is True


def test_detect_reset_decreasing_normal_drain_is_not_reset():
    assert detect_reset(80.0, 71.0, direction="decreasing") is False


def test_detect_reset_increasing_counter_wrap_is_reset():
    assert detect_reset(140.0, 20.0, direction="increasing") is True


def test_compute_delta_decreasing_consumption():
    assert compute_delta(80.0, 71.0, direction="decreasing") == 9.0


def test_compute_delta_reset_returns_none():
    assert compute_delta(5.0, 98.0, direction="decreasing") is None


def test_compute_delta_increasing():
    assert compute_delta(100.0, 140.0, direction="increasing") == 40.0


def test_window_changed_requires_distinct_known_timestamps():
    t1 = datetime(2026, 8, 21, 12, tzinfo=UTC)
    t2 = datetime(2026, 8, 22, 12, tzinfo=UTC)
    assert window_changed(t1, t2) is True
    assert window_changed(t1, t1) is False
    assert window_changed(None, t2) is False


# --- normalization: remaining delta + reset --------------------------------

CODECX_CAPS = analytics_spec(
    supported=True,
    metrics={"session_remaining_percent": metric_spec(type_="remaining", unit="%", direction="decreasing", maximum=100, reset_metric="session_reset_at")},
)


def test_remaining_percent_delta_and_reset_detection():
    base = datetime(2026, 8, 21, 14, tzinfo=UTC)
    snapshots = [
        _snap(base, [_metric("session_remaining_percent", 80, "%")]),
        _snap(base + timedelta(hours=1), [_metric("session_remaining_percent", 71, "%")]),
        _snap(base + timedelta(hours=2), [_metric("session_remaining_percent", 5, "%")]),
        _snap(base + timedelta(hours=3), [_metric("session_remaining_percent", 98, "%")]),
    ]
    observations = normalize_snapshots(snapshots, capabilities=CODECX_CAPS)
    points = [o for o in observations if o.kind == "point"]
    deltas = [o for o in observations if o.kind == "delta"]
    assert len(points) == 4
    # deltas: 80->71 = 9, 71->5 = 66; 5->98 is a reset -> no delta
    assert [d.value for d in deltas] == [9.0, 66.0]


def test_known_reset_timestamp_prevents_cross_window_delta():
    base = datetime(2026, 8, 21, 14, tzinfo=UTC)
    snapshots = [
        _snap(base, [_metric("session_remaining_percent", 80, "%"), {"label": "session_reset_at", "value": "2026-08-21T18:00:00Z"}]),
        _snap(base + timedelta(hours=1), [_metric("session_remaining_percent", 71, "%"), {"label": "session_reset_at", "value": "2026-08-22T18:00:00Z"}]),
    ]
    observations = normalize_snapshots(snapshots, capabilities=CODECX_CAPS)
    deltas = [o for o in observations if o.kind == "delta"]
    # reset timestamp advanced -> no delta across the reset boundary
    assert deltas == []


def test_rolling_total_is_never_a_counter():
    caps = analytics_spec(
        supported=True,
        metrics={"cost_30d": metric_spec(type_="rolling_total", unit="USD", direction="increasing", deltas=False)},
    )
    base = datetime(2026, 8, 21, 14, tzinfo=UTC)
    snapshots = [
        _snap(base, [_metric("cost_30d", 10.0, "USD")]),
        _snap(base + timedelta(days=1), [_metric("cost_30d", 9.0, "USD")]),
    ]
    observations = normalize_snapshots(snapshots, capabilities=caps)
    assert all(o.kind == "point" for o in observations)
    assert [o.value for o in observations] == [10.0, 9.0]


def test_undeclared_metric_falls_back_to_generic_gauge_point():
    base = datetime(2026, 8, 21, 14, tzinfo=UTC)
    snapshots = [_snap(base, [_metric("custom_thing", 42)])]
    observations = normalize_snapshots(snapshots, capabilities={})
    assert len(observations) == 1
    assert observations[0].kind == "point"


# --- aggregation -----------------------------------------------------------

def test_counter_aggregation_sums_deltas():
    base = datetime(2026, 8, 21, 14, tzinfo=UTC)
    caps = analytics_spec(metrics={"tokens": metric_spec(type_="counter", unit="tokens", direction="increasing")})
    snapshots = [
        _snap(base, [_metric("tokens", 100)]),
        _snap(base + timedelta(hours=1), [_metric("tokens", 140)]),
        _snap(base + timedelta(hours=2), [_metric("tokens", 200)]),
    ]
    observations = normalize_snapshots(snapshots, capabilities=caps)
    deltas = [o for o in observations if o.kind == "delta"]
    assert [d.value for d in deltas] == [40.0, 60.0]

    buckets = bucketize(observations, metric="tokens", interval="day", tz="UTC")
    assert len(buckets) == 1
    assert buckets[0].total == 100.0


def test_hourly_aggregation_splits_buckets():
    base = datetime(2026, 8, 21, 14, 30, tzinfo=UTC)
    observations = [
        _obs("tokens", 10.0, base),
        _obs("tokens", 20.0, base + timedelta(minutes=20)),
        _obs("tokens", 30.0, base + timedelta(hours=1)),
    ]
    buckets = bucketize(observations, metric="tokens", interval="hour", tz="UTC")
    assert len(buckets) == 2
    assert buckets[0].total == 30.0
    assert buckets[1].total == 30.0


def test_timezone_day_boundary_grouping():
    # 02:00 UTC on Aug 21 == 22:00 EDT on Aug 20 (UTC-4 in August).
    observed = datetime(2026, 8, 21, 2, 0, tzinfo=UTC)
    observations = [_obs("tokens", 5.0, observed)]
    utc_bucket = bucketize(observations, metric="tokens", interval="day", tz="UTC")[0]
    ny_bucket = bucketize(observations, metric="tokens", interval="day", tz="America/New_York")[0]
    assert utc_bucket.start.date().isoformat() == "2026-08-21"
    assert ny_bucket.start.date().isoformat() == "2026-08-20"


def test_series_coverage_detects_gaps():
    base = datetime(2026, 8, 21, 0, 0, tzinfo=UTC)
    observations = []
    # Hourly samples with a 5-hour outage in the middle.
    for hour in list(range(0, 10)) + list(range(15, 25)):
        observations.append(_obs("tokens", 1.0, base + timedelta(hours=hour)))
    cov = series_coverage(observations)
    assert cov["actual"] == len(observations)
    assert cov["coverage"] < 1.0
    assert cov["median_gap_seconds"] == 3600.0


# --- forecasting -----------------------------------------------------------

def test_rates_from_deltas_daily_average():
    base = datetime(2026, 8, 21, 0, 0, tzinfo=UTC)
    observations = []
    for day in range(10):
        observations.append(_obs("tokens", 20.0, base + timedelta(days=day)))
    rates = rates_from_deltas(observations, now=base + timedelta(days=10))
    assert rates["avg_7d"] == pytest.approx(20.0)


def test_forecast_remaining_projects_at_reset():
    base = datetime(2026, 8, 21, 0, 0, tzinfo=UTC)
    reset = base + timedelta(days=7)
    # 14% used so far (deltas), 2%/day rate -> at 50% of the week projected ~14 + 2*3.5 = 21%.
    observations = []
    for day in range(4):
        observations.append(_obs("pct", 2.0, base + timedelta(days=day)))
    now = base + timedelta(days=3, hours=12)
    result = forecast_for_metric(
        observations,
        metric_type="remaining",
        now=now,
        reset_at=reset,
        window_start=base,
        capacity=100,
    )
    assert result["projected_at_reset"] is not None
    assert result["time_through_window"] == pytest.approx(0.5, abs=0.01)
    assert result["remaining"] == pytest.approx(92.0)


def test_forecast_pace_ratio_under_pace():
    base = datetime(2026, 8, 21, 0, 0, tzinfo=UTC)
    reset = base + timedelta(days=7)
    now = base + timedelta(days=3, hours=12)
    # 8% used so far -> 92% remaining over 3.5 days -> sustainable ~26.29%/day.
    # Actual burn 20%/day -> pace_ratio ~0.76 (under pace).
    observations = []
    for day in range(4):
        observations.append(_obs("pct", 2.0, base + timedelta(days=day)))
    result = forecast_for_metric(
        observations, metric_type="remaining", now=now, reset_at=reset,
        window_start=base, capacity=100,
    )
    assert "pace_ratio" in result
    assert result["pacing"]["status"] in {"under", "on_pace", "over"}
    # 2%/day actual vs ~26.29%/day sustainable -> well under 1.0
    assert result["pace_ratio"] < 1.0


def test_forecast_pace_ratio_burning_hot_is_over():
    base = datetime(2026, 8, 21, 0, 0, tzinfo=UTC)
    reset = base + timedelta(days=7)
    now = base + timedelta(days=3, hours=12)
    # 60% used so far -> 40% remaining over 3.5 days -> sustainable ~11.43%/day.
    # Actual burn 15%/day -> pace_ratio ~1.31 (over pace).
    observations = []
    for day in range(4):
        observations.append(_obs("pct", 15.0, base + timedelta(days=day)))
    result = forecast_for_metric(
        observations, metric_type="remaining", now=now, reset_at=reset,
        window_start=base, capacity=100,
    )
    assert result["pace_ratio"] > 1.0
    assert result["pacing"]["status"] == "over"


def test_forecast_balance_estimates_remaining_days():
    base = datetime(2026, 8, 21, 0, 0, tzinfo=UTC)
    observations = [
        Observation(metric="balance", value=10.0, unit="USD", observed_at=base, kind="point", source="snapshot"),
    ]
    for day in range(1, 4):
        observations.append(_obs("balance", 2.0, base + timedelta(days=day)))
    result = forecast_for_metric(observations, metric_type="balance", now=base + timedelta(days=4))
    assert result["estimated_remaining_days"] == pytest.approx(5.0, abs=0.01)


def test_forecast_counter_projects_total_window_end():
    base = datetime(2026, 8, 1, 0, 0, tzinfo=UTC)
    reset = base + timedelta(days=30)
    now = base + timedelta(days=15)
    observations = [_obs("credits", 10.0, base + timedelta(days=day)) for day in range(15)]
    result = forecast_for_metric(
        observations, metric_type="counter", now=now, reset_at=reset, window_start=base,
    )
    assert result["spent_this_window"] == 150.0
    assert result["projected_additional_usage"] == pytest.approx(150.0)
    # projected_window_end must be the *total* at reset, not just the future usage.
    assert result["projected_window_end"] == pytest.approx(300.0)


def test_sustainable_pacing():
    pacing = sustainable_pacing(remaining=48.0, days_remaining=4.3, actual_per_day=16.4)
    assert pacing["safe_per_day"] == pytest.approx(11.16, abs=0.02)
    assert pacing["difference_pct"] == pytest.approx(46.9, abs=0.5)


# --- confidence ------------------------------------------------------------

def test_confidence_low_with_few_observations():
    base = datetime(2026, 8, 21, 0, 0, tzinfo=UTC)
    observations = [_obs("tokens", 1.0, base), _obs("tokens", 1.0, base + timedelta(hours=1))]
    # Inject a fixed "now" so the short-history result is deterministic regardless
    # of the wall-clock date the suite runs on.
    assert confidence_level(observations, now=base + timedelta(days=2))["level"] == "low"


def test_confidence_high_with_rich_native_history():
    base = datetime.now(UTC) - timedelta(days=20)
    observations = []
    for hour in range(24 * 20):
        observations.append(
            Observation(metric="tokens", value=5.0, unit="tokens", observed_at=base + timedelta(hours=hour), kind="delta", source="native")
        )
    level = confidence_level(observations, coverage=0.95)
    assert level["level"] == "high"


# --- native history normalization -----------------------------------------

def test_anthropic_native_observations_flat_records():
    raw = {
        "data": [
            {"start_time": "2026-08-21T14:00:00Z", "end_time": "2026-08-21T15:00:00Z", "input_tokens": 10, "output_tokens": 20, "num_requests": 3},
            {"start_time": "2026-08-21T15:00:00Z", "end_time": "2026-08-21T16:00:00Z", "input_tokens": 15, "output_tokens": 5, "num_requests": 1},
        ]
    }
    observations = AnthropicAdapter.native_observations(raw)
    input_obs = [o for o in observations if o["metric"] == "input_tokens"]
    assert len(input_obs) == 2
    assert input_obs[0]["kind"] == "delta"
    assert input_obs[0]["window_start"].hour == 14


def test_openai_native_observations_daily_buckets():
    base = datetime(2026, 8, 1, 0, 0, tzinfo=UTC)
    raw = {
        "data": [
            {
                "start_time": int(base.timestamp()),
                "end_time": int((base + timedelta(days=1)).timestamp()),
                "results": [{"amount": {"value": 1.5, "currency": "usd"}}, {"amount": {"value": 0.5, "currency": "usd"}}],
            }
        ]
    }
    observations = OpenAIAdapter.native_observations(raw)
    assert len(observations) == 1
    assert observations[0]["metric"] == "daily_cost"
    assert observations[0]["value"] == 2.0
    assert observations[0]["unit"] == "USD"


def test_normalize_native_wraps_into_observations():
    base = datetime(2026, 8, 21, 14, 0, tzinfo=UTC)
    native = [{"metric": "tokens", "value": 7.0, "unit": "tokens", "observed_at": base, "kind": "delta"}]
    observations = normalize_native(native)
    assert len(observations) == 1
    assert observations[0].source == "native"
    assert observations[0].value == 7.0


# --- utilization -----------------------------------------------------------

def test_utilization_value_counter_percent():
    assert utilization_value(40.0, spec={"type": "counter", "maximum": 100}) == 40.0


def test_utilization_value_remaining_inverts_to_consumed():
    assert utilization_value(54.0, spec={"type": "remaining", "maximum": 100}) == 46.0


def test_utilization_value_remaining_uses_capacity_metric():
    assert utilization_value(80.0, spec={"type": "remaining", "capacity_metric": "limit"}, capacity=100) == 20.0


def test_utilization_value_returns_none_without_quota():
    assert utilization_value(5.0, spec={"type": "gauge"}) is None
    assert utilization_value(5.0, spec={"type": "counter"}) is None  # no maximum


def test_utilization_value_floors_zero_but_preserves_overage():
    assert utilization_value(150.0, spec={"type": "counter", "maximum": 100}) == 150.0
    assert utilization_value(-10.0, spec={"type": "remaining", "maximum": 100}) == pytest.approx(110.0)
    assert utilization_value(120.0, spec={"type": "remaining", "maximum": 100}) == 0.0


def test_utilization_metric_prefers_marked_metric():
    caps = analytics_spec(
        metrics={
            "a": metric_spec(type_="remaining", unit="%", maximum=100),
            "b": metric_spec(type_="counter", unit="%", maximum=100, utilization=True),
        }
    )
    label, _ = utilization_metric(caps)
    assert label == "b"


def test_utilization_capacity_joined_at_or_before():
    base = datetime(2026, 8, 21, 14, 0, tzinfo=UTC)
    spec = {"type": "remaining", "capacity_metric": "limit"}
    point_obs = [
        Observation(metric="limit_remaining", value=80.0, unit="credits", observed_at=base + timedelta(seconds=2), kind="point", source="snapshot"),
    ]
    capacity_obs = [
        Observation(metric="limit", value=100.0, unit="credits", observed_at=base, kind="point", source="snapshot"),
    ]
    # Capacity persisted ~2s before the usage observation - must still pair.
    result = utilization_observations(point_obs, metric="limit_remaining", spec=spec, capacity_observations=capacity_obs)
    assert len(result) == 1
    assert result[0].value == 20.0


def test_utilization_ignores_capacity_from_after_observation():
    base = datetime(2026, 8, 21, 14, 0, tzinfo=UTC)
    spec = {"type": "remaining", "capacity_metric": "limit"}
    point_obs = [
        Observation(metric="limit_remaining", value=80.0, unit="credits", observed_at=base, kind="point", source="snapshot"),
    ]
    capacity_obs = [
        Observation(metric="limit", value=100.0, unit="credits", observed_at=base + timedelta(seconds=10), kind="point", source="snapshot"),
    ]
    result = utilization_observations(point_obs, metric="limit_remaining", spec=spec, capacity_observations=capacity_obs)
    assert result == []
