"""Data source API endpoints.

Data source config CRUD and sync are admin-only. Reading data source status and
observations is available to admin sessions and `datasources:read`/`analytics:read`
scoped tokens.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import asc, delete, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import require_admin_auth, require_scope
from app.core.config import settings
from app.core.crypto import CryptoService
from app.database import get_session
from app.datasources.registry import get_data_source, list_data_sources
from app.datasources.service import sync_data_source
from app.models import DataSourceConfig, UsageObservation
from app.schemas import (
    DataSourceConfigCreate,
    DataSourceConfigRead,
    DataSourceConfigUpdate,
    DataSourceInfo,
    DataSourceInspection,
    DataSourceObservationRead,
    DataSourceStatus,
    DataSourceSyncResult,
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
        poll_interval_minutes=source.poll_interval_minutes,
        is_enabled=source.is_enabled,
        created_at=source.created_at,
        updated_at=source.updated_at,
        token_masked="••••••••" if source.encrypted_token else "",
        status=_status(source),
    )


def _extra_from(payload_profiles, payload_mappings) -> dict:
    extra: dict = {}
    if payload_profiles is not None:
        extra["profiles"] = [str(p).strip() for p in payload_profiles if str(p).strip()]
    if payload_mappings is not None:
        extra["provider_mappings"] = {str(k): str(v) for k, v in payload_mappings.items()}
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
        extra=_extra_from(payload.profiles, payload.provider_mappings),
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
    if payload.has_update_for("profiles") or payload.has_update_for("provider_mappings"):
        extra = dict(source.extra or {})
        extra.update(_extra_from(payload.profiles, payload.provider_mappings))
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
