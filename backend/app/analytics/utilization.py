"""Quota-utilization helpers.

Utilization is the fraction of a provider's own quota consumed. It is usually
0-100, but can legitimately exceed 100 when a provider is over its allowance.
This remains the one cross-provider axis that is comparable even when providers
report tokens, USD, credits, or percentages.
"""

from __future__ import annotations

from bisect import bisect_right

from app.analytics.types import Observation


def floor_zero(value: float) -> float:
    return max(0.0, value)


def utilization_metrics(capabilities: dict) -> list[tuple[str, dict]]:
    """Return every metric that can produce quota utilization, preserving windows."""
    metrics = (capabilities or {}).get("metrics") or {}
    explicit = [(label, spec) for label, spec in metrics.items() if spec.get("utilization")]
    if explicit:
        return explicit
    return [
        (label, spec)
        for label, spec in metrics.items()
        if spec.get("type") in ("remaining", "counter")
        and (spec.get("maximum") is not None or spec.get("capacity_metric"))
    ]


def utilization_metric(capabilities: dict) -> tuple[str, dict] | None:
    """Return the preferred metric for headline quota utilization."""
    metrics = utilization_metrics(capabilities)
    if not metrics:
        return None
    overview = next((entry for entry in metrics if entry[1].get("overview")), None)
    return overview or metrics[0]


def utilization_value(value: float | None, *, spec: dict, capacity: float | None = None) -> float | None:
    """Fraction of quota consumed, or None when no quota is known.

    Values above 100 are meaningful overage signals and must not be clamped;
    only negative utilization is floored to zero.
    """
    if value is None:
        return None
    metric_type = spec.get("type")
    maximum = spec.get("maximum")
    if spec.get("utilization") and spec.get("unit") == "%" and metric_type == "gauge":
        return floor_zero(value)
    if metric_type == "counter":
        if maximum is not None and maximum > 0:
            return floor_zero(value / maximum * 100)
        return None
    if metric_type in ("remaining", "balance"):
        denominator = capacity if capacity is not None else maximum
        if denominator is not None and denominator > 0:
            return floor_zero((denominator - value) / denominator * 100)
        return None
    return None


def utilization_observations(
    point_observations: list[Observation],
    *,
    metric: str,
    spec: dict,
    capacity_observations: list[Observation] | None = None,
) -> list[Observation]:
    """Convert point readings into 0-100 utilization observations.

    When ``spec`` declares a ``capacity_metric``, the capacity is joined using
    the latest capacity reading at-or-before each usage observation (not an
    exact timestamp match), so a capacity and usage metric persisted even
    milliseconds apart still pair correctly.
    """
    capacity_points: list[tuple] = []
    capacity_metric_name = spec.get("capacity_metric")
    if capacity_metric_name and capacity_observations:
        capacity_points = sorted(
            (
                (obs.observed_at, obs.value)
                for obs in capacity_observations
                if obs.metric == capacity_metric_name and obs.kind == "point"
            ),
            key=lambda item: item[0],
        )
    capacity_times = [item[0] for item in capacity_points]

    def capacity_at(target) -> float | None:
        if not capacity_times:
            return None
        index = bisect_right(capacity_times, target) - 1
        return capacity_points[index][1] if index >= 0 else None

    result: list[Observation] = []
    for obs in point_observations:
        if obs.kind != "point" or obs.metric != metric:
            continue
        capacity = capacity_at(obs.observed_at)
        util = utilization_value(obs.value, spec=spec, capacity=capacity)
        if util is not None:
            result.append(
                Observation(
                    metric=metric,
                    value=util,
                    unit="%",
                    observed_at=obs.observed_at,
                    kind="point",
                    source=obs.source,
                    window_start=obs.window_start,
                    window_end=obs.window_end,
                    reset_at=obs.reset_at,
                )
            )
    return result
