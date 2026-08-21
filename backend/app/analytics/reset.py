"""Reset detection for quota/rate-limit metrics.

A reset is the moment a provider's quota window rolls over (for example a
weekly limit). When a *decreasing* metric such as "remaining credits" or
"remaining percent" jumps up between two observations, that must be classified
as a new window rather than negative usage.
"""

from __future__ import annotations

from datetime import datetime

# A reset is declared when a decreasing metric increases by more than this
# relative tolerance, or an increasing metric decreases by more than it.
# Kept small so genuine quota rollovers are detected without mistaking normal
# noise for a reset.
RESET_TOLERANCE = 0.5


def detect_reset(
    prev_value: float,
    curr_value: float,
    *,
    direction: str,
    tolerance: float = RESET_TOLERANCE,
) -> bool:
    """Return True when ``curr_value`` indicates the window reset since ``prev_value``.

    - decreasing (remaining/balance): curr > prev + tolerance -> reset.
    - increasing (counter): curr < prev - tolerance -> reset (counter wrapped).
    """
    if direction == "decreasing":
        return curr_value > prev_value + tolerance
    if direction == "increasing":
        return curr_value < prev_value - tolerance
    return False


def compute_delta(
    prev_value: float,
    curr_value: float,
    *,
    direction: str,
    tolerance: float = RESET_TOLERANCE,
) -> float | None:
    """Return consumption over the interval ``[prev, curr]`` or None on a reset.

    For decreasing metrics consumption is ``prev - curr``; for increasing
    counters it is ``curr - prev``. Returns ``None`` when a reset is detected so
    callers never record negative usage.
    """
    if detect_reset(prev_value, curr_value, direction=direction, tolerance=tolerance):
        return None
    delta = (prev_value - curr_value) if direction == "decreasing" else (curr_value - prev_value)
    return max(delta, 0.0)


def window_changed(prev_reset_at: datetime | None, curr_reset_at: datetime | None) -> bool:
    """Return True when a known reset timestamp advanced to a new window."""
    if curr_reset_at is None:
        return False
    if prev_reset_at is None:
        return False
    return curr_reset_at != prev_reset_at
