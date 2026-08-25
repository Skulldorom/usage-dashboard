"""Source reconciliation: disagreement detection, staleness, confidence impact.

The Usage page treats provider-reported data as authoritative and Hermes /
snapshot telemetry as corroborating. This module encodes the remaining rules
from issue #165 §4:

- pick an authoritative source (priority: native > snapshot > hermes > estimated);
- treat other compatible observations as corroboration;
- detect *material* disagreements between the authoritative value and a
  corroborating source (never blindly sum the two);
- flag when a corroborating source is fresher than the authoritative source so
  stale primary data cannot silently win;
- expose a confidence impact so conflicting/uncorroborated data reduces
  confidence rather than presenting itself as high.

Everything here is pure and unit-testable; it does no I/O.
"""

from __future__ import annotations

from datetime import UTC, datetime

# Lower is more authoritative.
SOURCE_PRIORITY: dict[str, int] = {
    "native": 0,
    "snapshot": 1,
    "hermes": 2,
    "estimated": 3,
}

# Material-disagreement tolerances. Capacity is a percentage; a corroborating
# estimate more than this many percentage points from the authoritative value is
# a disagreement. Activity is a raw count, compared relatively.
CAPACITY_DISAGREEMENT_POINTS = 15.0
ACTIVITY_DISAGREEMENT_RELATIVE = 0.5  # 50% relative difference

# A corroborating source fresher than the authoritative source by more than this
# is considered "stale authoritative" (authoritative data may be lagging).
STALE_MARGIN_SECONDS = 6 * 3600.0  # 6 hours

LEVELS = ("high", "medium", "low")


def authoritative_source(sources: list[str] | None) -> str | None:
    """Return the highest-priority source from a list of source names."""
    present = [s for s in (sources or []) if s]
    if not present:
        return None
    return min(present, key=lambda s: SOURCE_PRIORITY.get(s, 9))


def detect_disagreements(
    authoritative_value: float | None,
    corroborating: list[dict],
    *,
    is_percent: bool = False,
    tolerance: float | None = None,
) -> list[dict]:
    """Find corroborating values that materially disagree with the authoritative one.

    ``corroborating`` is a list of ``{source, value}`` dicts. Returns a list of
    disagreement dicts ``{source, value, authoritative_value, delta, detail}``.
    Missing/non-numeric values never count as disagreements (they are simply
    absent corroboration, not conflict).
    """
    if authoritative_value is None:
        return []
    threshold = (
        tolerance
        if tolerance is not None
        else (CAPACITY_DISAGREEMENT_POINTS if is_percent else ACTIVITY_DISAGREEMENT_RELATIVE)
    )
    disagreements: list[dict] = []
    for item in corroborating or []:
        source = item.get("source")
        value = item.get("value")
        if not source or value is None:
            continue
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            continue
        if is_percent:
            delta = numeric - authoritative_value
            if abs(delta) > threshold:
                disagreements.append(
                    {
                        "source": source,
                        "value": round(numeric, 4),
                        "authoritative_value": round(authoritative_value, 4),
                        "delta": round(delta, 4),
                        "detail": (
                            f"{source} reports {round(numeric, 1)}% vs authoritative "
                            f"{round(authoritative_value, 1)}% ({round(delta, 1)} pts)"
                        ),
                    }
                )
        else:
            if authoritative_value == 0:
                continue
            relative = (numeric - authoritative_value) / authoritative_value
            if abs(relative) > threshold:
                disagreements.append(
                    {
                        "source": source,
                        "value": round(numeric, 4),
                        "authoritative_value": round(authoritative_value, 4),
                        "delta": round(numeric - authoritative_value, 4),
                        "detail": (
                            f"{source} reports {round(numeric, 4)} vs authoritative "
                            f"{round(authoritative_value, 4)} ({relative:+.0%})"
                        ),
                    }
                )
    return disagreements


def _as_aware(value: datetime) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        # Naive datetimes are treated as UTC elsewhere in the analytics layer.
        return value.replace(tzinfo=UTC)
    return value


def stale_authoritative(
    authoritative_at: datetime | None,
    corroborating_times: list[datetime],
    *,
    margin_seconds: float = STALE_MARGIN_SECONDS,
) -> bool:
    """True when a corroborating source is fresher than the authoritative one.

    A corroborating observation newer than the authoritative reading by more
    than ``margin_seconds`` suggests the authoritative data is lagging and must
    not silently win on priority alone.
    """
    if authoritative_at is None:
        return False
    auth = _as_aware(authoritative_at)
    if auth is None:
        return False
    for observed in corroborating_times or []:
        corr = _as_aware(observed)
        if corr is None:
            continue
        if (corr - auth).total_seconds() > margin_seconds:
            return True
    return False


def reconcile(
    *,
    authoritative_source_name: str | None,
    authoritative_value: float | None,
    authoritative_at: datetime | None,
    corroborating: list[dict] | None = None,
    corroborating_sources: list[str] | None = None,
    corroborating_times: list[datetime] | None = None,
    is_percent: bool = False,
    tolerance: float | None = None,
) -> dict:
    """Combine disagreement + staleness detection into one reconciliation dict.

    Returns ``{authoritative_source, corroborating_sources, disagreements,
    has_disagreement, stale_authoritative, confidence_impact}`` where
    ``confidence_impact`` is a non-positive integer (0 = no impact, negative =
    demote confidence by that many steps).
    """
    corr = list(corroborating or [])
    disagreements = detect_disagreements(
        authoritative_value, corr, is_percent=is_percent, tolerance=tolerance
    )
    stale = stale_authoritative(authoritative_at, list(corroborating_times or []))
    impact = 0
    if disagreements:
        impact -= 1
    if stale:
        impact -= 1
    return {
        "authoritative_source": authoritative_source_name,
        "corroborating_sources": list(corroborating_sources or []),
        "disagreements": disagreements,
        "has_disagreement": bool(disagreements),
        "stale_authoritative": stale,
        "confidence_impact": impact,
    }


def degrade_confidence(level: str | None, steps: int) -> str:
    """Demote a confidence level by ``steps`` (clamped to ``low``)."""
    if steps >= 0:
        return level or "low"
    order = {name: index for index, name in enumerate(LEVELS)}
    current = order.get(level or "low", order["low"])
    demoted = min(current - steps, len(LEVELS) - 1)
    return LEVELS[demoted]
