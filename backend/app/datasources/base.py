"""Generic observed-telemetry data source abstractions."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from math import isfinite
from typing import Any

from app.analytics.normalizer import parse_time

METRIC_FIELDS: tuple[tuple[str, str], ...] = (
    ("input_tokens", "tokens"),
    ("output_tokens", "tokens"),
    ("cache_read_tokens", "tokens"),
    ("cache_write_tokens", "tokens"),
    ("reasoning_tokens", "tokens"),
    ("requests", "count"),
    ("cost", "USD"),
)
# Backward-compatible import name for existing data-source analytics code.
HERMES_METRIC_FIELDS = METRIC_FIELDS


@dataclass(frozen=True)
class DataSourceFetchResult:
    records: list[dict]
    cursor: str | None = None


class DataSourceRetryError(ValueError):
    """A source failure that supplies scheduler eligibility metadata."""

    def __init__(self, message: str, retry_after_seconds: int):
        super().__init__(message)
        self.retry_after_seconds = max(0, retry_after_seconds)


class DataSource(ABC):
    """Read-only application or gateway telemetry adapter."""

    id: str
    name: str
    description: str
    metric_names: list[str] = [field for field, _unit in METRIC_FIELDS]
    default_poll_interval_minutes: int = 60

    @abstractmethod
    async def fetch_observations(
        self,
        base_url: str | None,
        token: str | None,
        extra: dict[str, Any],
        timeout: float,
    ) -> DataSourceFetchResult | list[dict]:
        """Fetch records with optional source-owned incremental cursor metadata."""
        raise NotImplementedError


def _record_event_id(record: dict) -> str | None:
    for key in ("event_id", "id"):
        value = record.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def expand_observation_records(records: list[dict], source: str = "hermes") -> list[dict]:
    """Expand source events into generic, metric-level observations."""
    observations: list[dict] = []
    for record in records or []:
        observed_at = parse_time(record.get("timestamp"))
        if observed_at is None:
            continue
        provider = _normalize_provider(record.get("provider"))
        event_id = _record_event_id(record)
        for field, unit in METRIC_FIELDS:
            value = record.get(field)
            if value is None:
                continue
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                continue
            if not isfinite(numeric):
                continue
            observations.append(
                {
                    "metric": field,
                    "value": numeric,
                    "unit": unit,
                    "observed_at": observed_at,
                    "kind": "delta",
                    "source": source,
                    "provider": provider or "unknown",
                    "model": record.get("model"),
                    "profile": record.get("profile"),
                    "session_id": record.get("session_id"),
                    "cost_type": record.get("cost_type") if field == "cost" else None,
                    "provider_mapping": provider,
                    "event_id": event_id,
                }
            )
    return observations


def _normalize_provider(value: Any) -> str | None:
    if not value:
        return None
    return str(value).strip().lower()
