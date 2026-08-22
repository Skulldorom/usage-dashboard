"""Data source sync: fetch → normalize → persist (idempotent) → health.

Kept separate from the provider polling path. A data source outage must never
delete previously persisted history; it only records a failure.
"""

from __future__ import annotations

import asyncio
import hashlib
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.crypto import CryptoService
from app.datasources.base import expand_observation_records
from app.datasources.registry import get_data_source
from app.models import DataSourceConfig, UsageObservation

# Per-source sync locks (keyed by data source id). Shared by the manual sync
# endpoint and the background poller so neither overlaps the other.
_locks: dict[int, asyncio.Lock] = {}


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


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


def _fallback_event_id(obs: dict) -> str:
    """Deterministic identity for records without an explicit source event ID.

    Hashing all provenance (provider, timestamp, session, profile, model, cost
    type, metric, value, unit) keeps distinct observations distinct while making
    a re-fetch of identical data collapse to the same ID.
    """
    key = "|".join(
        [
            obs.get("provider") or "",
            _utc(obs["observed_at"]).isoformat(),
            obs.get("session_id") or "",
            obs.get("profile") or "",
            obs.get("model") or "",
            obs.get("cost_type") or "",
            obs.get("metric") or "",
            repr(obs.get("value")),
            obs.get("unit") or "",
        ]
    )
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:48]


def _source_event_id(obs: dict) -> str:
    return obs.get("event_id") or _fallback_event_id(obs)


async def _persist_observations(
    session: AsyncSession,
    source: DataSourceConfig,
    observations: list[dict],
) -> int:
    if not observations:
        return 0

    # Every observation gets a stable source event ID (explicit event_id or a
    # deterministic fallback). The database unique index on
    # (data_source_id, source_event_id) is the final protection against dupes.
    rows: list[dict] = [
        {**obs, "source_event_id": _source_event_id(obs)} for obs in observations
    ]

    def build(row: dict) -> UsageObservation:
        return UsageObservation(
            data_source_id=source.id,
            provider=row["provider"],
            metric=row["metric"],
            value=row["value"],
            unit=row["unit"],
            kind=row["kind"],
            source=row["source"],
            observed_at=row["observed_at"],
            model=row.get("model"),
            profile=row.get("profile"),
            session_id=row.get("session_id"),
            cost_type=row.get("cost_type"),
            provider_mapping=row.get("provider_mapping"),
            source_event_id=row["source_event_id"],
        )

    # Fast-path dedup: skip event IDs already present for this data source.
    existing_ids = set(
        (
            await session.execute(
                select(UsageObservation.source_event_id).where(
                    UsageObservation.data_source_id == source.id,
                    UsageObservation.source_event_id.in_([r["source_event_id"] for r in rows]),
                )
            )
        ).scalars().all()
    )
    to_insert = [r for r in rows if r["source_event_id"] not in existing_ids]

    for row in to_insert:
        session.add(build(row))
    try:
        await session.commit()
        return len(to_insert)
    except IntegrityError:
        # Defensive: a concurrent sync inserted the same event ID between our
        # check and commit. Re-insert one-by-one so a single conflict can't drop
        # the rest of the batch (the per-source sync lock normally prevents this).
        await session.rollback()
        inserted = 0
        for row in to_insert:
            session.add(build(row))
            try:
                await session.commit()
                inserted += 1
            except IntegrityError:
                await session.rollback()
        return inserted


async def sync_data_source(
    session: AsyncSession,
    source: DataSourceConfig,
    crypto: CryptoService,
) -> dict[str, Any]:
    """Sync one data source, serializing concurrent syncs of the same source.

    A per-source lock keeps the manual sync endpoint and the background poller
    from overlapping on the same data source. The database unique index on
    (data_source_id, source_event_id) remains the final guard against duplicate
    observations.
    """
    lock = _locks.setdefault(source.id, asyncio.Lock())
    async with lock:
        return await _sync_data_source(session, source, crypto)


async def _sync_data_source(
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
