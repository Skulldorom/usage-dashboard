"""Estimate how Hermes-observed activity correlates with quota movement.

The follow-up comment to issue #165 requires, but deliberately constrains, a
*historical quota-impact correlation*:

- correlate only observations in the same provider + reset window;
- never assume a fixed tokens -> quota conversion;
- require a minimum sample threshold before producing anything;
- expose sample size + confidence and label the result an **estimate**;
- degrade confidence when quota movement is not explained by Hermes activity;
- keep unattributed quota consumption visible (never force 100% attribution).

This module is pure and deterministic - it does no I/O. The correlation is a
least-squares slope of quota consumed vs Hermes token volume across complete
reset windows, reported alongside Pearson's r and r^2 so consumers can see how
well Hermes actually explains quota movement.
"""

from __future__ import annotations

from app.analytics.types import Observation

# Minimum number of *complete* reset windows required before an estimate is
# produced. Below this there is not enough correlated history to be meaningful.
MIN_WINDOWS = 3

# r^2 below this means Hermes activity does not meaningfully explain quota
# movement; confidence is degraded and ``explained`` is False.
CORRELATION_FLOOR = 0.3

# Token classes counted as "Hermes activity" for correlation purposes. Mirrors
# the Hermes token metrics in ``app.datasources.base``.
TOKEN_METRICS = frozenset(
    {"input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens", "reasoning_tokens"}
)


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def pearson(xs: list[float], ys: list[float]) -> float | None:
    """Pearson correlation coefficient of two equal-length numeric lists.

    Returns ``None`` when either list has zero variance (undefined).
    """
    if len(xs) != len(ys) or len(xs) < 2:
        return None
    mx = _mean(xs)
    my = _mean(ys)
    numerator = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = sum((x - mx) ** 2 for x in xs)
    dy = sum((y - my) ** 2 for y in ys)
    if dx <= 0 or dy <= 0:
        return None
    return numerator / ((dx * dy) ** 0.5)


def slope(xs: list[float], ys: list[float]) -> float | None:
    """Least-squares slope of ``ys`` vs ``xs`` (dy/dx), or None if undefined."""
    if len(xs) != len(ys) or len(xs) < 2:
        return None
    mx = _mean(xs)
    my = _mean(ys)
    denominator = sum((x - mx) ** 2 for x in xs)
    if denominator <= 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / denominator


def correlate_quota_impact(
    quota_consumed: list[float],
    hermes_activity: list[float],
) -> dict | None:
    """Correlate per-window quota consumption with per-window Hermes activity.

    ``quota_consumed[i]`` and ``hermes_activity[i]`` describe the same reset
    window. Returns ``None`` below the minimum sample threshold or on misaligned
    input (never a fabricated correlation from two points).
    """
    if len(quota_consumed) < MIN_WINDOWS or len(quota_consumed) != len(hermes_activity):
        return None
    r = pearson(hermes_activity, quota_consumed)
    m = slope(hermes_activity, quota_consumed)
    if r is None or m is None:
        return None

    r_squared = r * r
    explained = r_squared >= CORRELATION_FLOOR
    unattributed_pct = round(max(0.0, (1.0 - r_squared)) * 100.0, 1)

    if r_squared >= 0.7:
        confidence = "high"
    elif r_squared >= CORRELATION_FLOOR:
        confidence = "medium"
    else:
        confidence = "low"

    note = (
        "Hermes activity explains most observed quota movement"
        if explained
        else "Hermes activity does not explain observed quota movement"
    )

    return {
        "sample_size": len(quota_consumed),
        "correlation": round(r, 4),
        "r_squared": round(r_squared, 4),
        # Quota percentage points per Hermes token, over a complete window.
        "estimated_impact_per_token": round(m, 8),
        "unattributed_pct": unattributed_pct,
        "confidence": confidence,
        "explained": explained,
        "note": note,
    }


def estimate_quota_impact(
    util_points: list[Observation],
    hermes_deltas: list[Observation],
) -> dict | None:
    """Pair complete reset windows of utilization with Hermes activity and
    correlate them.

    ``util_points`` are utilization (%) point observations carrying a
    ``reset_at``. Windows are grouped by that reset timestamp; the most recent
    window is treated as in-progress and excluded. ``hermes_deltas`` are Hermes
    token deltas summed within each complete window.

    Returns ``None`` when fewer than :data:`MIN_WINDOWS` complete windows exist
    (not enough history to estimate impact).
    """
    windowed = [
        obs for obs in util_points
        if obs.kind == "point" and obs.reset_at is not None
    ]
    if len(windowed) < MIN_WINDOWS:
        return None

    # Group by reset timestamp (aware datetimes compare fine; use iso key to be
    # robust to tz-normalization differences).
    windows: dict[str, dict] = {}
    for obs in windowed:
        key = obs.reset_at.isoformat() if obs.reset_at else None
        entry = windows.setdefault(key, {"reset_at": obs.reset_at, "points": []})
        entry["points"].append(obs)

    # Sort windows by reset time, drop the most recent (in-progress) window.
    ordered = sorted(windows.values(), key=lambda w: w["reset_at"])
    complete = ordered[:-1]
    if len(complete) < MIN_WINDOWS:
        return None

    quota_consumed: list[float] = []
    hermes_activity: list[float] = []
    for index, window in enumerate(complete):
        points = sorted(window["points"], key=lambda p: p.observed_at)
        # Peak utilization observed within the window (a remaining % drains to a
        # minimum, so max utilization = quota consumed before reset).
        quota_consumed.append(max(p.value for p in points))
        window_start = points[0].observed_at
        window_end = window["reset_at"]
        # Hermes token deltas within the same reset window.
        activity = sum(
            obs.value for obs in hermes_deltas
            if obs.kind == "delta"
            and obs.metric in TOKEN_METRICS
            and window_start <= obs.observed_at < window_end
        )
        hermes_activity.append(activity)

    return correlate_quota_impact(quota_consumed, hermes_activity)
