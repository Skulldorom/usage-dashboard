import asyncio
from dataclasses import asdict
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import asc, delete, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.auth import homepage_auth, require_admin_auth
from app.core.config import settings
from app.core.crypto import CryptoError, CryptoService
from app.database import engine, get_session
from app.models import ProviderConfig, UsageSnapshot
from app.providers.registry import get_adapter_class, list_providers
from app.schemas import DashboardConfigUsage, HomepagePayload, HomepageProviderRow, PollStatusRead, ProviderConfigCreate, ProviderConfigOrderUpdate, ProviderConfigRead, ProviderConfigUpdate, ProviderInfo, ProviderUsageRead, UsageSnapshotRead

router = APIRouter()
_auto_poll_lock = asyncio.Lock()
_auto_poll_task: asyncio.Task | None = None
_last_auto_polled_at: datetime | None = None
_next_auto_poll_at: datetime | None = None


def _crypto() -> CryptoService:
    return CryptoService(settings.encryption_key)


def _config_read(config: ProviderConfig) -> ProviderConfigRead:
    return ProviderConfigRead.model_validate(config)


def _config_ordering():
    return (asc(ProviderConfig.display_order), asc(ProviderConfig.id))


def _slug(value: str) -> str:
    return "-".join(value.lower().replace("_", "-").split()) or "provider"


def _iso(value: datetime | None) -> str | None:
    return value.astimezone(UTC).isoformat() if value else None


def _format_homepage_number(value: float | int | str | bool | None) -> str:
    if isinstance(value, bool) or value is None:
        return str(value)
    if isinstance(value, int | float):
        if abs(value) >= 1000:
            return f"{value / 1000:.1f}k".rstrip("0").rstrip(".")
        return f"{value:g}"
    return str(value)


def _homepage_usage_text(metrics: list[dict], summary: str | None) -> str:
    for metric in metrics:
        label = str(metric.get("label") or "").lower().replace("-", "_").replace(" ", "_")
        if "used" in label:
            continue
        if any(token in label for token in ("remaining", "left", "balance")):
            value = _format_homepage_number(metric.get("value"))
            unit = metric.get("unit") or ("credits" if "credit" in label else None)
            suffix = f" {unit}" if unit and unit != "%" else ""
            return f"{value}{suffix} left"

    for metric in metrics:
        label = str(metric.get("label") or "").lower().replace("-", "_").replace(" ", "_")
        unit = metric.get("unit")
        if unit == "%" or "percent" in label:
            direction = "left" if any(token in label for token in ("remaining", "left")) else "used"
            return f"{_format_homepage_number(metric.get('value'))}% {direction}"

    return summary or "No usage snapshot yet"


def _homepage_provider_rows(rows: list[dict]) -> list[HomepageProviderRow]:
    provider_rows = []
    for row in rows:
        cfg = row["config"]
        if not cfg.is_enabled:
            continue
        latest = row["latest"]
        provider_rows.append(
            HomepageProviderRow(
                provider=cfg.provider,
                config_id=cfg.id,
                label=f"{cfg.provider} ({cfg.label})",
                value=_homepage_usage_text(latest.metrics, latest.summary) if latest else "No usage snapshot yet",
                status=latest.status if latest else "unknown",
            )
        )
    return provider_rows


async def _unique_label(session: AsyncSession, provider: str, requested: str | None) -> str:
    base = (requested or "main").strip() or "main"
    existing = set((await session.execute(select(ProviderConfig.label).where(ProviderConfig.provider == provider))).scalars().all())
    if base not in existing:
        return base
    provider_slug = _slug(provider)
    index = 2
    while f"{provider_slug}-{index}" in existing:
        index += 1
    return f"{provider_slug}-{index}"


@router.get("/providers", response_model=list[ProviderInfo])
async def providers() -> list[dict]:
    return list_providers()


@router.get("/configs", response_model=list[ProviderConfigRead], dependencies=[Depends(require_admin_auth)])
async def list_configs(session: AsyncSession = Depends(get_session)):
    rows = (await session.execute(select(ProviderConfig).order_by(*_config_ordering()))).scalars().all()
    return [_config_read(row) for row in rows]


@router.post("/configs", response_model=ProviderConfigRead, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_admin_auth)])
async def create_config(payload: ProviderConfigCreate, session: AsyncSession = Depends(get_session)):
    try:
        get_adapter_class(payload.provider)
        encrypted = _crypto().encrypt(payload.api_key)
    except (ValueError, CryptoError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    label = await _unique_label(session, payload.provider, payload.label)
    display_order = payload.display_order
    if display_order is None:
        max_order = await session.scalar(select(func.max(ProviderConfig.display_order)))
        display_order = int(max_order or 0) + 1 if max_order is not None else 0
    config = ProviderConfig(provider=payload.provider, label=label, encrypted_api_key=encrypted, base_url=payload.base_url, extra=payload.extra, is_enabled=payload.is_enabled, is_visible=payload.is_visible, display_order=display_order)
    session.add(config)
    try:
        await session.commit()
    except Exception as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail="Provider label already exists or database rejected the config") from exc
    await session.refresh(config)
    return _config_read(config)


@router.post("/configs/test", response_model=ProviderUsageRead, dependencies=[Depends(require_admin_auth)])
async def test_config(payload: ProviderConfigCreate):
    try:
        adapter_cls = get_adapter_class(payload.provider)
        adapter = adapter_cls(payload.api_key, base_url=payload.base_url, timeout=settings.request_timeout_seconds, extra=payload.extra)
        usage = await adapter.fetch_usage()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": usage.status, "summary": usage.summary, "metrics": [asdict(metric) for metric in usage.metrics], "raw": usage.raw}


@router.patch("/configs/order", response_model=list[ProviderConfigRead], dependencies=[Depends(require_admin_auth)])
async def reorder_configs(payload: ProviderConfigOrderUpdate, session: AsyncSession = Depends(get_session)):
    existing = (await session.execute(select(ProviderConfig).where(ProviderConfig.id.in_(payload.config_ids)))).scalars().all()
    by_id = {config.id: config for config in existing}
    missing = [config_id for config_id in payload.config_ids if config_id not in by_id]
    if missing:
        raise HTTPException(status_code=404, detail=f"Provider config not found: {missing[0]}")
    for index, config_id in enumerate(payload.config_ids):
        by_id[config_id].display_order = index
    await session.commit()
    rows = (await session.execute(select(ProviderConfig).order_by(*_config_ordering()))).scalars().all()
    return [_config_read(row) for row in rows]


@router.patch("/configs/{config_id}", response_model=ProviderConfigRead, dependencies=[Depends(require_admin_auth)])
async def update_config(config_id: int, payload: ProviderConfigUpdate, session: AsyncSession = Depends(get_session)):
    config = await session.get(ProviderConfig, config_id)
    if not config:
        raise HTTPException(status_code=404, detail="Provider config not found")
    if payload.has_update_for("label") and payload.label is not None:
        config.label = payload.label
    if payload.has_update_for("api_key") and payload.api_key is not None:
        config.encrypted_api_key = _crypto().encrypt(payload.api_key)
    if payload.has_update_for("base_url"):
        config.base_url = payload.base_url
    if payload.has_update_for("extra") and payload.extra is not None:
        config.extra = payload.extra
    if payload.has_update_for("is_enabled") and payload.is_enabled is not None:
        config.is_enabled = payload.is_enabled
    if payload.has_update_for("is_visible") and payload.is_visible is not None:
        config.is_visible = payload.is_visible
    if payload.has_update_for("display_order") and payload.display_order is not None:
        config.display_order = payload.display_order
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


async def _snapshot_for_config(config: ProviderConfig) -> UsageSnapshot:
    try:
        adapter_cls = get_adapter_class(config.provider)
        adapter = adapter_cls(_crypto().decrypt(config.encrypted_api_key), base_url=config.base_url, timeout=settings.request_timeout_seconds, extra=config.extra)
        usage = await adapter.fetch_usage()
        snapshot = UsageSnapshot(provider_config_id=config.id, provider=config.provider, status=usage.status, summary=usage.summary, metrics=[asdict(metric) for metric in usage.metrics], raw=usage.raw, error=None)
    except Exception as exc:
        snapshot = UsageSnapshot(provider_config_id=config.id, provider=config.provider, status="error", summary=f"{config.label}: polling failed", metrics=[], raw={}, error=str(exc))
    return snapshot


async def _prune_old_snapshots(session: AsyncSession) -> None:
    if settings.snapshot_retention_days < 0:
        return
    cutoff = datetime.now(UTC) - timedelta(days=settings.snapshot_retention_days)
    ranked_snapshots = select(
        UsageSnapshot.id,
        func.row_number().over(partition_by=UsageSnapshot.provider_config_id, order_by=(desc(UsageSnapshot.checked_at), desc(UsageSnapshot.id))).label("rank"),
    ).subquery()
    latest_snapshot_ids = select(ranked_snapshots.c.id).where(ranked_snapshots.c.rank == 1)
    await session.execute(delete(UsageSnapshot).where(UsageSnapshot.checked_at < cutoff, UsageSnapshot.id.not_in(latest_snapshot_ids)))
    await session.commit()


async def _poll_enabled_configs(session: AsyncSession) -> list[UsageSnapshot]:
    configs = (await session.execute(select(ProviderConfig).where(ProviderConfig.is_enabled.is_(True)).order_by(*_config_ordering()))).scalars().all()
    snapshots = await asyncio.gather(*(_snapshot_for_config(config) for config in configs)) if configs else []
    if snapshots:
        session.add_all(snapshots)
        await session.commit()
        for snapshot in snapshots:
            await session.refresh(snapshot)
        await _prune_old_snapshots(session)
    return snapshots


async def _run_auto_poll_once() -> None:
    global _last_auto_polled_at
    if _auto_poll_lock.locked():
        return
    async with _auto_poll_lock:
        Session = async_sessionmaker(engine, expire_on_commit=False)
        async with Session() as session:
            await _poll_enabled_configs(session)
        _last_auto_polled_at = datetime.now(UTC)


async def auto_poll_loop() -> None:
    global _next_auto_poll_at
    if not settings.auto_poll_enabled:
        _next_auto_poll_at = None
        return
    interval = timedelta(minutes=settings.auto_poll_interval_minutes)
    while True:
        _next_auto_poll_at = datetime.now(UTC) + interval
        await asyncio.sleep(interval.total_seconds())
        await _run_auto_poll_once()


def start_auto_polling() -> None:
    global _auto_poll_task, _next_auto_poll_at
    if not settings.auto_poll_enabled:
        _next_auto_poll_at = None
        return
    if _auto_poll_task is None or _auto_poll_task.done():
        _next_auto_poll_at = datetime.now(UTC) + timedelta(minutes=settings.auto_poll_interval_minutes)
        _auto_poll_task = asyncio.create_task(auto_poll_loop())


async def stop_auto_polling() -> None:
    global _auto_poll_task, _next_auto_poll_at
    if _auto_poll_task:
        _auto_poll_task.cancel()
        try:
            await _auto_poll_task
        except asyncio.CancelledError:
            pass
    _auto_poll_task = None
    _next_auto_poll_at = None


@router.post("/configs/{config_id}/poll", response_model=UsageSnapshotRead, dependencies=[Depends(require_admin_auth)])
async def poll_config(config_id: int, session: AsyncSession = Depends(get_session)):
    config = await session.get(ProviderConfig, config_id)
    if not config:
        raise HTTPException(status_code=404, detail="Provider config not found")
    if not config.is_enabled:
        raise HTTPException(status_code=409, detail="Provider config is disabled")
    return await _poll_one(config, session)


async def _poll_one(config: ProviderConfig, session: AsyncSession) -> UsageSnapshot:
    snapshot = await _snapshot_for_config(config)
    session.add(snapshot)
    await session.commit()
    await session.refresh(snapshot)
    await _prune_old_snapshots(session)
    return snapshot


@router.post("/poll", response_model=list[UsageSnapshotRead], dependencies=[Depends(require_admin_auth)])
async def poll_all(session: AsyncSession = Depends(get_session)):
    async with _auto_poll_lock:
        return await _poll_enabled_configs(session)


@router.get("/poll/status", response_model=PollStatusRead, dependencies=[Depends(require_admin_auth)])
async def poll_status():
    return PollStatusRead(
        auto_poll_enabled=settings.auto_poll_enabled,
        interval_seconds=settings.auto_poll_interval_minutes * 60,
        is_polling=_auto_poll_lock.locked(),
        last_polled_at=_iso(_last_auto_polled_at),
        next_poll_at=_iso(_next_auto_poll_at),
    )


@router.get("/usage", response_model=list[DashboardConfigUsage], dependencies=[Depends(require_admin_auth)])
async def usage(session: AsyncSession = Depends(get_session)):
    configs = (await session.execute(select(ProviderConfig).order_by(*_config_ordering()))).scalars().all()
    payload = []
    for config in configs:
        latest = (await session.execute(select(UsageSnapshot).where(UsageSnapshot.provider_config_id == config.id).order_by(desc(UsageSnapshot.checked_at), desc(UsageSnapshot.id)).limit(1))).scalar_one_or_none()
        payload.append({"config": _config_read(config), "latest": latest})
    return payload


@router.get("/homepage", response_model=HomepagePayload, dependencies=[Depends(homepage_auth)])
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
    return HomepagePayload(configured_providers=configured, healthy_providers=healthy, degraded_providers=degraded, latest_check=checked, summary=f"{healthy}/{configured} providers healthy" if configured else "No providers configured", metrics=metrics, list=_homepage_provider_rows(rows))
