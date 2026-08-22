import asyncio
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from secrets import token_urlsafe

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import asc, delete, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.analytics.normalizer import normalize_native, normalize_snapshots
from app.core.auth import auth_status, bearer_scheme, create_api_token_record, homepage_auth, login_admin, request_password_reset, require_admin_auth, require_scope, reset_admin_password, revoke_admin_session, revoke_api_token_record, setup_admin_password
from app.core.config import settings
from app.core.crypto import CryptoError, CryptoService
from app.core.thresholds import build_alerts, provider_alert_state
from app.database import engine, get_session
from app.health import default_max_stale_age, derive_health
from app.models import ApiToken, ProviderConfig, UsageObservation, UsageSnapshot
from app.providers import codex_oauth
from app.providers.registry import get_adapter_class, list_providers
from app.schemas import AlertStateRead, ApiTokenCreate, ApiTokenCreated, ApiTokenRead, AuthCodePasswordRequest, AuthPasswordRequest, AuthStatusRead, AuthTokenRead, CodexBrowserCompleteRead, CodexBrowserCompleteRequest, CodexBrowserStartRead, CodexDevicePollRead, CodexDevicePollRequest, CodexDeviceStartRead, DashboardConfigUsage, HomepagePayload, HomepageProviderRow, PollStatusRead, ProviderConfigCreate, ProviderConfigOrderUpdate, ProviderConfigRead, ProviderConfigUpdate, ProviderInfo, ProviderUsageRead, UsageSnapshotRead

router = APIRouter()
_auto_poll_lock = asyncio.Lock()
_auto_poll_task: asyncio.Task | None = None
_last_auto_polled_at: datetime | None = None
_next_auto_poll_at: datetime | None = None
_codex_device_flows: dict[str, codex_oauth.CodexDeviceStart] = {}
_codex_browser_flows: dict[str, codex_oauth.CodexBrowserStart] = {}
_codex_device_lock = asyncio.Lock()


def _crypto() -> CryptoService:
    return CryptoService(settings.encryption_key)


def _config_read(config: ProviderConfig) -> ProviderConfigRead:
    return ProviderConfigRead.model_validate(config)


def _config_ordering():
    return (asc(ProviderConfig.display_order), asc(ProviderConfig.id))


def _api_token_read(record: ApiToken) -> ApiTokenRead:
    return ApiTokenRead.model_validate(record)


def _slug(value: str) -> str:
    return "-".join(value.lower().replace("_", "-").split()) or "provider"


def _iso(value: datetime | None) -> str | None:
    return value.astimezone(UTC).isoformat() if value else None


def _prune_codex_device_flows(now: datetime | None = None) -> None:
    current = now or datetime.now(UTC)
    expired = [flow_id for flow_id, flow in _codex_device_flows.items() if flow.expires_at <= current]
    for flow_id in expired:
        _codex_device_flows.pop(flow_id, None)
    expired_browser = [flow_id for flow_id, flow in _codex_browser_flows.items() if flow.expires_at <= current]
    for flow_id in expired_browser:
        _codex_browser_flows.pop(flow_id, None)


def _format_homepage_number(value: float | int | str | bool | None) -> str:
    if isinstance(value, bool) or value is None:
        return str(value)
    if isinstance(value, int | float):
        if abs(value) >= 1000:
            return f"{value / 1000:.1f}k".rstrip("0").rstrip(".")
        return f"{value:g}"
    return str(value)


def _homepage_usage_text(metrics: list[dict], summary: str | None) -> str:
    labeled_metrics = {
        str(metric.get("label") or "").lower().replace("-", "_").replace(" ", "_"): metric
        for metric in metrics
    }
    usage_percent = labeled_metrics.get("usage_percent")
    credits_remaining = labeled_metrics.get("credits_remaining")
    if usage_percent and credits_remaining:
        usage_value = _format_homepage_number(usage_percent.get("value"))
        remaining_value = _format_homepage_number(credits_remaining.get("value"))
        return f"{usage_value}% • {remaining_value} credits left"

    for metric in metrics:
        label = str(metric.get("label") or "").lower().replace("-", "_").replace(" ", "_")
        if "used" in label:
            continue
        if any(token in label for token in ("remaining", "left", "balance")):
            value = _format_homepage_number(metric.get("value"))
            unit = metric.get("unit") or ("credits" if "credit" in label else None)
            suffix = "%" if unit == "%" else f" {unit}" if unit else ""
            return f"{value}{suffix} left"

    for metric in metrics:
        label = str(metric.get("label") or "").lower().replace("-", "_").replace(" ", "_")
        unit = metric.get("unit")
        if unit == "%" or "percent" in label:
            value = f"{_format_homepage_number(metric.get('value'))}%"
            return f"{value} left" if any(token in label for token in ("remaining", "left")) else value

    return summary or "No usage snapshot yet"


def _homepage_provider_rows(rows: list[dict]) -> list[HomepageProviderRow]:
    provider_rows = []
    for row in rows:
        cfg = row["config"]
        if not cfg.is_enabled:
            continue
        latest = row["latest"]
        last_good = row.get("last_good")
        health = row.get("health") or {}
        status = health.get("status") or (latest.status if latest else "unknown")
        # Health collapses a provider-level "degraded" (successful but partial)
        # into "healthy"; surface the provider's own signal when present.
        if status == "healthy" and latest is not None and latest.status == "degraded":
            status = "degraded"
        display = last_good if last_good is not None else latest
        provider_rows.append(
            HomepageProviderRow(
                provider=cfg.provider,
                config_id=cfg.id,
                label=f"{cfg.provider} ({cfg.label})",
                value=_homepage_usage_text(display.metrics, display.summary) if display else "No usage snapshot yet",
                status=status,
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


@router.get("/auth/status", response_model=AuthStatusRead)
async def get_auth_status(session: AsyncSession = Depends(get_session)):
    return await auth_status(session)


@router.post("/auth/setup", response_model=AuthTokenRead)
async def setup_auth(payload: AuthCodePasswordRequest, session: AsyncSession = Depends(get_session)):
    token, expires_at = await setup_admin_password(payload.code, payload.password, session)
    return AuthTokenRead(access_token=token, expires_at=expires_at)


@router.post("/auth/login", response_model=AuthTokenRead)
async def login_auth(payload: AuthPasswordRequest, session: AsyncSession = Depends(get_session)):
    token, expires_at = await login_admin(payload.password, session)
    return AuthTokenRead(access_token=token, expires_at=expires_at)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: AsyncSession = Depends(get_session),
):
    if credentials is not None and credentials.scheme.lower() == "bearer":
        await revoke_admin_session(credentials.credentials, session)


@router.post("/auth/reset/request", status_code=status.HTTP_202_ACCEPTED)
async def request_auth_reset(session: AsyncSession = Depends(get_session)):
    await request_password_reset(session)
    return {"status": "reset_code_logged"}


@router.post("/auth/reset/complete", response_model=AuthTokenRead)
async def complete_auth_reset(payload: AuthCodePasswordRequest, session: AsyncSession = Depends(get_session)):
    token, expires_at = await reset_admin_password(payload.code, payload.password, session)
    return AuthTokenRead(access_token=token, expires_at=expires_at)


@router.get("/api-tokens", response_model=list[ApiTokenRead], dependencies=[Depends(require_admin_auth)])
async def list_api_tokens(session: AsyncSession = Depends(get_session)):
    rows = (await session.execute(select(ApiToken).order_by(desc(ApiToken.created_at), desc(ApiToken.id)))).scalars().all()
    return [_api_token_read(row) for row in rows]


@router.post("/api-tokens", response_model=ApiTokenCreated, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_admin_auth)])
async def create_api_token(payload: ApiTokenCreate, session: AsyncSession = Depends(get_session)):
    record, token = await create_api_token_record(payload.name, payload.scopes, payload.expires_at, session)
    return ApiTokenCreated(**_api_token_read(record).model_dump(), token=token)


@router.post("/api-tokens/{token_id}/revoke", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_admin_auth)])
async def revoke_api_token(token_id: int, session: AsyncSession = Depends(get_session)):
    if not await revoke_api_token_record(token_id, session):
        raise HTTPException(status_code=404, detail="API token not found")


@router.get("/providers", response_model=list[ProviderInfo])
async def providers() -> list[dict]:
    return list_providers()


@router.get("/configs", response_model=list[ProviderConfigRead], dependencies=[Depends(require_scope("configs:read"))])
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
    config = ProviderConfig(provider=payload.provider, label=label, encrypted_api_key=encrypted, base_url=payload.base_url, extra=payload.extra, is_enabled=payload.is_enabled, is_visible=payload.is_visible, display_order=display_order, alert_thresholds=[rule.model_dump() for rule in payload.alert_thresholds])
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


@router.post("/codex/oauth/device/start", response_model=CodexDeviceStartRead, dependencies=[Depends(require_admin_auth)])
async def start_codex_device_oauth():
    try:
        device = await codex_oauth.start_device_authorization(timeout=settings.request_timeout_seconds)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    flow_id = token_urlsafe(32)
    async with _codex_device_lock:
        _prune_codex_device_flows()
        _codex_device_flows[flow_id] = device
    return codex_oauth.public_device_payload(flow_id, device)


@router.post("/codex/oauth/device/{flow_id}/poll", response_model=CodexDevicePollRead, dependencies=[Depends(require_admin_auth)])
async def poll_codex_device_oauth(flow_id: str, payload: CodexDevicePollRequest | None = None, session: AsyncSession = Depends(get_session)):
    async with _codex_device_lock:
        _prune_codex_device_flows()
        device = _codex_device_flows.get(flow_id)
    if not device:
        raise HTTPException(status_code=404, detail="Codex device authorization flow was not found or expired")
    if device.expires_at <= datetime.now(UTC):
        async with _codex_device_lock:
            _codex_device_flows.pop(flow_id, None)
        return {"status": "expired", "error": "Codex device code expired. Start a new connection.", "interval_seconds": None, "config": None}

    result = await codex_oauth.poll_device_authorization(device.device_code, timeout=settings.request_timeout_seconds)
    if result.get("status") != "completed":
        return {"status": result.get("status", "failed"), "interval_seconds": result.get("interval_seconds"), "error": result.get("error"), "config": None}

    secret = result.get("secret")
    if not isinstance(secret, str) or not secret.strip():
        return {"status": "failed", "error": "Codex device authorization completed without usable tokens", "interval_seconds": None, "config": None}

    label = await _unique_label(session, "codex", payload.label if payload else None)
    display_order = await session.scalar(select(func.max(ProviderConfig.display_order)))
    config = ProviderConfig(
        provider="codex",
        label=label,
        encrypted_api_key=_crypto().encrypt(secret),
        extra={"auth_method": "device_code"},
        is_enabled=True,
        is_visible=True,
        display_order=int(display_order or 0) + 1 if display_order is not None else 0,
    )
    session.add(config)
    await session.commit()
    await session.refresh(config)
    async with _codex_device_lock:
        _codex_device_flows.pop(flow_id, None)
    return {"status": "completed", "interval_seconds": None, "error": None, "config": _config_read(config)}


@router.post("/codex/oauth/browser/start", response_model=CodexBrowserStartRead, dependencies=[Depends(require_admin_auth)])
async def start_codex_browser_oauth():
    browser = codex_oauth.start_browser_authorization()
    flow_id = token_urlsafe(32)
    async with _codex_device_lock:
        _prune_codex_device_flows()
        _codex_browser_flows[flow_id] = browser
    return codex_oauth.public_browser_payload(flow_id, browser)


@router.post("/codex/oauth/browser/{flow_id}/complete", response_model=CodexBrowserCompleteRead, dependencies=[Depends(require_admin_auth)])
async def complete_codex_browser_oauth(flow_id: str, payload: CodexBrowserCompleteRequest, session: AsyncSession = Depends(get_session)):
    async with _codex_device_lock:
        _prune_codex_device_flows()
        browser = _codex_browser_flows.get(flow_id)
    if not browser:
        raise HTTPException(status_code=404, detail="Codex browser authorization flow was not found or expired")
    if browser.expires_at <= datetime.now(UTC):
        async with _codex_device_lock:
            _codex_browser_flows.pop(flow_id, None)
        return {"status": "expired", "error": "Codex browser login expired. Start a new connection.", "config": None}
    try:
        code = codex_oauth.authorization_code_from_callback(payload.callback, expected_state=browser.state)
        secret = await codex_oauth.exchange_browser_authorization_code(code, browser.code_verifier, timeout=settings.request_timeout_seconds)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    label = await _unique_label(session, "codex", payload.label)
    display_order = await session.scalar(select(func.max(ProviderConfig.display_order)))
    config = ProviderConfig(
        provider="codex",
        label=label,
        encrypted_api_key=_crypto().encrypt(secret),
        extra={"auth_method": "browser_pkce"},
        is_enabled=True,
        is_visible=True,
        display_order=int(display_order or 0) + 1 if display_order is not None else 0,
    )
    session.add(config)
    await session.commit()
    await session.refresh(config)
    async with _codex_device_lock:
        _codex_browser_flows.pop(flow_id, None)
    return {"status": "completed", "error": None, "config": _config_read(config)}


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
    if payload.has_update_for("alert_thresholds") and payload.alert_thresholds is not None:
        config.alert_thresholds = [rule.model_dump() for rule in payload.alert_thresholds]
    await session.commit()
    await session.refresh(config)
    return _config_read(config)


@router.delete("/configs/{config_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_admin_auth)])
async def delete_config(config_id: int, session: AsyncSession = Depends(get_session)):
    result = await session.execute(delete(ProviderConfig).where(ProviderConfig.id == config_id))
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Provider config not found")
    await session.commit()


@router.get("/configs/{config_id}/history", response_model=list[UsageSnapshotRead], dependencies=[Depends(require_scope("history:read"))])
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


async def _snapshot_for_config(config: ProviderConfig) -> tuple[UsageSnapshot, list[dict]]:
    try:
        adapter_cls = get_adapter_class(config.provider)
        crypto = _crypto()
        adapter = adapter_cls(crypto.decrypt(config.encrypted_api_key), base_url=config.base_url, timeout=settings.request_timeout_seconds, extra=config.extra)
        usage = await adapter.fetch_usage()
        updated_secret = getattr(adapter, "updated_secret", None)
        if updated_secret:
            config.encrypted_api_key = crypto.encrypt(updated_secret)
        snapshot = UsageSnapshot(provider_config_id=config.id, provider=config.provider, status=usage.status, summary=usage.summary, metrics=[asdict(metric) for metric in usage.metrics], raw=usage.raw, error=None)
        native = adapter.native_observations(usage.raw)
    except Exception as exc:
        snapshot = UsageSnapshot(provider_config_id=config.id, provider=config.provider, status="error", summary=f"{config.label}: polling failed", metrics=[], raw={}, error=str(exc))
        native = []
    return snapshot, native


def _as_utc(value):
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _observation_row(config: ProviderConfig, obs) -> UsageObservation:
    return UsageObservation(
        provider_config_id=config.id,
        provider=config.provider,
        metric=obs.metric,
        value=obs.value,
        unit=obs.unit,
        kind=obs.kind,
        source=obs.source,
        observed_at=obs.observed_at,
        window_start=obs.window_start,
        window_end=obs.window_end,
        reset_at=obs.reset_at,
    )


def _observation_key(obs) -> tuple:
    """A stable identity for an observation, independent of naive/aware tz mixing."""
    return (
        obs.metric,
        _as_utc(getattr(obs, "window_start", None)),
        _as_utc(getattr(obs, "window_end", None)),
        _as_utc(obs.observed_at),
    )


async def _ingest_observations(session: AsyncSession, config: ProviderConfig, snapshot: UsageSnapshot, native: list[dict]) -> None:
    """Derive and persist normalized observations for a freshly polled snapshot."""
    capabilities = get_adapter_class(config.provider).analytics or {}
    if snapshot.status != "error" and snapshot.metrics:
        recent = (
            await session.execute(
                select(UsageSnapshot)
                .where(UsageSnapshot.provider_config_id == config.id, UsageSnapshot.id < snapshot.id)
                .order_by(desc(UsageSnapshot.id))
                .limit(3)
            )
        ).scalars().all()
        previous = next((row for row in recent if row.metrics), None)
        history = []
        if previous is not None:
            history.append({"checked_at": previous.checked_at, "metrics": previous.metrics})
        history.append({"checked_at": snapshot.checked_at, "metrics": snapshot.metrics})
        observations = normalize_snapshots(history, capabilities=capabilities)
        for obs in observations:
            if obs.observed_at != snapshot.checked_at:
                continue
            session.add(_observation_row(config, obs))
    if native:
        # Upsert native history rather than delete-and-reinsert. Providers return
        # a rolling window (Anthropic 24h, OpenAI 30d), so wiping the dataset each
        # poll would cap retained native history at that window.
        native_obs = normalize_native(native)
        if native_obs:
            lower = min(obs.observed_at for obs in native_obs)
            upper = max(obs.observed_at for obs in native_obs)
            existing = (
                await session.execute(
                    select(UsageObservation).where(
                        UsageObservation.provider_config_id == config.id,
                        UsageObservation.source == "native",
                        UsageObservation.observed_at >= lower,
                        UsageObservation.observed_at <= upper,
                    )
                )
            ).scalars().all()
            by_key = {_observation_key(row): row for row in existing}
            for obs in native_obs:
                row = by_key.get(_observation_key(obs))
                if row is not None:
                    row.value = obs.value
                    row.unit = obs.unit
                    row.kind = obs.kind
                    row.reset_at = obs.reset_at
                else:
                    session.add(_observation_row(config, obs))
    await session.commit()


async def _prune_old_observations(session: AsyncSession) -> None:
    if settings.analytics_hourly_retention_days < 0:
        return
    cutoff = datetime.now(UTC) - timedelta(days=settings.analytics_hourly_retention_days)
    await session.execute(delete(UsageObservation).where(UsageObservation.observed_at < cutoff))
    await session.commit()


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
    results = await asyncio.gather(*(_snapshot_for_config(config) for config in configs)) if configs else []
    snapshots = [result[0] for result in results]
    if snapshots:
        session.add_all(snapshots)
        await session.commit()
        for snapshot in snapshots:
            await session.refresh(snapshot)
        for config, (snapshot, native) in zip(configs, results):
            await _ingest_observations(session, config, snapshot, native)
        await _prune_old_snapshots(session)
        await _prune_old_observations(session)
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


@router.post("/configs/{config_id}/poll", response_model=UsageSnapshotRead, dependencies=[Depends(require_scope("poll:write"))])
async def poll_config(config_id: int, session: AsyncSession = Depends(get_session)):
    config = await session.get(ProviderConfig, config_id)
    if not config:
        raise HTTPException(status_code=404, detail="Provider config not found")
    if not config.is_enabled:
        raise HTTPException(status_code=409, detail="Provider config is disabled")
    return await _poll_one(config, session)


async def _poll_one(config: ProviderConfig, session: AsyncSession) -> UsageSnapshot:
    snapshot, native = await _snapshot_for_config(config)
    session.add(snapshot)
    await session.commit()
    await session.refresh(snapshot)
    await _ingest_observations(session, config, snapshot, native)
    await _prune_old_snapshots(session)
    await _prune_old_observations(session)
    return snapshot


@router.post("/poll", response_model=list[UsageSnapshotRead], dependencies=[Depends(require_scope("poll:write"))])
async def poll_all(session: AsyncSession = Depends(get_session)):
    async with _auto_poll_lock:
        return await _poll_enabled_configs(session)


@router.get("/poll/status", response_model=PollStatusRead, dependencies=[Depends(require_scope("poll:write"))])
async def poll_status():
    return PollStatusRead(
        auto_poll_enabled=settings.auto_poll_enabled,
        interval_seconds=settings.auto_poll_interval_minutes * 60,
        is_polling=_auto_poll_lock.locked(),
        last_polled_at=_iso(_last_auto_polled_at),
        next_poll_at=_iso(_next_auto_poll_at),
    )


async def _health_for_config(session: AsyncSession, config: ProviderConfig) -> tuple[UsageSnapshot | None, dict, UsageSnapshot | None]:
    """Derive ``(latest, health, last_good)`` for a config using targeted queries.

    No bounded scan window: the latest snapshot, last success, last failure, and
    failure count are each located with their own query, so a long run of
    failures can never hide an older successful snapshot.
    """
    latest = (await session.execute(
        select(UsageSnapshot)
        .where(UsageSnapshot.provider_config_id == config.id)
        .order_by(desc(UsageSnapshot.checked_at), desc(UsageSnapshot.id))
        .limit(1)
    )).scalar_one_or_none()

    last_success = (await session.execute(
        select(UsageSnapshot)
        .where(UsageSnapshot.provider_config_id == config.id, UsageSnapshot.status != "error")
        .order_by(desc(UsageSnapshot.checked_at), desc(UsageSnapshot.id))
        .limit(1)
    )).scalar_one_or_none()

    last_failure = (await session.execute(
        select(UsageSnapshot)
        .where(UsageSnapshot.provider_config_id == config.id, UsageSnapshot.status == "error")
        .order_by(desc(UsageSnapshot.checked_at), desc(UsageSnapshot.id))
        .limit(1)
    )).scalar_one_or_none()

    last_success_at = last_success.checked_at if last_success is not None else None
    if last_success_at is not None:
        consecutive = (await session.execute(
            select(func.count(UsageSnapshot.id)).where(
                UsageSnapshot.provider_config_id == config.id,
                UsageSnapshot.status == "error",
                UsageSnapshot.checked_at > last_success_at,
            )
        )).scalar_one()
    else:
        consecutive = (await session.execute(
            select(func.count(UsageSnapshot.id)).where(
                UsageSnapshot.provider_config_id == config.id,
                UsageSnapshot.status == "error",
            )
        )).scalar_one()

    health = derive_health(
        latest_status=latest.status if latest is not None else None,
        last_attempt_at=latest.checked_at if latest is not None else None,
        last_success_at=last_success_at,
        last_failure_at=last_failure.checked_at if last_failure is not None else None,
        consecutive_failures=int(consecutive or 0),
        latest_error=last_failure.error if last_failure is not None else None,
        now=datetime.now(UTC),
        max_stale_age=default_max_stale_age(settings.auto_poll_interval_minutes),
    )

    # Preserve last-known-good only while it is still within policy (stale).
    # When the last success is too old to be useful (error) we surface the
    # failure instead of presenting stale values as current.
    last_good = last_success if health["status"] == "stale" else None
    return latest, health, last_good


@router.get("/usage", response_model=list[DashboardConfigUsage], dependencies=[Depends(require_scope("usage:read"))])
async def usage(session: AsyncSession = Depends(get_session)):
    configs = (await session.execute(select(ProviderConfig).order_by(*_config_ordering()))).scalars().all()
    payload = []
    for config in configs:
        latest, health, last_good = await _health_for_config(session, config)
        alert_source = last_good if last_good is not None else latest
        alerts = build_alerts(alert_source.metrics if alert_source else [], config.alert_thresholds) if alert_source else []
        payload.append(
            {
                "config": _config_read(config),
                "latest": latest,
                "last_good": last_good,
                "health": health,
                "alerts": [AlertStateRead(**alert) for alert in alerts],
                "alert_state": provider_alert_state(alerts),
            }
        )
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
