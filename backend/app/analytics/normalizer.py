"""Snapshot and native-history normalization into analytics observations."""

from __future__ import annotations

from datetime import UTC, datetime

from app.analytics.capabilities import is_delta_capable
from app.analytics.reset import compute_delta, window_changed
from app.analytics.types import Observation

# Metric types whose point value is the signal; their interval deltas are not
# meaningful and are never computed even when the spec requests deltas.
_NEVER_DELTA_TYPES = {"gauge", "rolling_total"}


def _numeric(value) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _parse_datetime(value) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    return parsed


def parse_time(value) -> datetime | None:
    """Parse an observation timestamp from a datetime, ISO string, or epoch."""
    if isinstance(value, datetime):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            return datetime.fromtimestamp(float(value), tz=UTC)
        except (OverflowError, OSError, ValueError):
            return None
    return _parse_datetime(value)


def _reset_values(metric_map: dict[str, dict]) -> dict[str, datetime | None]:
    """Map each metric label carrying a reset timestamp to a parsed datetime."""
    return {
        label: _parse_datetime(metric.get("value"))
        for label, metric in metric_map.items()
        if _parse_datetime(metric.get("value")) is not None
    }


def normalize_snapshots(
    snapshots: list[dict],
    *,
    capabilities: dict | None = None,
) -> list[Observation]:
    """Derive observations from a chronological list of snapshots.

    ``snapshots`` items are dicts: ``{"checked_at": datetime, "metrics": [...]}``
    where each metric dict has ``label``/``value``/``unit``. ``capabilities`` is
    the provider analytics spec (``{"metrics": {label: spec}}``); undeclared
    numeric metrics fall back to a generic point gauge.
    """
    metrics_spec = (capabilities or {}).get("metrics") or {}
    observations: list[Observation] = []
    previous: dict[str, tuple[float, datetime | None, datetime]] = {}

    ordered = sorted(snapshots, key=lambda snap: snap["checked_at"])
    for snap in ordered:
        checked_at = snap["checked_at"]
        metric_map = {
            str(metric.get("label")): metric
            for metric in (snap.get("metrics") or [])
            if metric.get("label") is not None
        }
        resets = _reset_values(metric_map)

        for label, metric in metric_map.items():
            value = _numeric(metric.get("value"))
            if value is None:
                continue
            unit = metric.get("unit")
            spec = metrics_spec.get(label)
            metric_type = spec.get("type", "gauge") if spec else "gauge"
            direction = "increasing"
            if spec:
                direction = spec.get("direction") or (
                    "decreasing" if metric_type in ("remaining", "balance") else "increasing"
                )
            reset_at = resets.get(spec["reset_metric"]) if spec and spec.get("reset_metric") else None

            observations.append(
                Observation(
                    metric=label,
                    value=value,
                    unit=unit,
                    observed_at=checked_at,
                    kind="point",
                    source="snapshot",
                    reset_at=reset_at,
                )
            )

            delta_eligible = (
                spec
                and spec.get("deltas", True)
                and is_delta_capable(metric_type)
                and metric_type not in _NEVER_DELTA_TYPES
            )
            if delta_eligible:
                prev = previous.get(label)
                if prev is not None and not window_changed(prev[1], reset_at):
                    prev_value, _, prev_at = prev
                    delta = compute_delta(prev_value, value, direction=direction)
                    if delta is not None and delta > 0:
                        observations.append(
                            Observation(
                                metric=label,
                                value=delta,
                                unit=unit,
                                observed_at=checked_at,
                                kind="delta",
                                source="snapshot",
                                window_start=prev_at,
                                window_end=checked_at,
                                reset_at=reset_at,
                            )
                        )
                previous[label] = (value, reset_at, checked_at)

    return observations


def normalize_native(native: list[dict]) -> list[Observation]:
    """Wrap provider-native historical buckets into observations.

    ``native`` items are dicts produced by ``ProviderAdapter.native_observations``
    with keys ``metric``/``value``/``unit``/``observed_at``/``kind`` and optional
    ``window_start``/``window_end``/``reset_at``.
    """
    observations: list[Observation] = []
    for item in native or []:
        value = _numeric(item.get("value"))
        if value is None:
            continue
        observations.append(
            Observation(
                metric=str(item["metric"]),
                value=value,
                unit=item.get("unit"),
                observed_at=item["observed_at"],
                kind=item.get("kind") or "delta",
                source="native",
                window_start=item.get("window_start"),
                window_end=item.get("window_end"),
                reset_at=item.get("reset_at"),
            )
        )
    return observations
