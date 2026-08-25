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
    overview: bool = False,
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
        "overview": overview,
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


def overview_metric(capabilities: dict | None) -> tuple[str, dict] | None:
    """Return the explicitly declared headline metric (label, spec), if any.

    The headline is deterministic - declared via ``overview=True`` - rather than
    inferred from summed unit totals, so overlapping or derived metrics never
    inflate a provider's headline value.
    """
    metrics = (capabilities or {}).get("metrics") or {}
    for label, spec in metrics.items():
        if spec.get("overview"):
            return label, spec
    return None


# ---------------------------------------------------------------------------
# Canonical activity dimensions (issue #165 §7/§8).
# ---------------------------------------------------------------------------

# Activity metrics are *consumption* counters, not point-in-time state. Only
# delta-capable counter/rate_limit metrics map to an activity dimension;
# gauges/balances/remaining/rolling totals are state and must not be summed as
# "activity". A metric maps to a dimension via its unit.
ACTIVITY_DIMENSION_BY_UNIT: dict[str, str] = {
    "tokens": "tokens",
    "requests": "requests",
    "count": "requests",
    "usd": "cost",
    "credits": "credits",
}

# Delta-capable types that are consumption counters (not state).
_ACTIVITY_TYPES = {"counter", "rate_limit"}


def _dimension_for_unit(unit: str | None) -> str | None:
    if not unit:
        return None
    return ACTIVITY_DIMENSION_BY_UNIT.get(str(unit).strip().lower())


def activity_dimensions(capabilities: dict | None) -> dict[str, list[tuple[str, dict]]]:
    """Map a provider's metrics into canonical activity dimensions.

    Returns ``{dimension: [(metric_label, spec), ...]}`` where ``dimension`` is
    one of ``tokens`` / ``requests`` / ``cost`` / ``credits``.

    Rules:
    - Only delta-capable counter/rate_limit metrics are activity (state metrics
      like balance/remaining/rolling_total are excluded).
    - ``%`` metrics (utilization) stay in capacity mode and are excluded.
    - Metrics with a ``window`` are overlapping time windows (e.g. OpenRouter
      daily/weekly/monthly) and are *not* summed: the ``overview=True`` metric
      wins, else the longest window. Metrics without a ``window`` are disjoint
      classes (input/output/cache tokens) and are summed.
    """
    metrics = (capabilities or {}).get("metrics") or {}
    grouped: dict[str, list[tuple[str, dict]]] = {}
    for label, spec in metrics.items():
        metric_type = spec.get("type")
        if metric_type not in _ACTIVITY_TYPES:
            continue
        if spec.get("utilization"):
            continue
        dimension = _dimension_for_unit(spec.get("unit"))
        if dimension is None:
            continue
        grouped.setdefault(dimension, []).append((label, spec))

    result: dict[str, list[tuple[str, dict]]] = {}
    for dimension, entries in grouped.items():
        windowed = [entry for entry in entries if entry[1].get("window")]
        if windowed:
            overview_entry = next((entry for entry in entries if entry[1].get("overview")), None)
            if overview_entry is not None:
                result[dimension] = [overview_entry]
            else:
                # Overlapping windows with no declared overview metric: keep the
                # longest window to avoid double-counting.
                longest = max(windowed, key=lambda entry: _window_rank(entry[1].get("window")))
                result[dimension] = [longest]
        else:
            result[dimension] = entries
    return result


_WINDOW_RANKS = {"24h": 1, "session": 1, "7d": 2, "week": 2, "30d": 3, "billing": 3, "month": 3}


def _window_rank(window: str | None) -> int:
    return _WINDOW_RANKS.get(window or "", 0)


def activity_metric_labels(dimensions: dict[str, list[tuple[str, dict]]]) -> dict[str, list[str]]:
    """Flatten ``activity_dimensions`` output to ``{dimension: [metric_label]}``."""
    return {
        dimension: [label for label, _spec in entries]
        for dimension, entries in dimensions.items()
    }
