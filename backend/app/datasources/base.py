"""Generic data source abstraction.

Data sources are *not* providers. Providers are the accounts/services whose
usage, quotas, balances and limits are being measured (authoritative).
Data sources are applications/gateways/agents that supply additional
telemetry about usage flowing through them (observed). Hermes Agent is the
first data source.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from math import isfinite
from typing import Any

from app.analytics.normalizer import parse_time

# Metric fields a telemetry source may emit, mapped to their display unit.
# These become individual UsageObservation rows (kind="delta", source="hermes").
HERMES_METRIC_FIELDS: tuple[tuple[str, str], ...] = (
    ("input_tokens", "tokens"),
    ("output_tokens", "tokens"),
    ("cache_read_tokens", "tokens"),
    ("cache_write_tokens", "tokens"),
    ("reasoning_tokens", "tokens"),
    ("requests", "count"),
    ("cost", "USD"),
)


class DataSource(ABC):
    """A telemetry source adapter.

    Subclasses implement ``fetch_observations`` to retrieve raw usage records
    over HTTP (read-only) and return them as a list of record dicts matching
    the contract below.
    """

    id: str
    name: str
    description: str
    metric_names: list[str] = [field for field, _unit in HERMES_METRIC_FIELDS]

    @abstractmethod
    async def fetch_observations(
        self,
        base_url: str | None,
        token: str | None,
        extra: dict[str, Any],
        timeout: float,
    ) -> list[dict]:
        """Fetch raw usage records and return them normalized to the contract.

        Each record dict may carry:
          - ``timestamp`` (required; ISO-8601 string, epoch, or datetime)
          - ``provider`` (required; provider id, e.g. ``anthropic``)
          - ``model``, ``profile``, ``session_id``, ``cost_type`` (optional)
          - any of the metric fields in :data:`HERMES_METRIC_FIELDS`
        """
        raise NotImplementedError


def expand_observation_records(records: list[dict]) -> list[dict]:
    """Expand raw telemetry records into per-metric observation dicts.

    Returns dicts ready to persist as ``UsageObservation`` rows with
    ``source="hermes"``. Records with no usable timestamp or no numeric metric
    fields are skipped.
    """
    observations: list[dict] = []
    for record in records or []:
        observed_at = parse_time(record.get("timestamp"))
        if observed_at is None:
            continue
        provider = _normalize_provider(record.get("provider"))
        for field, unit in HERMES_METRIC_FIELDS:
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
                    "source": "hermes",
                    "provider": provider or "unknown",
                    "model": record.get("model"),
                    "profile": record.get("profile"),
                    "session_id": record.get("session_id"),
                    "cost_type": record.get("cost_type") if field == "cost" else None,
                    "provider_mapping": provider,
                }
            )
    return observations


def _normalize_provider(value: Any) -> str | None:
    if not value:
        return None
    return str(value).strip().lower()
