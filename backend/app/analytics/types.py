"""Shared internal types for the analytics engine."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class Observation:
    """A normalized observation of a single metric.

    ``kind`` distinguishes a point-in-time reading (``"point"``) from an
    interval usage delta (``"delta"``). ``source`` records whether the value
    came from a provider-native historical bucket (``"native"``) or was derived
    from a ``UsageSnapshot`` (``"snapshot"``).

    ``model`` / ``provider_mapping`` / ``profile`` / ``session_id`` /
    ``cost_type`` are telemetry provenance carried through from Hermes
    observations so downstream layers (e.g. cost estimation) can key on them.
    """

    metric: str
    value: float
    unit: str | None
    observed_at: datetime
    kind: str
    source: str
    window_start: datetime | None = None
    window_end: datetime | None = None
    reset_at: datetime | None = None
    model: str | None = None
    provider_mapping: str | None = None
    profile: str | None = None
    session_id: str | None = None
    cost_type: str | None = None

    def to_dict(self) -> dict:
        return {
            "metric": self.metric,
            "value": self.value,
            "unit": self.unit,
            "observed_at": self.observed_at,
            "kind": self.kind,
            "source": self.source,
            "window_start": self.window_start,
            "window_end": self.window_end,
            "reset_at": self.reset_at,
            "model": self.model,
            "provider_mapping": self.provider_mapping,
            "profile": self.profile,
            "session_id": self.session_id,
            "cost_type": self.cost_type,
        }
