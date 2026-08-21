"""Deterministic, rate-based forecasting for provider usage metrics.

No ML. Forecasts are scoped to the relevant reset window and never extrapolate
rolling totals as if they were simple counters.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.analytics.types import Observation

_SECONDS_PER_DAY = 86_400.0


def _as_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _window_delta_sum(observations: list[Observation], *, since: datetime, until: datetime) -> float:
    total = 0.0
    for obs in observations:
        if obs.kind != "delta":
            continue
        if obs.observed_at >= since and obs.observed_at < until:
            total += obs.value
    return total


def rates_from_deltas(observations: list[Observation], *, now: datetime | None = None) -> dict:
    """Consumption rates (per day) over 24h / 7d / 30d windows from delta observations.

    The per-day rate uses the actual span of the deltas in the window when at
    least two samples exist, so short histories report a realistic rate instead
    of undercounting against the full nominal window.
    """
    current = _as_aware(now or datetime.now(UTC))
    deltas = [obs for obs in observations if obs.kind == "delta"]

    def daily_rate(seconds: float) -> float | None:
        window = current - timedelta(seconds=seconds)
        in_window = [obs for obs in deltas if obs.observed_at >= window]
        if not in_window:
            return None
        total = sum(obs.value for obs in in_window)
        if len(in_window) >= 2:
            earliest = min(obs.observed_at for obs in in_window)
            span = max((current - earliest).total_seconds(), 1.0)
        else:
            span = seconds
        days = span / _SECONDS_PER_DAY
        return round(total / days, 6) if days > 0 else None

    return {
        "current_24h": daily_rate(_SECONDS_PER_DAY),
        "avg_7d": daily_rate(7 * _SECONDS_PER_DAY),
        "avg_30d": daily_rate(30 * _SECONDS_PER_DAY),
    }


def _fraction(value: float | None) -> float | None:
    return round(value, 4) if value is not None else None


def forecast_for_metric(
    observations: list[Observation],
    *,
    metric_type: str,
    now: datetime | None = None,
    reset_at: datetime | None = None,
    window_start: datetime | None = None,
    capacity: float | None = None,
) -> dict:
    """Produce a type-appropriate forecast for a single metric."""
    current = _as_aware(now or datetime.now(UTC))
    rates = rates_from_deltas(observations, now=current)
    avg_7d = rates["avg_7d"] or rates["avg_30d"] or rates["current_24h"]

    result: dict = {
        "metric_type": metric_type,
        "rates": rates,
    }

    # Point value for remaining/balance/gauge/rolling metrics.
    points = sorted(
        (obs for obs in observations if obs.kind == "point"),
        key=lambda obs: obs.observed_at,
    )
    latest_point = points[-1].value if points else None

    if metric_type in ("rate_limit", "remaining"):
        # Usage consumed within the current window, derived from deltas since
        # window start (falling back to all deltas when the window is unknown).
        start = _as_aware(window_start) if window_start else (current - timedelta(days=7))
        window_usage = _window_delta_sum(observations, since=start, until=current)
        result["window_usage"] = round(window_usage, 4)

        if capacity:
            result["window_capacity"] = capacity
            remaining = max(0.0, capacity - window_usage)
            result["remaining"] = round(remaining, 4)

        if reset_at:
            next_reset = _as_aware(reset_at)
            window_span = max((next_reset - start).total_seconds(), 1.0)
            elapsed = max((current - start).total_seconds(), 0.0)
            result["time_through_window"] = _fraction(min(1.0, elapsed / window_span))
            result["reset_at"] = next_reset.isoformat()

            if avg_7d and avg_7d > 0:
                time_left = max((next_reset - current).total_seconds(), 0.0)
                projected = window_usage + (avg_7d / _SECONDS_PER_DAY) * time_left
                result["projected_at_reset"] = round(projected, 4)
                if capacity:
                    result["projected_at_reset_pct"] = _fraction(min(1.0, projected / capacity))
                    if projected >= capacity:
                        # Solve time when cumulative usage reaches capacity.
                        excess = capacity - window_usage
                        seconds_to_limit = (excess / avg_7d) * _SECONDS_PER_DAY if avg_7d > 0 else None
                        result["exhaustion_in_seconds"] = round(seconds_to_limit) if seconds_to_limit is not None else None
                        result["exhaustion_at"] = (
                            (current + timedelta(seconds=seconds_to_limit)).isoformat()
                            if seconds_to_limit is not None
                            else None
                        )

            days_left = max((next_reset - current).total_seconds() / _SECONDS_PER_DAY, 0.0)
            if capacity and days_left > 0:
                remaining = max(0.0, capacity - window_usage)
                result["sustainable_per_day"] = round(remaining / days_left, 4)

    if metric_type == "balance":
        result["balance"] = latest_point
        if avg_7d and avg_7d > 0 and latest_point is not None:
            result["estimated_remaining_days"] = round(latest_point / avg_7d, 2)
            result["exhaustion_date"] = (current + timedelta(days=latest_point / avg_7d)).isoformat()

    if metric_type == "counter":
        if window_start and reset_at:
            result["spent_this_window"] = round(
                _window_delta_sum(observations, since=_as_aware(window_start), until=current), 4
            )
        if avg_7d and avg_7d > 0 and reset_at:
            time_left = max((_as_aware(reset_at) - current).total_seconds(), 0.0)
            projected = (avg_7d / _SECONDS_PER_DAY) * time_left
            result["projected_window_end"] = round(projected, 4)

    if metric_type == "rolling_total":
        result["value"] = latest_point

    return result


def sustainable_pacing(
    *,
    remaining: float | None,
    days_remaining: float | None,
    actual_per_day: float | None,
) -> dict | None:
    """Compare actual pace against a sustainable target pace."""
    if remaining is None or not days_remaining or days_remaining <= 0:
        return None
    target = remaining / days_remaining
    result: dict = {
        "remaining": round(remaining, 4),
        "days_remaining": round(days_remaining, 2),
        "safe_per_day": round(target, 4),
    }
    if actual_per_day is not None and target > 0:
        result["actual_per_day"] = round(actual_per_day, 4)
        result["difference_pct"] = round((actual_per_day - target) / target * 100, 1)
    return result
