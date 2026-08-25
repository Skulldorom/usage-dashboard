"""Data source API endpoints.

Data source config CRUD and sync are admin-only. Reading data source status and
observations is available to admin sessions and `datasources:read`/`analytics:read`
scoped tokens.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import asc, delete, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import require_admin_auth, require_scope
from app.core.config import settings
from app.core.crypto import CryptoService
from app.database import get_session
from app.datasources.registry import get_data_source, list_data_sources
from app.datasources.service import sync_data_source
from app.models import DataSourceConfig, ProviderConfig, UsageObservation
from app.schemas import (
    DataSourceConfigCreate,
    DataSourceConfigRead,
    DataSourceConfigUpdate,
    DataSourceInfo,
    DataSourceInspection,
    DataSourceObservationRead,
    DataSourceStatus,
    DataSourceSyncResult,
    HermesObservedProvider,
    HermesProviderMappingOption,
    HermesProviderMappingsRead,
    HermesProviderMappingsUpdate,
)

router = APIRouter()


def _crypto() -> CryptoService:
    return CryptoService(settings.encryption_key)


def _status(source: DataSourceConfig) -> DataSourceStatus:
    if source.last_attempt_at is None:
        state = "never_connected"
    elif source.consecutive_failures == 0 and source.last_success_at is not None:
        state = "healthy"
    else:
        state = "error"
    return DataSourceStatus(
        status=state,
        last_attempt_at=source.last_attempt_at,
        last_success_at=source.last_success_at,
        last_failure_at=source.last_failure_at,
        consecutive_failures=source.consecutive_failures or 0,
        latest_error=source.latest_error,
    )


def _read(source: DataSourceConfig) -> DataSourceConfigRead:
    extra = source.extra or {}
    return DataSourceConfigRead(
        id=source.id,
        kind=source.kind,
        name=source.name,
        base_url=source.base_url,
        profiles=list(extra.get("profiles") or []),
        provider_mappings=dict(extra.get("provider_mappings") or {}),
        mute_unmapped_provider_alerts=bool(extra.get("mute_unmapped_provider_alerts", False)),
        poll_interval_minutes=source.poll_interval_minutes,
        is_enabled=source.is_enabled,
        created_at=source.created_at,
        updated_at=source.updated_at,
        token_masked="••••••••" if source.encrypted_token else "",
        status=_status(source),
    )


def _extra_from(payload_profiles, payload_mappings, mute_unmapped_provider_alerts=None) -> dict:
    extra: dict = {}
    if payload_profiles is not None:
        extra["profiles"] = [str(p).strip() for p in payload_profiles if str(p).strip()]
    if payload_mappings is not None:
        extra["provider_mappings"] = {str(k): str(v) for k, v in payload_mappings.items()}
    if mute_unmapped_provider_alerts is not None:
        extra["mute_unmapped_provider_alerts"] = bool(mute_unmapped_provider_alerts)
    return extra


@router.get("", response_model=list[DataSourceInfo], dependencies=[Depends(require_admin_auth)])
async def data_sources_catalog() -> list[dict]:
    return list_data_sources()


@router.get("/configs", response_model=list[DataSourceConfigRead], dependencies=[Depends(require_scope("datasources:read"))])
async def list_data_source_configs(session: AsyncSession = Depends(get_session)):
    rows = (await session.execute(select(DataSourceConfig).order_by(asc(DataSourceConfig.id)))).scalars().all()
    return [_read(row) for row in rows]


@router.post("/configs", response_model=DataSourceConfigRead, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_admin_auth)])
async def create_data_source_config(payload: DataSourceConfigCreate, session: AsyncSession = Depends(get_session)):
    try:
        get_data_source(payload.kind)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    name = (payload.name or payload.kind).strip() or payload.kind
    encrypted = _crypto().encrypt(payload.token) if payload.token else None
    source = DataSourceConfig(
        kind=payload.kind,
        name=name,
        base_url=payload.base_url,
        encrypted_token=encrypted,
        extra=_extra_from(payload.profiles, payload.provider_mappings, payload.mute_unmapped_provider_alerts),
        is_enabled=payload.is_enabled,
        poll_interval_minutes=payload.poll_interval_minutes,
    )
    session.add(source)
    try:
        await session.commit()
    except Exception as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail="Data source name already exists or the database rejected it") from exc
    await session.refresh(source)
    return _read(source)


@router.patch("/configs/{source_id}", response_model=DataSourceConfigRead, dependencies=[Depends(require_admin_auth)])
async def update_data_source_config(source_id: int, payload: DataSourceConfigUpdate, session: AsyncSession = Depends(get_session)):
    source = await session.get(DataSourceConfig, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Data source not found")
    if payload.has_update_for("name") and payload.name is not None:
        source.name = payload.name.strip()
    if payload.has_update_for("base_url"):
        source.base_url = payload.base_url
    if payload.has_update_for("token"):
        source.encrypted_token = _crypto().encrypt(payload.token) if payload.token else None
    if payload.has_update_for("profiles") or payload.has_update_for("provider_mappings") or payload.has_update_for("mute_unmapped_provider_alerts"):
        extra = dict(source.extra or {})
        extra.update(
            _extra_from(
                payload.profiles,
                payload.provider_mappings,
                payload.mute_unmapped_provider_alerts if payload.has_update_for("mute_unmapped_provider_alerts") else None,
            )
        )
        source.extra = extra
    if payload.has_update_for("poll_interval_minutes") and payload.poll_interval_minutes is not None:
        source.poll_interval_minutes = payload.poll_interval_minutes
    if payload.has_update_for("is_enabled") and payload.is_enabled is not None:
        source.is_enabled = payload.is_enabled
    await session.commit()
    await session.refresh(source)
    return _read(source)


@router.delete("/configs/{source_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_admin_auth)])
async def delete_data_source_config(source_id: int, session: AsyncSession = Depends(get_session)):
    result = await session.execute(delete(DataSourceConfig).where(DataSourceConfig.id == source_id))
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Data source not found")
    await session.commit()


@router.post("/configs/{source_id}/test", dependencies=[Depends(require_admin_auth)])
async def test_data_source(source_id: int, session: AsyncSession = Depends(get_session)):
    source = await session.get(DataSourceConfig, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Data source not found")
    try:
        adapter = get_data_source(source.kind)()
        token = _crypto().decrypt(source.encrypted_token) if source.encrypted_token else None
        records = await adapter.fetch_observations(source.base_url, token, source.extra or {}, settings.request_timeout_seconds)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "records": len(records)}


@router.post("/configs/{source_id}/sync", response_model=DataSourceSyncResult, dependencies=[Depends(require_admin_auth)])
async def sync_data_source_config(source_id: int, session: AsyncSession = Depends(get_session)):
    source = await session.get(DataSourceConfig, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Data source not found")
    if not source.is_enabled:
        raise HTTPException(status_code=409, detail="Data source is disabled")
    result = await sync_data_source(session, source, _crypto())
    return DataSourceSyncResult(**result)


@router.get("/configs/{source_id}/observations", response_model=DataSourceInspection, dependencies=[Depends(require_scope("datasources:read"))])
async def data_source_observations(source_id: int, limit: int = 50, session: AsyncSession = Depends(get_session)):
    source = await session.get(DataSourceConfig, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Data source not found")
    bounded_limit = max(1, min(int(limit or 50), 200))
    rows = (
        await session.execute(
            select(UsageObservation)
            .where(UsageObservation.data_source_id == source_id, UsageObservation.source == "hermes")
            .order_by(desc(UsageObservation.observed_at), desc(UsageObservation.id))
            .limit(bounded_limit)
        )
    ).scalars().all()
    observations = [
        DataSourceObservationRead(
            id=row.id,
            observed_at=row.observed_at,
            provider=row.provider,
            provider_mapping=row.provider_mapping,
            model=row.model,
            profile=row.profile,
            session_id=row.session_id,
            metric=row.metric,
            value=row.value,
            unit=row.unit,
            cost_type=row.cost_type,
            source_event_id=row.source_event_id,
        )
        for row in rows
    ]
    return DataSourceInspection(source=_read(source), observations=observations)


@router.get("/configs/{source_id}/status", response_model=DataSourceStatus, dependencies=[Depends(require_scope("datasources:read"))])
async def data_source_status(source_id: int, session: AsyncSession = Depends(get_session)):
    source = await session.get(DataSourceConfig, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Data source not found")
    return _status(source)


_TOKEN_METRICS = frozenset(
    {"input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens", "reasoning_tokens"}
)


async def _provider_mappings_read(session: AsyncSession, source: DataSourceConfig) -> HermesProviderMappingsRead:
    """Observed raw Hermes providers with aggregate metrics + current mappings.

    ``UsageObservation.provider`` holds the raw identifier observed from Hermes,
    while ``provider_mapping`` holds the effective (mapped) value. This endpoint
    derives the editable attribution layer: every distinct raw provider, its
    aggregate cost/tokens/requests, its last observation, and whether it is
    mapped, unmapped, or mapped to an invalid (deleted/disabled) target.
    """
    enabled = set(
        (
            await session.execute(select(ProviderConfig.provider).where(ProviderConfig.is_enabled.is_(True)))
        ).scalars().all()
    )
    config_rows = (
        await session.execute(
            select(ProviderConfig.provider, ProviderConfig.label).order_by(asc(ProviderConfig.id))
        )
    ).all()
    option_by_provider: dict[str, str] = {}
    for provider, label in config_rows:
        option_by_provider.setdefault(provider, label or "main")
    all_provider_ids = set(option_by_provider)

    agg_rows = (
        await session.execute(
            select(
                UsageObservation.provider,
                UsageObservation.metric,
                func.sum(UsageObservation.value),
                func.max(UsageObservation.observed_at),
                func.count(UsageObservation.id),
            )
            .where(
                UsageObservation.data_source_id == source.id,
                UsageObservation.source == "hermes",
            )
            .group_by(UsageObservation.provider, UsageObservation.metric)
        )
    ).all()

    by_provider: dict[str, dict] = {}
    for provider, metric, total, latest, count in agg_rows:
        raw = str(provider or "unknown").strip().lower() or "unknown"
        entry = by_provider.setdefault(
            raw,
            {"cost": None, "tokens": None, "requests": None, "last_observed_at": None, "observations": 0},
        )
        entry["observations"] += count or 0
        if latest is not None and (entry["last_observed_at"] is None or latest > entry["last_observed_at"]):
            entry["last_observed_at"] = latest
        if total is None:
            continue
        if metric == "cost":
            entry["cost"] = round(float(total), 6)
        elif metric in _TOKEN_METRICS:
            entry["tokens"] = round((entry["tokens"] or 0.0) + float(total), 6)
        elif metric == "requests":
            entry["requests"] = round(float(total), 6)

    mappings = dict((source.extra or {}).get("provider_mappings") or {})
    observed: list[HermesObservedProvider] = []
    mapped_count = 0
    unmapped_count = 0
    unmapped_observations = 0
    for raw in sorted(by_provider):
        entry = by_provider[raw]
        mapped_to = mappings.get(raw)
        status = "unmapped"
        reason = None
        if mapped_to:
            target = str(mapped_to).strip().lower()
            if target in enabled:
                status = "mapped"
            else:
                status = "invalid"
                reason = (
                    f"target provider '{target}' is disabled"
                    if target in all_provider_ids
                    else f"target provider '{target}' no longer exists"
                )
            mapped_to = target
        if status == "mapped":
            mapped_count += 1
        else:
            unmapped_count += 1
            unmapped_observations += entry["observations"]
        observed.append(
            HermesObservedProvider(
                raw_provider=raw,
                cost=entry["cost"],
                tokens=entry["tokens"],
                requests=entry["requests"],
                observations=entry["observations"],
                last_observed_at=entry["last_observed_at"],
                mapped_to=mapped_to,
                status=status,
                reason=reason,
            )
        )

    return HermesProviderMappingsRead(
        source_id=source.id,
        configured_providers=[HermesProviderMappingOption(provider=p, label=option_by_provider[p]) for p in sorted(option_by_provider)],
        mappings=mappings,
        observed=observed,
        mapped_count=mapped_count,
        unmapped_count=unmapped_count,
        unmapped_observations=unmapped_observations,
    )


@router.get("/configs/{source_id}/provider-mappings", response_model=HermesProviderMappingsRead, dependencies=[Depends(require_admin_auth)])
async def get_provider_mappings(source_id: int, session: AsyncSession = Depends(get_session)):
    source = await session.get(DataSourceConfig, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Data source not found")
    return await _provider_mappings_read(session, source)


@router.put("/configs/{source_id}/provider-mappings", response_model=HermesProviderMappingsRead, dependencies=[Depends(require_admin_auth)])
async def put_provider_mappings(source_id: int, payload: HermesProviderMappingsUpdate, session: AsyncSession = Depends(get_session)):
    source = await session.get(DataSourceConfig, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Data source not found")

    all_provider_ids = set(
        (await session.execute(select(ProviderConfig.provider))).scalars().all()
    )
    mappings = dict((source.extra or {}).get("provider_mappings") or {})
    for raw, target in (payload.mappings or {}).items():
        raw_key = str(raw).strip().lower()
        if not raw_key:
            continue
        if target is None or str(target).strip() == "":
            mappings.pop(raw_key, None)  # explicitly left unmapped
            continue
        target_id = str(target).strip().lower()
        if target_id not in all_provider_ids:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown provider '{target_id}': must match a configured Usage Dashboard provider",
            )
        mappings[raw_key] = target_id

    extra = dict(source.extra or {})
    extra["provider_mappings"] = mappings
    source.extra = extra
    await session.commit()
    await session.refresh(source)
    return await _provider_mappings_read(session, source)
