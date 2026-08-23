"""Data source sync: fetch → normalize → persist (idempotent) → health.

Kept separate from the provider polling path. A data source outage must never
delete previously persisted history; it only records a failure.
"""

from __future__ import annotations

import asyncio
import hashlib
from datetime import UTC, datetime
from math import isfinite
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.crypto import CryptoService
from app.analytics.normalizer import parse_time
from app.datasources.base import HERMES_METRIC_FIELDS, expand_observation_records
from app.datasources.registry import get_data_source
from app.models import DataSourceConfig, ProviderConfig, UsageObservation

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




def _numeric_metric_count(record: dict) -> tuple[int, int]:
    valid = 0
    invalid = 0
    for field, _unit in HERMES_METRIC_FIELDS:
        if field not in record or record.get(field) is None:
            continue
        try:
            value = float(record.get(field))
        except (TypeError, ValueError):
            invalid += 1
            continue
        if isfinite(value):
            valid += 1
        else:
            invalid += 1
    return valid, invalid


def _sync_diagnostics(
    records: list[dict],
    produced: list[dict],
    accepted: list[dict],
    profiles: list[str] | None,
    provider_mappings: dict[str, str],
    configured_providers: set[str],
) -> dict[str, Any]:
    invalid_timestamps = 0
    records_accepted = 0
    records_without_metrics = 0
    invalid_metrics = 0
    profile_filtered = 0
    raw_providers: set[str] = set()
    raw_profiles: set[str] = set()
    unmapped: set[str] = set()

    produced_by_profile = len(produced)
    if profiles:
        produced_by_profile = sum(1 for obs in produced if obs.get("profile") in profiles)
        profile_filtered = len(produced) - produced_by_profile

    for record in records or []:
        valid_timestamp = parse_time(record.get("timestamp")) is not None
        if not valid_timestamp:
            invalid_timestamps += 1
        valid_metrics, bad_metrics = _numeric_metric_count(record)
        invalid_metrics += bad_metrics
        if valid_metrics and valid_timestamp:
            records_accepted += 1
        if not valid_metrics:
            records_without_metrics += 1
        provider = str(record.get("provider") or "unknown").strip().lower() or "unknown"
        raw_providers.add(provider)
        if record.get("profile"):
            raw_profiles.add(str(record.get("profile")))
        mapped = str(provider_mappings.get(provider, provider)).strip().lower()
        if configured_providers and mapped not in configured_providers:
            unmapped.add(provider)

    observed_times = [_utc(obs["observed_at"]) for obs in accepted if obs.get("observed_at")]
    return {
        "records_fetched": len(records or []),
        "records_accepted": records_accepted,
        "observations_produced": len(produced),
        "observations_accepted": len(accepted),
        "records_skipped_invalid_timestamp": invalid_timestamps,
        "records_skipped_no_supported_metrics": records_without_metrics,
        "metrics_skipped_invalid": invalid_metrics,
        "observations_skipped_profile_filter": profile_filtered,
        "earliest_observation_at": min(observed_times).isoformat() if observed_times else None,
        "latest_observation_at": max(observed_times).isoformat() if observed_times else None,
        "providers_discovered": sorted(raw_providers),
        "profiles_discovered": sorted(raw_profiles),
        "unmapped_providers": sorted(unmapped),
    }

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
    """Stable per-observation identity.

    An explicit source ``event_id`` identifies a whole Hermes event, but one
    event expands into multiple metric rows (input_tokens, output_tokens, cost,
    ...). Suffixing the metric keeps each row's identity unique while the DB
    constraint stays a simple ``(data_source_id, source_event_id)``. Records
    without an event ID fall back to a provenance hash that already includes the
    metric.
    """
    event_id = obs.get("event_id")
    if event_id:
        return f"{event_id}:{obs['metric']}"
    return _fallback_event_id(obs)


async def _persist_observations(
    session: AsyncSession,
    source: DataSourceConfig,
    observations: list[dict],
) -> dict[str, int]:
    if not observations:
        return {"inserted": 0, "duplicates_skipped": 0}

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
        return {"inserted": len(to_insert), "duplicates_skipped": len(rows) - len(to_insert)}
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
        return {"inserted": inserted, "duplicates_skipped": len(rows) - inserted}


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
        observations_produced = expand_observation_records(records)
        profiles = _profiles(source.extra or {})
        observations = observations_produced
        if profiles:
            observations = [o for o in observations if o.get("profile") in profiles]
        extra = source.extra or {}
        observations = [_apply_provider_mappings(o, extra) for o in observations]
        configured_providers = set(
            (
                await session.execute(select(ProviderConfig.provider).where(ProviderConfig.is_enabled.is_(True)))
            ).scalars().all()
        )
        diagnostics = _sync_diagnostics(
            records,
            observations_produced,
            observations,
            profiles,
            dict(extra.get("provider_mappings") or {}),
            {p.strip().lower() for p in configured_providers},
        )
        persist_result = await _persist_observations(session, source, observations)
        inserted = persist_result["inserted"]

        source.last_success_at = now
        source.consecutive_failures = 0
        source.latest_error = None
        await session.commit()
        return {
            "status": "healthy",
            "inserted": inserted,
            "observed": len(observations),
            "duplicates_skipped": persist_result["duplicates_skipped"],
            **diagnostics,
        }
    except Exception as exc:  # noqa: BLE001 - record any failure, never leak tokens
        source.last_failure_at = now
        source.consecutive_failures = (source.consecutive_failures or 0) + 1
        source.latest_error = str(exc)
        await session.commit()
        return {"status": "error", "inserted": 0, "observed": 0, "error": str(exc)}
