from datetime import UTC, datetime, timedelta
from dataclasses import asdict
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import asc, delete, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import require_admin_auth
from app.core.config import settings
from app.core.crypto import CryptoError, CryptoService
from app.database import get_session
from app.models import ProviderConfig, UsageSnapshot
from app.providers.registry import get_adapter_class, list_providers
from app.schemas import DashboardConfigUsage, HomepagePayload, ProviderConfigCreate, ProviderConfigRead, ProviderConfigUpdate, ProviderInfo, UsageSnapshotRead

router = APIRouter()

def _crypto() -> CryptoService:
    return CryptoService(settings.encryption_key)

def _config_read(config: ProviderConfig) -> ProviderConfigRead:
    return ProviderConfigRead.model_validate(config)

@router.get("/providers", response_model=list[ProviderInfo])
async def providers() -> list[dict]:
    return list_providers()

@router.get("/configs", response_model=list[ProviderConfigRead], dependencies=[Depends(require_admin_auth)])
async def list_configs(session: AsyncSession = Depends(get_session)):
    rows = (await session.execute(select(ProviderConfig).order_by(ProviderConfig.provider, ProviderConfig.label))).scalars().all()
    return [_config_read(row) for row in rows]

@router.post("/configs", response_model=ProviderConfigRead, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_admin_auth)])
async def create_config(payload: ProviderConfigCreate, session: AsyncSession = Depends(get_session)):
    try:
        get_adapter_class(payload.provider)
        encrypted = _crypto().encrypt(payload.api_key)
    except (ValueError, CryptoError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    config = ProviderConfig(provider=payload.provider, label=payload.label, encrypted_api_key=encrypted, base_url=payload.base_url, extra=payload.extra, is_enabled=payload.is_enabled)
    session.add(config)
    try:
        await session.commit()
    except Exception as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail="Provider label already exists or database rejected the config") from exc
    await session.refresh(config)
    return _config_read(config)

@router.patch("/configs/{config_id}", response_model=ProviderConfigRead, dependencies=[Depends(require_admin_auth)])
async def update_config(config_id: int, payload: ProviderConfigUpdate, session: AsyncSession = Depends(get_session)):
    config = await session.get(ProviderConfig, config_id)
    if not config:
        raise HTTPException(status_code=404, detail="Provider config not found")
    if payload.label is not None:
        config.label = payload.label
    if payload.api_key is not None:
        config.encrypted_api_key = _crypto().encrypt(payload.api_key)
    if payload.base_url is not None:
        config.base_url = payload.base_url
    if payload.extra is not None:
        config.extra = payload.extra
    if payload.is_enabled is not None:
        config.is_enabled = payload.is_enabled
    await session.commit()
    await session.refresh(config)
    return _config_read(config)

@router.delete("/configs/{config_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_admin_auth)])
async def delete_config(config_id: int, session: AsyncSession = Depends(get_session)):
    result = await session.execute(delete(ProviderConfig).where(ProviderConfig.id == config_id))
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Provider config not found")
    await session.commit()

@router.get("/configs/{config_id}/history", response_model=list[UsageSnapshotRead], dependencies=[Depends(require_admin_auth)])
async def config_history(config_id: int, hours: int = 168, limit: int = 500, session: AsyncSession = Depends(get_session)):
    config = await session.get(ProviderConfig, config_id)
    if not config:
        raise HTTPException(status_code=404, detail="Provider config not found")
    if hours <= 0:
        raise HTTPException(status_code=400, detail="hours must be greater than zero")
    if limit <= 0:
        raise HTTPException(status_code=400, detail="limit must be greater than zero")
    since = datetime.now(UTC) - timedelta(hours=hours)
    result = await session.execute(select(UsageSnapshot).where(UsageSnapshot.provider_config_id == config_id, UsageSnapshot.checked_at >= since).order_by(asc(UsageSnapshot.checked_at), asc(UsageSnapshot.id)).limit(limit))
    return result.scalars().all()

async def _poll_one(config: ProviderConfig, session: AsyncSession) -> UsageSnapshot:
    try:
        adapter_cls = get_adapter_class(config.provider)
        adapter = adapter_cls(_crypto().decrypt(config.encrypted_api_key), base_url=config.base_url, timeout=settings.request_timeout_seconds, extra=config.extra)
        usage = await adapter.fetch_usage()
        snapshot = UsageSnapshot(provider_config_id=config.id, provider=config.provider, status=usage.status, summary=usage.summary, metrics=[asdict(metric) for metric in usage.metrics], raw=usage.raw, error=None)
    except Exception as exc:
        snapshot = UsageSnapshot(provider_config_id=config.id, provider=config.provider, status="error", summary=f"{config.label}: polling failed", metrics=[], raw={}, error=str(exc))
    session.add(snapshot)
    await session.commit()
    await session.refresh(snapshot)
    return snapshot

@router.post("/configs/{config_id}/poll", response_model=UsageSnapshotRead, dependencies=[Depends(require_admin_auth)])
async def poll_config(config_id: int, session: AsyncSession = Depends(get_session)):
    config = await session.get(ProviderConfig, config_id)
    if not config:
        raise HTTPException(status_code=404, detail="Provider config not found")
    if not config.is_enabled:
        raise HTTPException(status_code=409, detail="Provider config is disabled")
    return await _poll_one(config, session)

@router.post("/poll", response_model=list[UsageSnapshotRead], dependencies=[Depends(require_admin_auth)])
async def poll_all(session: AsyncSession = Depends(get_session)):
    configs = (await session.execute(select(ProviderConfig).where(ProviderConfig.is_enabled.is_(True)))).scalars().all()
    return [await _poll_one(config, session) for config in configs]

@router.get("/usage", response_model=list[DashboardConfigUsage], dependencies=[Depends(require_admin_auth)])
async def usage(session: AsyncSession = Depends(get_session)):
    configs = (await session.execute(select(ProviderConfig).order_by(ProviderConfig.provider, ProviderConfig.label))).scalars().all()
    payload = []
    for config in configs:
        latest = (await session.execute(select(UsageSnapshot).where(UsageSnapshot.provider_config_id == config.id).order_by(desc(UsageSnapshot.checked_at), desc(UsageSnapshot.id)).limit(1))).scalar_one_or_none()
        payload.append({"config": _config_read(config), "latest": latest})
    return payload

@router.get("/homepage", response_model=HomepagePayload, dependencies=[Depends(require_admin_auth)])
async def homepage(session: AsyncSession = Depends(get_session)):
    rows = await usage(session)
    configured = len(rows)
    healthy = degraded = 0
    latest_check = None
    metrics: dict[str, float | int | str | bool | None] = {}
    for row in rows:
        cfg = row["config"]
        latest = row["latest"]
        if latest is None:
            degraded += 1
            continue
        healthy += 1 if latest.status == "healthy" else 0
        degraded += 0 if latest.status == "healthy" else 1
        latest_check = max(latest_check or latest.checked_at, latest.checked_at)
        for metric in latest.metrics:
            key = f"{cfg.provider}_{cfg.label}_{metric.get('label')}".lower().replace(" ", "_")
            metrics[key] = metric.get("value")
    checked = latest_check.astimezone(UTC).isoformat() if latest_check else None
    return HomepagePayload(configured_providers=configured, healthy_providers=healthy, degraded_providers=degraded, latest_check=checked, summary=f"{healthy}/{configured} providers healthy" if configured else "No providers configured", metrics=metrics)
