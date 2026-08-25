"""Unit tests for source reconciliation (app.analytics.reconciliation)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.analytics.reconciliation import (
    ACTIVITY_DISAGREEMENT_RELATIVE,
    CAPACITY_DISAGREEMENT_POINTS,
    SOURCE_PRIORITY,
    authoritative_source,
    degrade_confidence,
    detect_disagreements,
    reconcile,
    stale_authoritative,
)


# ---------------------------------------------------------------------------
# authoritative_source
# ---------------------------------------------------------------------------


def test_authoritative_source_prefers_native():
    assert authoritative_source(["hermes", "native", "snapshot"]) == "native"
    assert authoritative_source(["estimated", "snapshot"]) == "snapshot"


def test_authoritative_source_ignores_empty_and_unknown():
    assert authoritative_source([]) is None
    assert authoritative_source(None) is None
    assert authoritative_source([""]) is None
    # unknown sources sort last (priority 9) but still resolve to one
    assert authoritative_source(["unknown-x", "hermes"]) == "hermes"


# ---------------------------------------------------------------------------
# detect_disagreements
# ---------------------------------------------------------------------------


def test_capacity_disagreement_detected_beyond_tolerance():
    disagreements = detect_disagreements(100.0, [{"source": "hermes", "value": 130.0}], is_percent=True)
    assert len(disagreements) == 1
    assert disagreements[0]["delta"] == 30.0


def test_capacity_agreement_within_tolerance():
    disagreements = detect_disagreements(100.0, [{"source": "hermes", "value": 110.0}], is_percent=True)
    assert disagreements == []


def test_activity_disagreement_is_relative():
    # 50% relative threshold: 90 vs 100 is within, 40 vs 100 is not
    assert detect_disagreements(100.0, [{"source": "hermes", "value": 90.0}]) == []
    disagreements = detect_disagreements(100.0, [{"source": "hermes", "value": 40.0}])
    assert len(disagreements) == 1


def test_missing_and_non_numeric_values_are_not_disagreements():
    assert detect_disagreements(100.0, [{"source": "hermes", "value": None}]) == []
    assert detect_disagreements(100.0, [{"source": "hermes", "value": "n/a"}]) == []
    assert detect_disagreements(100.0, [{"source": "hermes"}]) == []
    assert detect_disagreements(None, [{"source": "hermes", "value": 500.0}]) == []


def test_activity_zero_authoritative_never_disagrees():
    assert detect_disagreements(0.0, [{"source": "hermes", "value": 100.0}]) == []


# ---------------------------------------------------------------------------
# stale_authoritative
# ---------------------------------------------------------------------------


def test_stale_when_corroborating_is_fresher_beyond_margin():
    auth = datetime(2025, 8, 1, 0, 0, tzinfo=UTC)
    corr = auth + timedelta(hours=10)
    assert stale_authoritative(auth, [corr]) is True


def test_not_stale_within_margin():
    auth = datetime(2025, 8, 1, 0, 0, tzinfo=UTC)
    corr = auth + timedelta(hours=1)
    assert stale_authoritative(auth, [corr]) is False


def test_not_stale_when_authoritative_is_fresher():
    auth = datetime(2025, 8, 2, 0, 0, tzinfo=UTC)
    corr = auth - timedelta(hours=10)
    assert stale_authoritative(auth, [corr]) is False


def test_not_stale_when_authoritative_missing():
    assert stale_authoritative(None, [datetime(2025, 8, 1, tzinfo=UTC)]) is False


def test_stale_naive_timestamps_treated_as_utc():
    auth = datetime(2025, 8, 1, 0, 0, 0)
    corr = auth + timedelta(hours=10)
    assert stale_authoritative(auth, [corr]) is True


# ---------------------------------------------------------------------------
# reconcile
# ---------------------------------------------------------------------------


def test_reconcile_clean():
    result = reconcile(
        authoritative_source_name="native",
        authoritative_value=50.0,
        authoritative_at=datetime(2025, 8, 1, tzinfo=UTC),
        corroborating=[{"source": "hermes", "value": 55.0}],
        corroborating_sources=["hermes"],
        corroborating_times=[datetime(2025, 8, 1, 1, tzinfo=UTC)],
        is_percent=True,
    )
    assert result["authoritative_source"] == "native"
    assert result["has_disagreement"] is False
    assert result["stale_authoritative"] is False
    assert result["confidence_impact"] == 0


def test_reconcile_disagreement_reduces_confidence():
    result = reconcile(
        authoritative_source_name="native",
        authoritative_value=50.0,
        authoritative_at=datetime(2025, 8, 1, tzinfo=UTC),
        corroborating=[{"source": "hermes", "value": 90.0}],
        is_percent=True,
    )
    assert result["has_disagreement"] is True
    assert result["confidence_impact"] == -1


def test_reconcile_stale_reduces_confidence():
    result = reconcile(
        authoritative_source_name="snapshot",
        authoritative_value=50.0,
        authoritative_at=datetime(2025, 8, 1, tzinfo=UTC),
        corroborating=[{"source": "hermes", "value": 55.0}],
        corroborating_times=[datetime(2025, 8, 2, tzinfo=UTC)],
        is_percent=True,
    )
    assert result["stale_authoritative"] is True
    assert result["confidence_impact"] == -1


def test_reconcile_disagreement_and_stale_stack():
    result = reconcile(
        authoritative_source_name="native",
        authoritative_value=50.0,
        authoritative_at=datetime(2025, 8, 1, tzinfo=UTC),
        corroborating=[{"source": "hermes", "value": 90.0}],
        corroborating_times=[datetime(2025, 8, 2, tzinfo=UTC)],
        is_percent=True,
    )
    assert result["has_disagreement"] is True
    assert result["stale_authoritative"] is True
    assert result["confidence_impact"] == -2


# ---------------------------------------------------------------------------
# degrade_confidence
# ---------------------------------------------------------------------------


def test_degrade_confidence_steps():
    assert degrade_confidence("high", -1) == "medium"
    assert degrade_confidence("high", -2) == "low"
    assert degrade_confidence("medium", -1) == "low"
    assert degrade_confidence("low", -1) == "low"
    assert degrade_confidence("low", -5) == "low"


def test_degrade_confidence_no_impact_preserves_level():
    assert degrade_confidence("high", 0) == "high"
    assert degrade_confidence(None, 0) == "low"


# ---------------------------------------------------------------------------
# constants sanity
# ---------------------------------------------------------------------------


def test_priority_ordering():
    assert SOURCE_PRIORITY["native"] < SOURCE_PRIORITY["snapshot"] < SOURCE_PRIORITY["hermes"] < SOURCE_PRIORITY["estimated"]
    assert CAPACITY_DISAGREEMENT_POINTS > 0
    assert ACTIVITY_DISAGREEMENT_RELATIVE > 0
