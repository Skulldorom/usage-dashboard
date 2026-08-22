"""Provider health derivation from snapshot history.

Health is derived from targeted snapshot queries rather than a dedicated table
or a bounded scan window. Every poll already persists a snapshot — success
(``status != "error"``) or failure (``status == "error"``) — so last-success,
last-failure, and consecutive-failure counts are recovered with cheap aggregate
queries and no arbitrary history window.
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
    *,
    latest_status: str | None,
    last_attempt_at: datetime | None,
    last_success_at: datetime | None,
    last_failure_at: datetime | None,
    consecutive_failures: int = 0,
    latest_error: str | None = None,
    now: datetime | None = None,
    max_stale_age: timedelta | None = None,
) -> dict:
    """Derive a provider health record from its snapshot summary fields.

    The caller computes the inputs with targeted queries (latest snapshot,
    last success, last failure, and failure count) rather than a bounded scan,
    so a long run of failures can never hide an older successful snapshot.

    Naive datetimes are treated as UTC (SQLite returns naive timestamps).

    Returns a dict with keys: ``status``, ``last_attempt_at``,
    ``last_success_at``, ``last_failure_at``, ``consecutive_failures``,
    ``latest_error``, ``age_seconds``, ``is_stale``.
    """
    current = _as_utc(now) or datetime.now(UTC)
    if max_stale_age is None:
        max_stale_age = default_max_stale_age(60)

    last_attempt_at = _as_utc(last_attempt_at)
    last_success_at = _as_utc(last_success_at)
    last_failure_at = _as_utc(last_failure_at)

    age_seconds: float | None = None
    if last_success_at is not None:
        age_seconds = (current - last_success_at).total_seconds()

    if last_attempt_at is None:
        status = NEVER_CONNECTED
        is_stale = False
    elif last_success_at is None:
        status = ERROR
        is_stale = False
    elif is_success(latest_status):
        status = HEALTHY
        is_stale = False
    elif age_seconds is not None and age_seconds <= max_stale_age.total_seconds():
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
