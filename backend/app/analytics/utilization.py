"""Quota-utilization helpers.

Utilization is the fraction of a provider's own quota consumed (0-100), which
is the one cross-provider axis that is comparable even when providers report
tokens, USD, credits, or percentages.
"""

from __future__ import annotations

from bisect import bisect_right

from app.analytics.types import Observation


def clamp100(value: float) -> float:
    return max(0.0, min(100.0, value))


def utilization_metric(capabilities: dict) -> tuple[str, dict] | None:
    """Return the metric (label, spec) that best expresses quota utilization."""
    metrics = (capabilities or {}).get("metrics") or {}
    for label, spec in metrics.items():
        if spec.get("utilization"):
            return label, spec
    for label, spec in metrics.items():
        if spec.get("type") in ("remaining", "counter") and (
            spec.get("maximum") is not None or spec.get("capacity_metric")
        ):
            return label, spec
    return None


def utilization_value(value: float | None, *, spec: dict, capacity: float | None = None) -> float | None:
    """Fraction of quota consumed (0-100), or None when no quota is known."""
    if value is None:
        return None
    metric_type = spec.get("type")
    maximum = spec.get("maximum")
    if metric_type == "counter":
        if maximum is not None and maximum > 0:
            return clamp100(value / maximum * 100)
        return None
    if metric_type in ("remaining", "balance"):
        denominator = capacity if capacity is not None else maximum
        if denominator is not None and denominator > 0:
            return clamp100((denominator - value) / denominator * 100)
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
