"""Data source sync: fetch → normalize → persist (idempotent) → health.

Kept separate from the provider polling path. A data source outage must never
delete previously persisted history; it only records a failure.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.crypto import CryptoService
from app.datasources.base import expand_observation_records
from app.datasources.registry import get_data_source
from app.models import DataSourceConfig, UsageObservation


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _observation_key(obs: dict) -> tuple:
    return (
        obs["metric"],
        _utc(obs["observed_at"]),
        obs.get("profile"),
        obs.get("session_id"),
        obs.get("provider"),
    )


def _row_key(row: UsageObservation) -> tuple:
    return (row.metric, _utc(row.observed_at), row.profile, row.session_id, row.provider)


def _profiles(extra: dict[str, Any]) -> list[str] | None:
    profiles = extra.get("profiles")
    if isinstance(profiles, list) and profiles:
        return [str(p) for p in profiles]
    return None


def _apply_provider_mappings(obs: dict, extra: dict[str, Any]) -> dict:
    mappings = extra.get("provider_mappings") or {}
    raw = obs.get("provider_mapping")
    if raw and raw in mappings:
        obs["provider_mapping"] = str(mappings[raw]).strip().lower()
    return obs


async def _persist_observations(
    session: AsyncSession,
    source: DataSourceConfig,
    observations: list[dict],
) -> int:
    if not observations:
        return 0
    lower = min(o["observed_at"] for o in observations)
    upper = max(o["observed_at"] for o in observations)
    existing = (
        await session.execute(
            select(UsageObservation).where(
                UsageObservation.data_source_id == source.id,
                UsageObservation.source == "hermes",
                UsageObservation.observed_at >= lower,
                UsageObservation.observed_at <= upper,
            )
        )
    ).scalars().all()
    by_key = {_row_key(row): row for row in existing}

    inserted = 0
    for obs in observations:
        if _observation_key(obs) in by_key:
            continue
        session.add(
            UsageObservation(
                data_source_id=source.id,
                provider=obs["provider"],
                metric=obs["metric"],
                value=obs["value"],
                unit=obs["unit"],
                kind=obs["kind"],
                source=obs["source"],
                observed_at=obs["observed_at"],
                model=obs.get("model"),
                profile=obs.get("profile"),
                session_id=obs.get("session_id"),
                cost_type=obs.get("cost_type"),
                provider_mapping=obs.get("provider_mapping"),
            )
        )
        inserted += 1
    await session.commit()
    return inserted


async def sync_data_source(
    session: AsyncSession,
    source: DataSourceConfig,
    crypto: CryptoService,
) -> dict[str, Any]:
    """Fetch and persist observations for one data source, updating its health."""
    adapter_cls = get_data_source(source.kind)
    adapter = adapter_cls()
    now = datetime.now(UTC)
    token = crypto.decrypt(source.encrypted_token) if source.encrypted_token else None
    source.last_attempt_at = now

    try:
        records = await adapter.fetch_observations(
            source.base_url, token, source.extra or {}, settings.request_timeout_seconds
        )
        observations = expand_observation_records(records)
        profiles = _profiles(source.extra or {})
        if profiles:
            observations = [o for o in observations if o.get("profile") in profiles]
        observations = [_apply_provider_mappings(o, source.extra or {}) for o in observations]
        inserted = await _persist_observations(session, source, observations)

        source.last_success_at = now
        source.consecutive_failures = 0
        source.latest_error = None
        await session.commit()
        return {
            "status": "healthy",
            "inserted": inserted,
            "observed": len(observations),
        }
    except Exception as exc:  # noqa: BLE001 - record any failure, never leak tokens
        source.last_failure_at = now
        source.consecutive_failures = (source.consecutive_failures or 0) + 1
        source.latest_error = str(exc)
        await session.commit()
        return {"status": "error", "inserted": 0, "observed": 0, "error": str(exc)}
