"""Metric capability semantics for provider analytics.

Providers declare how each of their metrics behaves so the analytics engine can
normalize, aggregate, and forecast without hard-coding provider names.
"""

from __future__ import annotations

METRIC_TYPES = ("counter", "gauge", "remaining", "balance", "rolling_total", "rate_limit")

# Types whose interval deltas are meaningful (usage consumed between two
# observations), as opposed to gauges/rolling totals where the point value is
# the signal and changes must not be treated as simple consumption.
DELTA_CAPABLE_TYPES = {"counter", "remaining", "balance", "rate_limit"}

AGGREGATIONS = ("hourly", "daily", "weekly")

# Metric types that report a *point-in-time* value rather than a cumulative
# usage counter. Aggregation keeps min/max/avg/last for these.
POINT_TYPES = {"gauge", "remaining", "balance", "rolling_total"}


def metric_spec(
    *,
    type_: str,
    unit: str | None = None,
    direction: str = "increasing",
    aggregations: list[str] | None = None,
    deltas: bool = True,
    maximum: float | int | None = None,
    reset_metric: str | None = None,
    window: str | None = None,
    capacity_metric: str | None = None,
    utilization: bool = False,
) -> dict:
    """Build a normalized per-metric capability spec with safe defaults."""
    if type_ not in METRIC_TYPES:
        raise ValueError(f"Unsupported analytics metric type: {type_}")
    spec: dict = {
        "type": type_,
        "unit": unit,
        "direction": direction,
        "aggregations": aggregations or ["hourly", "daily"],
        "deltas": deltas,
        "maximum": maximum,
        "reset_metric": reset_metric,
        "window": window,
        "capacity_metric": capacity_metric,
        "utilization": utilization,
    }
    return {key: value for key, value in spec.items() if value is not None and value is not False}


def analytics_spec(
    *,
    supported: bool = True,
    native_history: bool = False,
    metrics: dict[str, dict] | None = None,
) -> dict:
    """Build a provider-level analytics capability declaration."""
    return {
        "supported": supported,
        "native_history": native_history,
        "metrics": metrics or {},
    }


def is_delta_capable(metric_type: str) -> bool:
    return metric_type in DELTA_CAPABLE_TYPES


def is_point_type(metric_type: str) -> bool:
    return metric_type in POINT_TYPES
