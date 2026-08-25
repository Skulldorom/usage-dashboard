"""Unit tests for quota-impact correlation (app.analytics.quota_correlation)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.analytics.quota_correlation import (
    CORRELATION_FLOOR,
    MIN_WINDOWS,
    correlate_quota_impact,
    estimate_quota_impact,
    pearson,
    slope,
)
from app.analytics.types import Observation


def _util(value, observed_at, reset_at):
    return Observation(
        metric="weekly_remaining_percent",
        value=value,
        unit="%",
        observed_at=observed_at,
        kind="point",
        source="snapshot",
        reset_at=reset_at,
    )


def _hermes_tokens(value, observed_at, model="claude-sonnet-4"):
    return Observation(
        metric="input_tokens",
        value=value,
        unit="tokens",
        observed_at=observed_at,
        kind="delta",
        source="hermes",
        model=model,
    )


# ---------------------------------------------------------------------------
# pearson / slope
# ---------------------------------------------------------------------------


def test_pearson_perfect_positive():
    assert pearson([1.0, 2.0, 3.0, 4.0], [2.0, 4.0, 6.0, 8.0]) == 1.0


def test_pearson_zero_variance_is_none():
    assert pearson([1.0, 1.0, 1.0], [2.0, 3.0, 4.0]) is None
    assert pearson([1.0, 2.0], [1.0, 2.0, 3.0]) is None


def test_slope_linear():
    # y = 2x + 1
    assert slope([1.0, 2.0, 3.0], [3.0, 5.0, 7.0]) == 2.0


# ---------------------------------------------------------------------------
# correlate_quota_impact
# ---------------------------------------------------------------------------


def test_below_threshold_returns_none():
    assert correlate_quota_impact([10.0, 20.0], [100.0, 200.0]) is None


def test_misaligned_lengths_return_none():
    assert correlate_quota_impact([10.0, 20.0, 30.0], [100.0, 200.0]) is None


def test_strong_correlation_high_confidence():
    # Quota consumed is a clean linear function of Hermes tokens.
    tokens = [1000.0, 2000.0, 3000.0, 4000.0, 5000.0]
    quota = [t * 0.01 for t in tokens]  # 10, 20, 30, 40, 50
    result = correlate_quota_impact(quota, tokens)
    assert result is not None
    assert result["sample_size"] == 5
    assert result["confidence"] == "high"
    assert result["explained"] is True
    assert result["r_squared"] == 1.0
    assert result["unattributed_pct"] == 0.0
    assert result["estimated_impact_per_token"] == 0.01


def test_weak_correlation_low_confidence_unexplained():
    # Quota movement is basically unrelated to Hermes tokens.
    tokens = [100.0, 200.0, 300.0, 400.0, 500.0]
    quota = [30.0, 12.0, 45.0, 8.0, 50.0]
    result = correlate_quota_impact(quota, tokens)
    assert result is not None
    assert result["explained"] is False
    assert result["confidence"] == "low"
    assert result["unattributed_pct"] > 50.0
    assert result["r_squared"] < CORRELATION_FLOOR


def test_zero_hermes_variance_returns_none():
    result = correlate_quota_impact([10.0, 20.0, 30.0], [100.0, 100.0, 100.0])
    assert result is None


# ---------------------------------------------------------------------------
# estimate_quota_impact (window grouping)
# ---------------------------------------------------------------------------


def _windows(base, count):
    """Build `count` complete weekly windows of utilization + Hermes tokens.

    Each window's consumed % rises to a peak proportional to its Hermes token
    volume, so the correlation is meaningful (not constant across windows).
    """
    util = []
    hermes = []
    for window in range(count):
        reset = base + timedelta(days=7 * (window + 1))
        peak = 10.0 * (window + 1)  # 10, 20, 30, ...
        util.append(_util(peak * 0.2, base + timedelta(days=7 * window), reset))
        util.append(_util(peak * 0.6, base + timedelta(days=7 * window + 2), reset))
        util.append(_util(peak, base + timedelta(days=7 * window + 5), reset))
        hermes.append(_hermes_tokens(1000.0 * (window + 1), base + timedelta(days=7 * window + 3)))
    return util, hermes


def test_estimate_groups_windows_and_correlates():
    base = datetime(2026, 1, 1, tzinfo=UTC)
    util, hermes = _windows(base, 5)
    # 5 windows -> 4 complete (the latest reset window is in-progress, excluded).
    result = estimate_quota_impact(util, hermes)
    assert result is not None
    assert result["sample_size"] == 4


def test_estimate_peak_quota_consumed_per_window():
    base = datetime(2026, 1, 1, tzinfo=UTC)
    util, hermes = _windows(base, 4)
    # 4 windows -> 3 complete, exactly MIN_WINDOWS, eligible.
    result = estimate_quota_impact(util, hermes)
    assert result is not None
    assert result["sample_size"] == 3
    assert result["explained"] is True  # clean linear peak-vs-tokens relationship


def test_estimate_returns_none_with_insufficient_windows():
    base = datetime(2026, 1, 1, tzinfo=UTC)
    util, hermes = _windows(base, 2)
    assert estimate_quota_impact(util, hermes) is None


def test_estimate_returns_none_without_reset_timestamps():
    base = datetime(2026, 1, 1, tzinfo=UTC)
    util = [_util(50.0, base + timedelta(days=i), None) for i in range(5)]
    hermes = [_hermes_tokens(100.0, base + timedelta(days=i)) for i in range(5)]
    assert estimate_quota_impact(util, hermes) is None


def test_estimate_ignores_non_token_hermes_deltas():
    base = datetime(2026, 1, 1, tzinfo=UTC)
    util, hermes = _windows(base, 4)
    # Requests are not token metrics and must not inflate activity.
    requests = Observation(
        metric="requests", value=999999.0, unit="count",
        observed_at=base + timedelta(days=3), kind="delta", source="hermes",
    )
    hermes.append(requests)
    result = estimate_quota_impact(util, hermes)
    assert result is not None
    # Token-only correlation is preserved regardless of the request noise.
    assert result["sample_size"] == 3
    assert result["explained"] is True
