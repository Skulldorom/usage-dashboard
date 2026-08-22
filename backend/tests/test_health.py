"""Unit tests for provider health derivation (app.health)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.health import default_max_stale_age, derive_health, is_success

NOW = datetime(2026, 8, 22, 12, 0, 0, tzinfo=UTC)
STALE = timedelta(hours=4)


def _health(**overrides):
    base = dict(
        latest_status="healthy",
        last_attempt_at=NOW - timedelta(minutes=2),
        last_success_at=NOW - timedelta(minutes=2),
        last_failure_at=None,
        consecutive_failures=0,
        latest_error=None,
        now=NOW,
        max_stale_age=STALE,
    )
    base.update(overrides)
    return derive_health(**base)


def test_healthy_single_snapshot():
    health = _health()
    assert health["status"] == "healthy"
    assert health["last_success_at"] == NOW - timedelta(minutes=2)
    assert health["consecutive_failures"] == 0
    assert health["is_stale"] is False
    assert health["age_seconds"] == pytest.approx(120)


def test_stale_latest_failed_recent_success():
    health = _health(
        latest_status="error",
        last_attempt_at=NOW - timedelta(minutes=5),
        last_success_at=NOW - timedelta(hours=2),
        last_failure_at=NOW - timedelta(minutes=5),
        consecutive_failures=1,
        latest_error="timeout",
    )
    assert health["status"] == "stale"
    assert health["is_stale"] is True
    assert health["last_success_at"] == NOW - timedelta(hours=2)
    assert health["last_failure_at"] == NOW - timedelta(minutes=5)
    assert health["consecutive_failures"] == 1
    assert health["latest_error"] == "timeout"


def test_error_when_last_success_too_old():
    health = _health(
        latest_status="error",
        last_attempt_at=NOW - timedelta(minutes=5),
        last_success_at=NOW - timedelta(hours=10),
        last_failure_at=NOW - timedelta(minutes=5),
        consecutive_failures=2,
        latest_error="down",
    )
    assert health["status"] == "error"
    assert health["is_stale"] is False


def test_error_when_no_success_ever():
    health = _health(
        latest_status="error",
        last_attempt_at=NOW - timedelta(minutes=5),
        last_success_at=None,
        last_failure_at=NOW - timedelta(minutes=5),
        consecutive_failures=3,
        latest_error="e3",
    )
    assert health["status"] == "error"
    assert health["last_success_at"] is None
    assert health["consecutive_failures"] == 3
    assert health["latest_error"] == "e3"


def test_never_connected_empty_history():
    health = _health(latest_status=None, last_attempt_at=None, last_success_at=None)
    assert health["status"] == "never_connected"
    assert health["last_attempt_at"] is None
    assert health["consecutive_failures"] == 0


def test_degraded_counts_as_success():
    health = _health(latest_status="degraded")
    assert health["status"] == "healthy"
    assert health["consecutive_failures"] == 0


def test_healthy_after_recovery():
    health = _health(
        latest_status="healthy",
        last_attempt_at=NOW - timedelta(minutes=5),
        last_success_at=NOW - timedelta(minutes=5),
        last_failure_at=NOW - timedelta(hours=2),
        consecutive_failures=0,
    )
    assert health["status"] == "healthy"


def test_consecutive_failures_pass_through():
    health = _health(
        latest_status="error",
        last_success_at=NOW - timedelta(hours=3),
        consecutive_failures=2,
    )
    assert health["consecutive_failures"] == 2
    assert health["status"] == "stale"


def test_naive_datetimes_treated_as_utc():
    naive = datetime(2026, 8, 22, 12, 0, 0)
    health = derive_health(
        latest_status="healthy",
        last_attempt_at=naive,
        last_success_at=naive,
        last_failure_at=None,
        now=NOW,
        max_stale_age=STALE,
    )
    assert health["status"] == "healthy"
    assert health["age_seconds"] == pytest.approx(0)


def test_default_max_stale_age_derives_from_interval():
    assert default_max_stale_age(60) == timedelta(minutes=120)
    assert default_max_stale_age(15) == timedelta(minutes=30)
    # A zero/negative interval still yields a sane floor.
    assert default_max_stale_age(0) == timedelta(minutes=2)


def test_is_success():
    assert is_success("healthy") is True
    assert is_success("degraded") is True
    assert is_success("error") is False
    assert is_success(None) is False
