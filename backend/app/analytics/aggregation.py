"""Timezone-aware aggregation of observations into hourly/daily/weekly buckets."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from statistics import median
from zoneinfo import ZoneInfo

from app.analytics.types import Observation

INTERVALS = {"hour": "hourly", "day": "daily", "week": "weekly"}


@dataclass(slots=True)
class Bucket:
    start: datetime
    end: datetime
    total: float = 0.0
    value: float | None = None
    min: float | None = None
    max: float | None = None
    avg: float | None = None
    samples: int = 0
    delta_samples: int = 0
    coverage: float = 0.0


def _as_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def resolve_tz(name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(name or "UTC")
    except Exception:
        return ZoneInfo("UTC")


def bucket_start(dt: datetime, interval: str, tz: ZoneInfo) -> datetime:
    local = dt.astimezone(tz)
    if interval == "hour":
        floored = local.replace(minute=0, second=0, microsecond=0)
    elif interval == "day":
        floored = local.replace(hour=0, minute=0, second=0, microsecond=0)
    elif interval == "week":
        floored = (local - timedelta(days=local.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        raise ValueError(f"Unsupported interval: {interval}")
    return floored


def bucket_span(interval: str) -> timedelta:
    return {"hour": timedelta(hours=1), "day": timedelta(days=1), "week": timedelta(days=7)}[interval]


def median_gap_seconds(observations: list[Observation]) -> float | None:
    """Median interval between consecutive observations (proxy for poll cadence)."""
    if len(observations) < 2:
        return None
    times = sorted(obs.observed_at for obs in observations)
    gaps = [(times[i + 1] - times[i]).total_seconds() for i in range(len(times) - 1)]
    gaps = [gap for gap in gaps if gap > 0]
    if not gaps:
        return None
    return float(median(gaps))


def series_coverage(observations: list[Observation]) -> dict:
    """Estimate data coverage from the gap between samples.

    Expected samples are derived from the median gap; a server outage shows up
    as an oversized gap that lowers coverage instead of reading as zero usage.
    """
    if not observations:
        return {"expected": 0, "actual": 0, "coverage": 0.0, "span_seconds": 0, "median_gap_seconds": None}
    times = sorted(obs.observed_at for obs in observations)
    span = (times[-1] - times[0]).total_seconds()
    gap = median_gap_seconds(observations)
    actual = len(observations)
    if gap is None or gap <= 0:
        expected = actual
    else:
        expected = max(1, int(round(span / gap)) + 1)
    coverage = min(1.0, actual / expected) if expected else 0.0
    return {
        "expected": expected,
        "actual": actual,
        "coverage": round(coverage, 4),
        "span_seconds": span,
        "median_gap_seconds": gap,
    }


def bucketize(
    observations: list[Observation],
    *,
    metric: str,
    interval: str,
    tz: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
) -> list[Bucket]:
    """Aggregate a metric's observations into timezone-aware buckets.

    Point observations contribute ``min``/``max``/``avg``/``value`` (last
    reading). Delta observations contribute ``total`` (summed usage). Both
    contribute to ``samples``.
    """
    if interval not in INTERVALS:
        raise ValueError(f"Unsupported interval: {interval}")
    zone = resolve_tz(tz)
    span = bucket_span(interval)
    relevant = [obs for obs in observations if obs.metric == metric]
    if start is not None:
        relevant = [obs for obs in relevant if obs.observed_at >= _as_aware(start)]
    if end is not None:
        relevant = [obs for obs in relevant if obs.observed_at < _as_aware(end)]

    # Accumulators keyed by bucket start (tz-aware).
    acc: dict[datetime, dict] = {}
    gap = median_gap_seconds(relevant)

    for obs in relevant:
        key = bucket_start(obs.observed_at, interval, zone)
        entry = acc.setdefault(
            key,
            {
                "total": 0.0,
                "value": None,
                "min": None,
                "max": None,
                "point_sum": 0.0,
                "point_count": 0,
                "delta_count": 0,
            },
        )
        if obs.kind == "delta":
            entry["total"] += obs.value
            entry["delta_count"] += 1
        else:
            entry["point_sum"] += obs.value
            entry["point_count"] += 1
            entry["value"] = obs.value
            if entry["min"] is None or obs.value < entry["min"]:
                entry["min"] = obs.value
            if entry["max"] is None or obs.value > entry["max"]:
                entry["max"] = obs.value

    buckets: list[Bucket] = []
    for key in sorted(acc):
        entry = acc[key]
        point_count = entry["point_count"]
        delta_count = entry["delta_count"]
        points = point_count + delta_count
        avg = (entry["point_sum"] / point_count) if point_count else None
        expected = max(1, int(round(span.total_seconds() / gap))) if gap and gap > 0 else points
        coverage = min(1.0, points / expected) if points else 0.0
        buckets.append(
            Bucket(
                start=key,
                end=key + span,
                total=entry["total"],
                value=entry["value"],
                min=entry["min"],
                max=entry["max"],
                avg=round(avg, 6) if avg is not None else None,
                samples=point_count,
                delta_samples=delta_count,
                coverage=round(coverage, 4),
            )
        )
    return buckets


def fill_buckets(
    buckets: list[Bucket],
    *,
    interval: str,
    start: datetime | None = None,
    end: datetime | None = None,
    tz: str | None = None,
) -> list[Bucket]:
    """Insert empty buckets between ``start`` and ``end`` so gaps are explicit."""
    zone = resolve_tz(tz)
    span = bucket_span(interval)
    existing = {bucket.start: bucket for bucket in buckets}
    if start is not None and end is not None:
        first = bucket_start(_as_aware(start), interval, zone)
        last = bucket_start(_as_aware(end), interval, zone)
        cursor = first
        while cursor <= last:
            if cursor not in existing:
                existing[cursor] = Bucket(start=cursor, end=cursor + span)
            cursor += span
    return [existing[key] for key in sorted(existing)]
