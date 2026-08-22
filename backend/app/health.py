"""Provider health derivation from snapshot history.

Health is derived from ``UsageSnapshot`` rows rather than a dedicated table:
every poll already persists a snapshot — success (``status != "error"``) or
failure (``status == "error"``) — so last-attempt/last-success/last-failure and
consecutive-failure counts are all recoverable without new storage.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

HEALTHY = "healthy"
STALE = "stale"
ERROR = "error"
NEVER_CONNECTED = "never_connected"

HEALTH_STATES = (HEALTHY, STALE, ERROR, NEVER_CONNECTED)

# Any snapshot whose status is not "error" represents a successful collection.
# Provider adapters emit "healthy" or "degraded" on success.
_SUCCESS_STATUSES = frozenset({"healthy", "degraded"})


def is_success(status: str | None) -> bool:
    """Whether a snapshot status represents a successful collection."""
    return status in _SUCCESS_STATUSES


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def default_max_stale_age(interval_minutes: int) -> timedelta:
    """Staleness threshold derived from the polling interval, not a hardcoded
    constant. A provider expected to refresh every ``interval_minutes`` becomes
    stale after missing roughly two expected refreshes."""
    minutes = max(interval_minutes, 1)
    return timedelta(minutes=minutes * 2)


def derive_health(
    snapshots: list[dict],
    *,
    now: datetime | None = None,
    max_stale_age: timedelta | None = None,
) -> dict:
    """Derive a provider health record from its snapshot history.

    ``snapshots`` items are dicts with ``checked_at`` (datetime), ``status``
    (str) and ``error`` (str | None). Order does not matter; the list is sorted
    internally. Naive datetimes are treated as UTC (SQLite returns naive
    timestamps).

    Returns a dict with keys: ``status``, ``last_attempt_at``,
    ``last_success_at``, ``last_failure_at``, ``consecutive_failures``,
    ``latest_error``, ``age_seconds``, ``is_stale``.
    """
    current = _as_utc(now) or datetime.now(UTC)
    if max_stale_age is None:
        max_stale_age = default_max_stale_age(60)

    def key(snap: dict) -> datetime:
        return _as_utc(snap["checked_at"]) or datetime.min.replace(tzinfo=UTC)

    ordered = sorted(snapshots, key=key, reverse=True)

    if not ordered:
        return {
            "status": NEVER_CONNECTED,
            "last_attempt_at": None,
            "last_success_at": None,
            "last_failure_at": None,
            "consecutive_failures": 0,
            "latest_error": None,
            "age_seconds": None,
            "is_stale": False,
        }

    latest = ordered[0]
    last_attempt_at = key(latest)

    successes = [snap for snap in ordered if is_success(snap.get("status"))]
    failures = [snap for snap in ordered if not is_success(snap.get("status"))]

    last_success_at = key(successes[0]) if successes else None
    last_failure_at = key(failures[0]) if failures else None

    # Consecutive failures: count trailing error snapshots from newest back.
    consecutive_failures = 0
    for snap in ordered:
        if is_success(snap.get("status")):
            break
        consecutive_failures += 1

    latest_error = failures[0].get("error") if failures else None

    age_seconds: float | None = None
    if last_success_at is not None:
        age_seconds = (current - last_success_at).total_seconds()

    if last_success_at is None:
        # Attempts exist (ordered is non-empty) but none succeeded.
        status = ERROR
        is_stale = False
    elif is_success(latest.get("status")):
        status = HEALTHY
        is_stale = False
    else:
        # Latest attempt failed but a previous success exists. Decide stale vs
        # error by whether the last-known-good value is still within policy.
        if age_seconds is not None and age_seconds <= max_stale_age.total_seconds():
            status = STALE
            is_stale = True
        else:
            status = ERROR
            is_stale = False

    return {
        "status": status,
        "last_attempt_at": last_attempt_at,
        "last_success_at": last_success_at,
        "last_failure_at": last_failure_at,
        "consecutive_failures": consecutive_failures,
        "latest_error": latest_error,
        "age_seconds": age_seconds,
        "is_stale": is_stale,
    }
