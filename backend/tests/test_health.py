"""Unit tests for provider health derivation (app.health)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.health import derive_health, default_max_stale_age


def _snap(checked_at, status="healthy", error=None):
    return {"checked_at": checked_at, "status": status, "error": error}


NOW = datetime(2026, 8, 22, 12, 0, 0, tzinfo=UTC)
STALE = timedelta(hours=4)


def test_healthy_single_snapshot():
    snap = _snap(NOW - timedelta(minutes=2))
    health = derive_health([snap], now=NOW, max_stale_age=STALE)
    assert health["status"] == "healthy"
    assert health["last_success_at"] == snap["checked_at"]
    assert health["consecutive_failures"] == 0
    assert health["is_stale"] is False
    assert health["age_seconds"] == pytest.approx(120)


def test_stale_latest_failed_recent_success():
    success = _snap(NOW - timedelta(hours=2))
    failure = _snap(NOW - timedelta(minutes=5), status="error", error="timeout")
    health = derive_health([failure, success], now=NOW, max_stale_age=STALE)
    assert health["status"] == "stale"
    assert health["is_stale"] is True
    assert health["last_success_at"] == success["checked_at"]
    assert health["last_failure_at"] == failure["checked_at"]
    assert health["consecutive_failures"] == 1
    assert health["latest_error"] == "timeout"


def test_error_when_last_success_too_old():
    success = _snap(NOW - timedelta(hours=10))
    failure = _snap(NOW - timedelta(minutes=5), status="error", error="down")
    health = derive_health([failure, success], now=NOW, max_stale_age=STALE)
    assert health["status"] == "error"
    assert health["is_stale"] is False


def test_error_when_no_success_ever():
    failures = [
        _snap(NOW - timedelta(minutes=40), status="error", error="e1"),
        _snap(NOW - timedelta(minutes=20), status="error", error="e2"),
        _snap(NOW - timedelta(minutes=5), status="error", error="e3"),
    ]
    health = derive_health(failures, now=NOW, max_stale_age=STALE)
    assert health["status"] == "error"
    assert health["last_success_at"] is None
    assert health["consecutive_failures"] == 3
    assert health["latest_error"] == "e3"


def test_never_connected_empty_history():
    health = derive_health([], now=NOW, max_stale_age=STALE)
    assert health["status"] == "never_connected"
    assert health["last_attempt_at"] is None
    assert health["consecutive_failures"] == 0


def test_degraded_counts_as_success():
    health = derive_health([_snap(NOW, status="degraded")], now=NOW, max_stale_age=STALE)
    assert health["status"] == "healthy"
    assert health["consecutive_failures"] == 0


def test_recovery_after_failures_resets_consecutive():
    snapshots = [
        _snap(NOW - timedelta(hours=3), status="error", error="x"),
        _snap(NOW - timedelta(hours=2), status="error", error="y"),
        _snap(NOW - timedelta(minutes=5), status="healthy"),
    ]
    health = derive_health(snapshots, now=NOW, max_stale_age=STALE)
    assert health["status"] == "healthy"
    assert health["consecutive_failures"] == 0


def test_consecutive_failures_after_last_success():
    snapshots = [
        _snap(NOW - timedelta(hours=3), status="healthy"),
        _snap(NOW - timedelta(hours=2), status="error", error="a"),
        _snap(NOW - timedelta(hours=1), status="error", error="b"),
    ]
    health = derive_health(snapshots, now=NOW, max_stale_age=STALE)
    assert health["consecutive_failures"] == 2
    assert health["status"] == "stale"


def test_naive_datetimes_treated_as_utc():
    naive = datetime(2026, 8, 22, 12, 0, 0)
    health = derive_health([_snap(naive)], now=NOW, max_stale_age=STALE)
    assert health["status"] == "healthy"
    assert health["age_seconds"] == pytest.approx(0)


def test_default_max_stale_age_derives_from_interval():
    assert default_max_stale_age(60) == timedelta(minutes=120)
    assert default_max_stale_age(15) == timedelta(minutes=30)
    # A zero/negative interval still yields a sane floor.
    assert default_max_stale_age(0) == timedelta(minutes=2)
