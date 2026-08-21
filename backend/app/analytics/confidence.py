"""Forecast confidence and data-quality scoring."""

from __future__ import annotations

from datetime import UTC, datetime
from statistics import pstdev

from app.analytics.types import Observation

LEVELS = ("high", "medium", "low")


def _span_days(observations: list[Observation], now: datetime | None = None) -> float:
    if not observations:
        return 0.0
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    first = min(obs.observed_at for obs in observations)
    if first.tzinfo is None:
        first = first.replace(tzinfo=UTC)
    return max((current - first).total_seconds() / 86_400.0, 0.0)


def _coefficient_of_variation(deltas: list[float]) -> float | None:
    if len(deltas) < 2:
        return None
    mean = sum(deltas) / len(deltas)
    if mean <= 0:
        return None
    return pstdev(deltas) / mean


def confidence_level(
    observations: list[Observation],
    *,
    coverage: float | None = None,
) -> dict:
    """Score forecast confidence as high/medium/low from available history.

    Factors: observation count, time span, data coverage, whether any
    provider-native history is present, and variance of the consumption signal.
    """
    if not observations:
        return {"level": "low", "score": 0, "reason": "No observations available"}

    count = len(observations)
    span_days = _span_days(observations)
    native = any(obs.source == "native" for obs in observations)
    deltas = [obs.value for obs in observations if obs.kind == "delta"]
    cv = _coefficient_of_variation(deltas)
    cov = coverage if coverage is not None else 1.0

    score = 0
    reasons: list[str] = []

    if count >= 30:
        score += 2
        reasons.append(f"{count} observations")
    elif count >= 10:
        score += 1
        reasons.append(f"{count} observations")
    else:
        reasons.append(f"only {count} observations")

    if span_days >= 14:
        score += 2
        reasons.append(f"{span_days:.0f} days of history")
    elif span_days >= 3:
        score += 1
        reasons.append(f"{span_days:.0f} days of history")
    else:
        reasons.append("short history")

    if cov >= 0.9:
        score += 2
        reasons.append(f"{cov:.0%} coverage")
    elif cov >= 0.7:
        score += 1
        reasons.append(f"{cov:.0%} coverage")
    elif cov < 0.5:
        score -= 1
        reasons.append(f"{cov:.0%} coverage (gaps present)")

    if native:
        score += 1
        reasons.append("provider-native history")
    if cv is not None and cv > 1.0:
        score -= 1
        reasons.append("high variance")

    if score >= 6:
        level = "high"
    elif score >= 4:
        level = "medium"
    else:
        level = "low"

    return {
        "level": level,
        "score": max(score, 0),
        "reason": ", ".join(reasons),
        "coverage": cov,
    }
