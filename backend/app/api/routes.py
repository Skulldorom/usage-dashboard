import asyncio
import errno
import html
import logging
import threading
from dataclasses import asdict, dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
from datetime import UTC, datetime, timedelta
from secrets import token_urlsafe

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import and_, asc, delete, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.analytics.normalizer import normalize_native, normalize_snapshots, parse_time
from app.core.auth import (
    auth_status,
    bearer_scheme,
    create_api_token_record,
    homepage_auth,
    login_admin,
    request_password_reset,
    require_admin_auth,
    require_scope,
    reset_admin_password,
    revoke_admin_session,
    revoke_api_token_record,
    setup_admin_password,
)
from app.core.config import settings
from app.core.crypto import CryptoError, CryptoService
from app.core.thresholds import build_alerts, provider_alert_state
from app.database import engine, get_session
from app.health import default_max_stale_age, derive_health
from app.models import (
    ApiToken,
    OpenRouterAnalyticsState,
    OpenRouterAnalyticsWindow,
    ProviderConfig,
    UsageObservation,
    UsageSnapshot,
)
from app.providers import codex_oauth
from app.providers.errors import classify_exception, log_provider_failure
from app.providers.registry import get_adapter_class, list_providers
from app.schemas import (
    AlertStateRead,
    ApiTokenCreate,
    ApiTokenCreated,
    ApiTokenRead,
    AuthCodePasswordRequest,
    AuthPasswordRequest,
    AuthStatusRead,
    AuthTokenRead,
    BILLING_CADENCES,
    CodexBrowserCompleteRead,
    CodexBrowserCompleteRequest,
    CodexBrowserStartRead,
    CodexBrowserStatusRead,
    CodexDevicePollRead,
    CodexDevicePollRequest,
    CodexDeviceStartRead,
    DashboardConfigUsage,
    HomepagePayload,
    HomepageProviderRow,
    PollStatusRead,
    PRICING_MODELS,
    ProviderConfigCreate,
    ProviderConfigOrderUpdate,
    ProviderConfigRead,
    ProviderConfigUpdate,
    ProviderInfo,
    ProviderUsageRead,
    UsageSnapshotRead,
)

router = APIRouter()
_auto_poll_lock = asyncio.Lock()
_auto_poll_task: asyncio.Task | None = None
_last_auto_polled_at: datetime | None = None
_next_auto_poll_at: datetime | None = None
_codex_device_flows: dict[str, codex_oauth.CodexDeviceStart] = {}


@dataclass(slots=True)
class CodexBrowserFlowState:
    browser: codex_oauth.CodexBrowserStart
    status: str = "pending"
    error: str | None = None
    config_id_result: int | None = None
    label_result: str | None = None
    label: str | None = None
    config_id: int | None = None
    completed_at: datetime | None = None

    @property
    def state(self) -> str:
        return self.browser.state

    @property
    def code_verifier(self) -> str:
        return self.browser.code_verifier

    @property
    def expires_at(self) -> datetime:
        return self.browser.expires_at


_codex_browser_flows: dict[str, CodexBrowserFlowState] = {}
_initial_poll_tasks: set[asyncio.Task] = set()
_logger = logging.getLogger(__name__)
_codex_browser_listener: ThreadingHTTPServer | None = None
_codex_browser_listener_thread: threading.Thread | None = None
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
    expired_browser = []
    for flow_id, flow in _codex_browser_flows.items():
        if flow.status == "pending" and flow.browser.expires_at <= current:
            flow.status = "expired"
            flow.error = "Codex browser login expired. Start a new connection."
            flow.completed_at = current
        if (
            flow.status in {"completed", "failed", "expired"}
            and (flow.completed_at or flow.browser.expires_at) + timedelta(minutes=2) <= current
        ):
            expired_browser.append(flow_id)
    for flow_id in expired_browser:
        _codex_browser_flows.pop(flow_id, None)
    if not any(flow.status in {"pending", "processing"} for flow in _codex_browser_flows.values()):
        _stop_codex_browser_listener()


def _codex_browser_result_page(success: bool, message: str) -> str:
    title = "Codex connected" if success else "Codex authorization failed"
    color = "#16a34a" if success else "#dc2626"
    safe_message = html.escape(message, quote=True)
    mark = "✓" if success else "✕"
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>{title}</title><style>body{{font-family:system-ui,sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;background:#f6f7f9}}.card{{max-width:460px;padding:32px;border-radius:12px;background:white;box-shadow:0 8px 32px #0002;text-align:center}}.mark{{font-size:44px;color:{color}}}p{{color:#4b5563}}</style></head><body><main class="card"><div class="mark">{mark}</div><h1>{title}</h1><p>{safe_message}</p><p>This window will close automatically if your browser allows it.</p></main><script>setTimeout(() => window.close(), 1800);</script></body></html>"""


def _safe_browser_error(exc: Exception) -> str:
    message = str(exc).lower()
    if "expired" in message:
        return "Codex authorization expired."
    if "access_denied" in message or "denied" in message or "rejected" in message:
        return "OpenAI rejected the authorization request."
    return "Unable to exchange the Codex authorization code."


def _browser_status_payload(flow: CodexBrowserFlowState) -> dict[str, object]:
    return {"status": flow.status, "error": flow.error, "config_id": flow.config_id_result, "label": flow.label_result}


async def _claim_codex_browser_flow(
    flow_id: str | None, callback: str, *, allow_failed_retry: bool = False
) -> tuple[str | None, CodexBrowserFlowState | None, str | None, str | None]:
    async with _codex_device_lock:
        _prune_codex_device_flows()
        candidates = [(fid, flow) for fid, flow in _codex_browser_flows.items() if flow_id is None or fid == flow_id]
        matched_by_id = _codex_browser_flows.get(flow_id) if flow_id else None
        for candidate_id, flow in candidates:
            try:
                code = codex_oauth.authorization_code_from_callback(callback, expected_state=flow.browser.state)
            except Exception:
                continue
            if flow.status != "pending" and not (allow_failed_retry and flow.status == "failed"):
                return (
                    None,
                    flow,
                    None,
                    "This Codex authorization flow is already being processed or has finished. Start a new login if needed.",
                )
            if flow.browser.expires_at <= datetime.now(UTC):
                flow.status = "expired"
                flow.error = "Codex authorization expired."
                flow.completed_at = datetime.now(UTC)
                return None, flow, None, flow.error
            flow.status = "processing"
            return candidate_id, flow, code, None
        return None, matched_by_id, None, "Codex authorization failed."


async def _finish_codex_browser_flow(
    flow_id: str, flow: CodexBrowserFlowState, code: str, session: AsyncSession | None = None
) -> tuple[bool, str, ProviderConfigRead | None]:
    try:
        secret = await codex_oauth.exchange_browser_authorization_code(
            code, flow.browser.code_verifier, timeout=settings.request_timeout_seconds
        )
        if session is None:
            session_factory = async_sessionmaker(engine, expire_on_commit=False)
            async with session_factory() as local_session:
                config = await _save_codex_secret(
                    local_session, secret, auth_method="browser_pkce", label=flow.label, config_id=flow.config_id
                )
                config_read = _config_read(config)
        else:
            config = await _save_codex_secret(
                session, secret, auth_method="browser_pkce", label=flow.label, config_id=flow.config_id
            )
            config_read = _config_read(config)
        async with _codex_device_lock:
            current = _codex_browser_flows.get(flow_id)
            if current and current.status == "processing":
                current.status = "completed"
                current.config_id_result = config_read.id
                current.label_result = config_read.label
                current.completed_at = datetime.now(UTC)
        return True, "Codex connected successfully. You can close this window.", config_read
    except Exception as exc:
        message = _safe_browser_error(exc)
        async with _codex_device_lock:
            current = _codex_browser_flows.get(flow_id)
            if current and current.status == "processing":
                current.status = "failed"
                current.error = message
                current.completed_at = datetime.now(UTC)
        return False, message, None
    finally:
        async with _codex_device_lock:
            if not any(item.status in {"pending", "processing"} for item in _codex_browser_flows.values()):
                _stop_codex_browser_listener()


async def _complete_codex_browser_callback(state: str | None, callback_url: str) -> tuple[bool, str]:
    if state:
        try:
            codex_oauth.authorization_code_from_callback(callback_url, expected_state=state)
        except Exception:
            return False, "Codex authorization failed."
    flow_id, flow, code, error = await _claim_codex_browser_flow(None, callback_url)
    if not flow_id or not flow or not code:
        return False, error or "Codex authorization failed."
    ok, message, _ = await _finish_codex_browser_flow(flow_id, flow, code)
    return ok, message


def _start_codex_browser_listener(loop: asyncio.AbstractEventLoop) -> tuple[bool, str | None]:
    global _codex_browser_listener, _codex_browser_listener_thread
    if _codex_browser_listener:
        return True, None

    class CodexCallbackHandler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            return

        def do_GET(self):
            parsed = urlparse(self.path)
            if parsed.path != "/auth/callback":
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b"Not found")
                return
            origin = self.headers.get("Origin")
            if origin and not origin.startswith(("http://localhost", "http://127.0.0.1")):
                self.send_response(403)
                self.end_headers()
                self.wfile.write(b"Forbidden")
                return
            state = parse_qs(parsed.query, keep_blank_values=False).get("state", [None])[0]
            future = asyncio.run_coroutine_threadsafe(
                _complete_codex_browser_callback(state, f"http://localhost:1455{self.path}"), loop
            )
            try:
                success, message = future.result(timeout=settings.request_timeout_seconds + 5)
            except Exception:
                success, message = (
                    False,
                    "Codex authorization failed. Return to Usage Dashboard and use manual callback fallback.",
                )
            body = _codex_browser_result_page(success, message).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    try:
        server = ThreadingHTTPServer(("127.0.0.1", 1455), CodexCallbackHandler)
    except OSError as exc:
        return False, "port_busy" if getattr(exc, "errno", None) == errno.EADDRINUSE else "listener_unavailable"
    _codex_browser_listener = server
    _codex_browser_listener_thread = threading.Thread(
        target=server.serve_forever, name="codex-oauth-callback", daemon=True
    )
    _codex_browser_listener_thread.start()
    return True, None


def _stop_codex_browser_listener() -> None:
    global _codex_browser_listener, _codex_browser_listener_thread
    server = _codex_browser_listener
    if not server:
        return
    _codex_browser_listener = None
    _codex_browser_listener_thread = None
    threading.Thread(target=server.shutdown, daemon=True).start()


def _format_homepage_number(value: float | int | str | bool | None) -> str:
    if isinstance(value, bool) or value is None:
        return str(value)
    if isinstance(value, int | float):
        if abs(value) >= 1000:
            return f"{value / 1000:.1f}k".rstrip("0").rstrip(".")
        return f"{value:g}"
    return str(value)


def _homepage_usage_text(metrics: list[dict], summary: str | None, provider: str | None = None) -> str:
    labeled_metrics = {
        str(metric.get("label") or "").lower().replace("-", "_").replace(" ", "_"): metric for metric in metrics
    }

    quota_windows = {
        "codex": (
            ("Session", "session_remaining_percent"),
            ("Weekly", "weekly_remaining_percent"),
        ),
        "opencode-go": (
            ("Session", "five_hour_remaining_percent"),
            ("Weekly", "weekly_remaining_percent"),
            ("Monthly", "monthly_remaining_percent"),
        ),
        "minimax": (
            ("Session/5h", "five_hour_remaining_percent"),
            ("Weekly", "weekly_remaining_percent"),
        ),
    }.get(provider, ())
    window_parts = [
        f"{title} {_format_homepage_number(labeled_metrics[metric_name].get('value'))}%"
        for title, metric_name in quota_windows
        if metric_name in labeled_metrics and labeled_metrics[metric_name].get("value") is not None
    ]
    if window_parts:
        return " • ".join(window_parts)

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


def _provider_display_name(provider: str) -> str:
    try:
        return get_adapter_class(provider).name
    except ValueError:
        return provider.replace("_", " ").replace("-", " ").title() or "Provider"


def _homepage_provider_rows(rows: list[dict]) -> list[HomepageProviderRow]:
    provider_rows = []
    provider_counts = {
        provider: sum(row["config"].provider == provider and row["config"].is_enabled for row in rows)
        for provider in {row["config"].provider for row in rows if row["config"].is_enabled}
    }
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
        provider_name = _provider_display_name(cfg.provider)
        provider_rows.append(
            HomepageProviderRow(
                provider=cfg.provider,
                config_id=cfg.id,
                label=(provider_name if provider_counts[cfg.provider] == 1 else f"{provider_name} ({cfg.label})"),
                value=(
                    _homepage_usage_text(display.metrics, display.summary, cfg.provider)
                    if display
                    else "No usage snapshot yet"
                ),
                status=status,
            )
        )
    return provider_rows


async def _unique_label(session: AsyncSession, provider: str, requested: str | None) -> str:
    base = (requested or "main").strip() or "main"
    existing = set(
        (await session.execute(select(ProviderConfig.label).where(ProviderConfig.provider == provider))).scalars().all()
    )
    if base not in existing:
        return base
    provider_slug = _slug(provider)
    index = 2
    while f"{provider_slug}-{index}" in existing:
        index += 1
    return f"{provider_slug}-{index}"


async def _save_codex_secret(
    session: AsyncSession,
    secret: str,
    *,
    auth_method: str,
    label: str | None = None,
    config_id: int | None = None,
) -> ProviderConfig:
    encrypted = _crypto().encrypt(secret)
    if config_id is not None:
        config = await session.get(ProviderConfig, config_id)
        if not config or config.provider != "codex":
            raise HTTPException(status_code=404, detail="Codex provider config not found")
        config.encrypted_api_key = encrypted
        config.extra = {**(config.extra or {}), "auth_method": auth_method}
        await session.commit()
        await session.refresh(config)
        return config

    unique_label = await _unique_label(session, "codex", label)
    display_order = await session.scalar(select(func.max(ProviderConfig.display_order)))
    config = ProviderConfig(
        provider="codex",
        label=unique_label,
        encrypted_api_key=encrypted,
        extra={"auth_method": auth_method},
        is_enabled=True,
        is_visible=True,
        display_order=int(display_order or 0) + 1 if display_order is not None else 0,
    )
    session.add(config)
    await session.commit()
    await session.refresh(config)
    return config


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
    rows = (
        (await session.execute(select(ApiToken).order_by(desc(ApiToken.created_at), desc(ApiToken.id)))).scalars().all()
    )
    return [_api_token_read(row) for row in rows]


@router.post(
    "/api-tokens",
    response_model=ApiTokenCreated,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin_auth)],
)
async def create_api_token(payload: ApiTokenCreate, session: AsyncSession = Depends(get_session)):
    record, token = await create_api_token_record(payload.name, payload.scopes, payload.expires_at, session)
    return ApiTokenCreated(**_api_token_read(record).model_dump(), token=token)


@router.post(
    "/api-tokens/{token_id}/revoke", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_admin_auth)]
)
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


async def _poll_new_config(config_id: int) -> None:
    """Poll a new config once, unless another poll already populated it."""
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with _auto_poll_lock:
        async with Session() as session:
            config = await session.get(ProviderConfig, config_id)
            if not config or not config.is_enabled:
                return
            has_snapshot = await session.scalar(
                select(UsageSnapshot.id)
                .where(
                    UsageSnapshot.provider_config_id == config.id,
                    UsageSnapshot.config_revision == config.usage_revision,
                )
                .limit(1)
            )
            if has_snapshot is not None:
                return
            await _poll_one(config, session)


def _initial_poll_done(task: asyncio.Task) -> None:
    _initial_poll_tasks.discard(task)
    if task.cancelled():
        return
    try:
        task.result()
    except HTTPException as exc:
        if exc.status_code != 409:
            _logger.warning("Initial provider poll failed: status=%s", exc.status_code)
    except Exception as exc:
        _logger.error("Unexpected initial provider poll failure: type=%s", type(exc).__name__)


def _schedule_initial_poll(config_id: int) -> None:
    task = asyncio.create_task(_poll_new_config(config_id))
    _initial_poll_tasks.add(task)
    task.add_done_callback(_initial_poll_done)


async def stop_initial_polls() -> None:
    tasks = tuple(_initial_poll_tasks)
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    _initial_poll_tasks.clear()


async def wait_initial_polls() -> None:
    """Wait for currently scheduled initial polls without cancelling them."""
    while _initial_poll_tasks:
        await asyncio.gather(*tuple(_initial_poll_tasks), return_exceptions=True)


@router.post(
    "/configs",
    response_model=ProviderConfigRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin_auth)],
)
async def create_config(payload: ProviderConfigCreate, session: AsyncSession = Depends(get_session)):
    _validate_openrouter_config(payload.provider, payload.base_url, payload.extra)
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
    config = ProviderConfig(
        provider=payload.provider,
        label=label,
        encrypted_api_key=encrypted,
        base_url=payload.base_url,
        extra=payload.extra,
        is_enabled=payload.is_enabled,
        is_visible=payload.is_visible,
        display_order=display_order,
        alert_thresholds=[rule.model_dump() for rule in payload.alert_thresholds],
        pricing_model=payload.pricing_model,
        subscription_amount=payload.subscription_amount,
        subscription_currency=payload.subscription_currency,
        billing_cadence=payload.billing_cadence,
        billing_anchor=payload.billing_anchor,
    )
    _validate_openrouter_config(config.provider, config.base_url, config.extra)
    _normalize_and_validate_billing(config)
    session.add(config)
    try:
        await session.commit()
    except Exception as exc:
        await session.rollback()
        raise HTTPException(
            status_code=409, detail="Provider label already exists or database rejected the config"
        ) from exc
    await session.refresh(config)
    if config.is_enabled:
        _schedule_initial_poll(config.id)
    return _config_read(config)


@router.post("/configs/test", response_model=ProviderUsageRead, dependencies=[Depends(require_admin_auth)])
async def test_config(payload: ProviderConfigCreate):
    try:
        adapter_cls = get_adapter_class(payload.provider)
        adapter = adapter_cls(
            payload.api_key, base_url=payload.base_url, timeout=settings.request_timeout_seconds, extra=payload.extra
        )
        usage = await adapter.fetch_usage()
    except Exception as exc:
        detail = "Provider connection test failed" if payload.provider == "openrouter" else str(exc)
        raise HTTPException(status_code=400, detail=detail) from None
    return {
        "status": usage.status,
        "summary": usage.summary,
        "metrics": [asdict(metric) for metric in usage.metrics],
        "raw": usage.raw,
    }


@router.post(
    "/codex/oauth/device/start", response_model=CodexDeviceStartRead, dependencies=[Depends(require_admin_auth)]
)
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


@router.post(
    "/codex/oauth/device/{flow_id}/poll", response_model=CodexDevicePollRead, dependencies=[Depends(require_admin_auth)]
)
async def poll_codex_device_oauth(
    flow_id: str, payload: CodexDevicePollRequest | None = None, session: AsyncSession = Depends(get_session)
):
    async with _codex_device_lock:
        _prune_codex_device_flows()
        device = _codex_device_flows.get(flow_id)
    if not device:
        raise HTTPException(status_code=404, detail="Codex device authorization flow was not found or expired")
    if device.expires_at <= datetime.now(UTC):
        async with _codex_device_lock:
            _codex_device_flows.pop(flow_id, None)
        return {
            "status": "expired",
            "error": "Codex device code expired. Start a new connection.",
            "interval_seconds": None,
            "config": None,
        }

    result = await codex_oauth.poll_device_authorization(device.device_code, timeout=settings.request_timeout_seconds)
    if result.get("status") != "completed":
        return {
            "status": result.get("status", "failed"),
            "interval_seconds": result.get("interval_seconds"),
            "error": result.get("error"),
            "config": None,
        }

    secret = result.get("secret")
    if not isinstance(secret, str) or not secret.strip():
        return {
            "status": "failed",
            "error": "Codex device authorization completed without usable tokens",
            "interval_seconds": None,
            "config": None,
        }

    config = await _save_codex_secret(
        session,
        secret,
        auth_method="device_code",
        label=payload.label if payload else None,
        config_id=payload.config_id if payload else None,
    )
    async with _codex_device_lock:
        _codex_device_flows.pop(flow_id, None)
    return {"status": "completed", "interval_seconds": None, "error": None, "config": _config_read(config)}


@router.post(
    "/codex/oauth/browser/start", response_model=CodexBrowserStartRead, dependencies=[Depends(require_admin_auth)]
)
async def start_codex_browser_oauth(payload: CodexDevicePollRequest | None = None):
    browser = codex_oauth.start_browser_authorization()
    flow_id = token_urlsafe(32)
    if settings.codex_browser_oauth_auto_capture_enabled:
        listener_started, fallback_reason = _start_codex_browser_listener(asyncio.get_running_loop())
    else:
        listener_started, fallback_reason = False, "auto_capture_not_enabled"
    async with _codex_device_lock:
        _prune_codex_device_flows()
        _codex_browser_flows[flow_id] = CodexBrowserFlowState(
            browser=browser, label=payload.label if payload else None, config_id=payload.config_id if payload else None
        )
    data = codex_oauth.public_browser_payload(flow_id, browser)
    data["callback_available"] = listener_started
    data["fallback_reason"] = fallback_reason
    return data


@router.post(
    "/codex/oauth/browser/{flow_id}/complete",
    response_model=CodexBrowserCompleteRead,
    dependencies=[Depends(require_admin_auth)],
)
async def complete_codex_browser_oauth(
    flow_id: str, payload: CodexBrowserCompleteRequest, session: AsyncSession = Depends(get_session)
):
    claimed_id, flow, code, error = await _claim_codex_browser_flow(flow_id, payload.callback, allow_failed_retry=True)
    if not flow:
        raise HTTPException(status_code=404, detail="Codex browser authorization flow was not found or expired")
    if not claimed_id or not code:
        return {"status": flow.status, "error": error or flow.error, "config": None}
    ok, message, config = await _finish_codex_browser_flow(claimed_id, flow, code, session)
    if not ok:
        raise HTTPException(status_code=400, detail=message)
    return {"status": "completed", "error": None, "config": config}


@router.get(
    "/codex/oauth/browser/{flow_id}/status",
    response_model=CodexBrowserStatusRead,
    dependencies=[Depends(require_admin_auth)],
)
async def codex_browser_oauth_status(flow_id: str):
    async with _codex_device_lock:
        _prune_codex_device_flows()
        flow = _codex_browser_flows.get(flow_id)
        if not flow:
            return {"status": "expired", "error": "Codex authorization expired.", "config_id": None, "label": None}
        if flow.status == "pending" and flow.browser.expires_at <= datetime.now(UTC):
            flow.status = "expired"
            flow.error = "Codex authorization expired."
            flow.completed_at = datetime.now(UTC)
        return _browser_status_payload(flow)


@router.patch("/configs/order", response_model=list[ProviderConfigRead], dependencies=[Depends(require_admin_auth)])
async def reorder_configs(payload: ProviderConfigOrderUpdate, session: AsyncSession = Depends(get_session)):
    existing = (
        (await session.execute(select(ProviderConfig).where(ProviderConfig.id.in_(payload.config_ids)))).scalars().all()
    )
    by_id = {config.id: config for config in existing}
    missing = [config_id for config_id in payload.config_ids if config_id not in by_id]
    if missing:
        raise HTTPException(status_code=404, detail=f"Provider config not found: {missing[0]}")
    for index, config_id in enumerate(payload.config_ids):
        by_id[config_id].display_order = index
    await session.commit()
    rows = (await session.execute(select(ProviderConfig).order_by(*_config_ordering()))).scalars().all()
    return [_config_read(row) for row in rows]


def _validate_openrouter_config(provider: str, base_url: str | None, extra: dict | None) -> None:
    if provider != "openrouter":
        return
    from app.providers.openrouter import OpenRouterAdapter

    try:
        OpenRouterAdapter.validate_config(base_url, extra)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _normalize_and_validate_billing(config: ProviderConfig) -> None:
    """Validate the *resulting persisted* billing combination, not just the PATCH.

    A partial PATCH can leave a persisted state that is invalid on its own (e.g.
    subscription without a cadence, or a stale anchor left behind after switching
    to payg). This normalizes currency/model and enforces the invariants on the
    final merged row, clearing subscription-only fields when they no longer apply.
    """
    model = (config.pricing_model or "payg").strip().lower()
    if model not in PRICING_MODELS:
        raise HTTPException(status_code=422, detail=f"Unsupported pricing model: {config.pricing_model}")
    config.pricing_model = model

    currency = (config.subscription_currency or "USD").strip().upper()
    if len(currency) != 3 or not currency.isalpha():
        raise HTTPException(status_code=422, detail=f"Invalid subscription currency: {currency!r}")
    config.subscription_currency = currency

    if model == "subscription":
        if config.subscription_amount is None:
            raise HTTPException(status_code=422, detail="subscription_amount is required for subscription pricing")
        if config.subscription_amount < 0:
            raise HTTPException(status_code=422, detail="subscription_amount cannot be negative")
        cadence = (config.billing_cadence or "").strip().lower()
        if not cadence:
            raise HTTPException(status_code=422, detail="billing_cadence is required for subscription pricing")
        if cadence not in BILLING_CADENCES:
            raise HTTPException(status_code=422, detail=f"Unsupported billing cadence: {config.billing_cadence}")
        config.billing_cadence = cadence
    else:
        # payg/free: subscription-only fields are cleared so stale cadence/anchor/
        # amount never linger in an inconsistent persisted combination.
        config.subscription_amount = None
        config.billing_cadence = None
        config.billing_anchor = None


@router.patch("/configs/{config_id}", response_model=ProviderConfigRead, dependencies=[Depends(require_admin_auth)])
async def update_config(config_id: int, payload: ProviderConfigUpdate, session: AsyncSession = Depends(get_session)):
    config = await session.get(ProviderConfig, config_id)
    if not config:
        raise HTTPException(status_code=404, detail="Provider config not found")
    old_key = _crypto().decrypt(config.encrypted_api_key)
    old_base_url = config.base_url
    old_extra = dict(config.extra or {})
    if config.provider == "openrouter" and payload.has_update_for("extra"):
        current_mode = (config.extra or {}).get("monitoring_mode", "individual_key")
        requested_mode = (payload.extra or {}).get("monitoring_mode", "individual_key")
        if requested_mode != current_mode:
            replacement_key = payload.api_key.strip() if isinstance(payload.api_key, str) else ""
            if not replacement_key or _crypto().decrypt(config.encrypted_api_key) == replacement_key:
                raise HTTPException(
                    status_code=422,
                    detail="Replacing the OpenRouter monitoring mode requires a new credential",
                )
            payload.api_key = replacement_key
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
    if payload.has_update_for("pricing_model") and payload.pricing_model is not None:
        config.pricing_model = payload.pricing_model
    if payload.has_update_for("subscription_amount"):
        config.subscription_amount = payload.subscription_amount
    if payload.has_update_for("subscription_currency") and payload.subscription_currency is not None:
        config.subscription_currency = payload.subscription_currency
    if payload.has_update_for("billing_cadence"):
        config.billing_cadence = payload.billing_cadence
    if payload.has_update_for("billing_anchor"):
        config.billing_anchor = payload.billing_anchor
    _validate_openrouter_config(config.provider, config.base_url, config.extra)
    _normalize_and_validate_billing(config)
    identity_changed = (
        (payload.has_update_for("api_key") and payload.api_key is not None and payload.api_key != old_key)
        or (payload.has_update_for("base_url") and config.base_url != old_base_url)
        or (payload.has_update_for("extra") and (config.extra or {}) != old_extra)
    )
    if identity_changed:
        config.usage_revision = (config.usage_revision or 1) + 1
    await session.commit()
    await session.refresh(config)
    return _config_read(config)


@router.delete(
    "/configs/{config_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_admin_auth)]
)
async def delete_config(config_id: int, session: AsyncSession = Depends(get_session)):
    result = await session.execute(delete(ProviderConfig).where(ProviderConfig.id == config_id))
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Provider config not found")
    await session.commit()


@router.get(
    "/configs/{config_id}/history",
    response_model=list[UsageSnapshotRead],
    dependencies=[Depends(require_scope("history:read"))],
)
async def config_history(
    config_id: int, hours: int = 168, limit: int = 500, session: AsyncSession = Depends(get_session)
):
    config = await session.get(ProviderConfig, config_id)
    if not config:
        raise HTTPException(status_code=404, detail="Provider config not found")
    if hours <= 0:
        raise HTTPException(status_code=400, detail="hours must be greater than zero")
    if limit <= 0:
        raise HTTPException(status_code=400, detail="limit must be greater than zero")
    since = datetime.now(UTC) - timedelta(hours=hours)
    result = await session.execute(
        select(UsageSnapshot)
        .where(
            UsageSnapshot.provider_config_id == config_id,
            UsageSnapshot.checked_at >= since,
            or_(
                UsageSnapshot.config_revision == config.usage_revision,
                and_(UsageSnapshot.config_revision.is_(None), config.usage_revision == 1),
            ),
        )
        .order_by(asc(UsageSnapshot.checked_at), asc(UsageSnapshot.id))
        .limit(limit)
    )
    return result.scalars().all()


async def _snapshot_for_config(
    config: ProviderConfig, analytics_state: dict | None = None
) -> tuple[UsageSnapshot, list[dict]]:
    try:
        adapter_cls = get_adapter_class(config.provider)
        crypto = _crypto()
        adapter_extra = dict(config.extra or {})
        if config.provider == "openrouter" and adapter_extra.get("monitoring_mode") == "account_wide":
            adapter_extra.update(
                {"_analytics_revision": config.usage_revision, "_analytics_state": analytics_state or {}}
            )
        adapter = adapter_cls(
            crypto.decrypt(config.encrypted_api_key),
            base_url=config.base_url,
            timeout=settings.request_timeout_seconds,
            extra=adapter_extra,
        )
        usage = await adapter.fetch_usage()
        updated_secret = getattr(adapter, "updated_secret", None)
        if updated_secret:
            config.encrypted_api_key = crypto.encrypt(updated_secret)
        snapshot = UsageSnapshot(
            provider_config_id=config.id,
            provider=config.provider,
            config_revision=config.usage_revision,
            status=usage.status,
            summary=usage.summary,
            metrics=[asdict(metric) for metric in usage.metrics],
            raw=usage.raw,
            error=None,
            error_details=None,
        )
        native = adapter.native_observations(usage.raw)
    except Exception as exc:  # noqa: BLE001 - classify + record, never leak secrets
        error = classify_exception(exc, stage="fetch_usage")
        snapshot = UsageSnapshot(
            provider_config_id=config.id,
            provider=config.provider,
            config_revision=config.usage_revision,
            status="error",
            summary=f"{config.label}: polling failed",
            metrics=[],
            raw={},
            error=error.message,
            error_details=error.to_dict(),
        )
        log_provider_failure(provider=config.provider, config_id=config.id, error=error)
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
        config_revision=config.usage_revision,
        metric=obs.metric,
        value=obs.value,
        unit=obs.unit,
        kind=obs.kind,
        source=obs.source,
        observed_at=obs.observed_at,
        window_start=obs.window_start,
        window_end=obs.window_end,
        reset_at=obs.reset_at,
        model=obs.model,
        provider_mapping=obs.provider_mapping,
        profile=obs.profile,
    )


def _observation_key(obs) -> tuple:
    """A stable identity for an observation, independent of naive/aware tz mixing."""
    return (
        obs.metric,
        _as_utc(getattr(obs, "window_start", None)),
        _as_utc(getattr(obs, "window_end", None)),
        _as_utc(obs.observed_at),
        getattr(obs, "model", None),
        getattr(obs, "provider_mapping", None),
        getattr(obs, "profile", None),
        getattr(obs, "source", None),
    )


async def _ingest_observations(
    session: AsyncSession, config: ProviderConfig, snapshot: UsageSnapshot, native: list[dict]
) -> None:
    """Derive and persist normalized observations for a freshly polled snapshot."""
    capabilities = get_adapter_class(config.provider).analytics or {}
    if snapshot.status != "error" and snapshot.metrics:
        recent = (
            (
                await session.execute(
                    select(UsageSnapshot)
                    .where(
                        UsageSnapshot.provider_config_id == snapshot.provider_config_id,
                        UsageSnapshot.id < snapshot.id,
                        or_(
                            UsageSnapshot.config_revision == snapshot.config_revision,
                            and_(UsageSnapshot.config_revision.is_(None), snapshot.config_revision == 1),
                        ),
                    )
                    .order_by(desc(UsageSnapshot.id))
                    .limit(3)
                )
            )
            .scalars()
            .all()
        )
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
    analytics_raw = snapshot.raw.get("analytics") if isinstance(snapshot.raw, dict) else None
    query_raw = snapshot.raw.get("analytics_query") if isinstance(snapshot.raw, dict) else None
    if config.provider == "openrouter" and isinstance(analytics_raw, dict):
        now = snapshot.checked_at
        scope = str((query_raw or {}).get("scope") or "account")
        workspace_id = str((query_raw or {}).get("workspace_id") or "")
        states = (
            (
                await session.execute(
                    select(OpenRouterAnalyticsState).where(
                        OpenRouterAnalyticsState.provider_config_id == config.id,
                        OpenRouterAnalyticsState.config_revision == config.usage_revision,
                        OpenRouterAnalyticsState.scope == scope,
                        OpenRouterAnalyticsState.workspace_id == workspace_id,
                    )
                )
            )
            .scalars()
            .all()
        )
        by_group = {row.grouping: row for row in states}
        query_items = {"": (query_raw or {}).get("account")} if isinstance(query_raw, dict) else {}
        if isinstance(query_raw, dict):
            query_items.update(query_raw.get("groups") or {})
        for grouping, evidence in query_items.items():
            row = by_group.get(grouping)
            if row is None:
                row = OpenRouterAnalyticsState(
                    provider_config_id=config.id,
                    config_revision=config.usage_revision,
                    scope=scope,
                    workspace_id=workspace_id,
                    grouping=grouping,
                )
                session.add(row)
            row.last_attempt_at = now
            window = (query_raw or {}).get("window") if isinstance(query_raw, dict) else None
            start, end = (
                (parse_time(window.get("start")), parse_time(window.get("end")))
                if isinstance(window, dict)
                else (None, None)
            )
            row.requested_start, row.requested_end = start, end
            if isinstance(evidence, dict) and start is not None and end is not None and not evidence.get("error"):
                row.completed_start, row.completed_end = start, end
                row.last_success_at, row.last_failure_at, row.error_category = now, None, None
                row.status = "empty" if not evidence.get("data") else "ready"
                # Unique identity makes retried/overlapping polls idempotent.  The
                # evidence and observations commit in this same transaction.
                existing_window = await session.scalar(
                    select(OpenRouterAnalyticsWindow).where(
                        OpenRouterAnalyticsWindow.provider_config_id == config.id,
                        OpenRouterAnalyticsWindow.config_revision == config.usage_revision,
                        OpenRouterAnalyticsWindow.scope == scope,
                        OpenRouterAnalyticsWindow.workspace_id == workspace_id,
                        OpenRouterAnalyticsWindow.grouping == grouping,
                        OpenRouterAnalyticsWindow.window_start == start,
                        OpenRouterAnalyticsWindow.window_end == end,
                    )
                )
                if existing_window is None:
                    session.add(
                        OpenRouterAnalyticsWindow(
                            provider_config_id=config.id,
                            config_revision=config.usage_revision,
                            scope=scope,
                            workspace_id=workspace_id,
                            grouping=grouping,
                            window_start=start,
                            window_end=end,
                            valid_empty=not bool(evidence.get("data")),
                            completed_at=now,
                        )
                    )
                if grouping == "" and query_raw.get("backfill"):
                    row.backfill_cursor = max(filter(None, [row.backfill_cursor, end]))
                    row.backfill_complete = row.backfill_cursor >= datetime.now(UTC).replace(
                        hour=0, minute=0, second=0, microsecond=0
                    )
            else:
                row.last_failure_at, row.error_category, row.status = (
                    now,
                    str((evidence or {}).get("error") or analytics_raw.get("error") or "upstream_error"),
                    "failed",
                )
        if not query_items:
            row = by_group.get("")
            if row is None:
                row = OpenRouterAnalyticsState(
                    provider_config_id=config.id,
                    config_revision=config.usage_revision,
                    scope=scope,
                    workspace_id=workspace_id,
                    grouping="",
                )
                session.add(row)
            row.last_attempt_at, row.last_failure_at = now, now
            row.error_category, row.status = str(analytics_raw.get("error") or "upstream_error"), "failed"
    if native:
        # Upsert native history rather than delete-and-reinsert. Providers return
        # a rolling window (Anthropic 24h, OpenAI 30d), so wiping the dataset each
        # poll would cap retained native history at that window.
        native_obs = normalize_native(native)
        if native_obs:
            lower = min(obs.observed_at for obs in native_obs)
            upper = max(obs.observed_at for obs in native_obs)
            existing = (
                (
                    await session.execute(
                        select(UsageObservation).where(
                            UsageObservation.provider_config_id == config.id,
                            or_(
                                UsageObservation.config_revision == config.usage_revision,
                                and_(UsageObservation.config_revision.is_(None), config.usage_revision == 1),
                            ),
                            UsageObservation.source.in_(("native", "native_grouped")),
                            UsageObservation.observed_at >= lower,
                            UsageObservation.observed_at <= upper,
                        )
                    )
                )
                .scalars()
                .all()
            )
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
        func.row_number()
        .over(
            partition_by=UsageSnapshot.provider_config_id,
            order_by=(desc(UsageSnapshot.checked_at), desc(UsageSnapshot.id)),
        )
        .label("rank"),
    ).subquery()
    latest_snapshot_ids = select(ranked_snapshots.c.id).where(ranked_snapshots.c.rank == 1)
    await session.execute(
        delete(UsageSnapshot).where(UsageSnapshot.checked_at < cutoff, UsageSnapshot.id.not_in(latest_snapshot_ids))
    )
    await session.commit()


async def _poll_enabled_configs(session: AsyncSession) -> list[UsageSnapshot]:
    configs = (
        (
            await session.execute(
                select(ProviderConfig).where(ProviderConfig.is_enabled.is_(True)).order_by(*_config_ordering())
            )
        )
        .scalars()
        .all()
    )
    analytics_states = {}
    if configs:
        rows = (
            (
                await session.execute(
                    select(OpenRouterAnalyticsState).where(
                        OpenRouterAnalyticsState.provider_config_id.in_([config.id for config in configs]),
                        OpenRouterAnalyticsState.grouping == "",
                    )
                )
            )
            .scalars()
            .all()
        )
        # Select the state belonging to the configuration's authoritative
        # effective scope; account and workspace cursors must never collide.
        analytics_states = {}
        by_config = {config.id: config for config in configs}
        for row in rows:
            config = by_config[row.provider_config_id]
            configured_workspace = (
                (config.extra or {}).get("analytics_workspace_id") if config.provider == "openrouter" else None
            )
            expected_scope, expected_workspace = (
                ("workspace", str(configured_workspace)) if configured_workspace else ("account", "")
            )
            if row.config_revision == config.usage_revision and (row.scope, row.workspace_id) == (
                expected_scope,
                expected_workspace,
            ):
                analytics_states[(row.provider_config_id, row.config_revision)] = {
                    "next_backfill_start": row.backfill_cursor.isoformat() if row.backfill_cursor else None,
                    "backfill_complete": row.backfill_complete,
                }
    results = (
        await asyncio.gather(
            *(
                _snapshot_for_config(config, analytics_states.get((config.id, config.usage_revision)))
                for config in configs
            )
        )
        if configs
        else []
    )
    current_revisions = (
        dict(
            (
                await session.execute(
                    select(ProviderConfig.id, ProviderConfig.usage_revision).where(
                        ProviderConfig.id.in_([config.id for config in configs])
                    )
                )
            ).all()
        )
        if configs
        else {}
    )
    compatible = [
        (config, result)
        for config, result in zip(configs, results)
        if current_revisions.get(config.id) == config.usage_revision
    ]
    snapshots = [result[0] for _, result in compatible]
    if snapshots:
        session.add_all(snapshots)
        await session.commit()
        for snapshot in snapshots:
            await session.refresh(snapshot)
        for config, (snapshot, native) in compatible:
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


@router.post(
    "/configs/{config_id}/poll", response_model=UsageSnapshotRead, dependencies=[Depends(require_scope("poll:write"))]
)
async def poll_config(config_id: int, session: AsyncSession = Depends(get_session)):
    async with _auto_poll_lock:
        config = await session.get(ProviderConfig, config_id)
        if not config:
            raise HTTPException(status_code=404, detail="Provider config not found")
        if not config.is_enabled:
            raise HTTPException(status_code=409, detail="Provider config is disabled")
        return await _poll_one(config, session)


async def _poll_one(config: ProviderConfig, session: AsyncSession) -> UsageSnapshot:
    revision = config.usage_revision
    snapshot, native = await _snapshot_for_config(config)
    current_revision = await session.scalar(select(ProviderConfig.usage_revision).where(ProviderConfig.id == config.id))
    if current_revision != revision:
        raise HTTPException(status_code=409, detail="Provider configuration changed while polling; retry")
    session.add(snapshot)
    await session.flush()
    current_revision = await session.scalar(select(ProviderConfig.usage_revision).where(ProviderConfig.id == config.id))
    if current_revision != revision:
        await session.rollback()
        raise HTTPException(status_code=409, detail="Provider configuration changed while polling; retry")
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


async def _health_for_config(
    session: AsyncSession, config: ProviderConfig
) -> tuple[UsageSnapshot | None, dict, UsageSnapshot | None]:
    """Derive ``(latest, health, last_good)`` for a config using targeted queries.

    No bounded scan window: the latest snapshot, last success, last failure, and
    failure count are each located with their own query, so a long run of
    failures can never hide an older successful snapshot.
    """
    latest = (
        await session.execute(
            select(UsageSnapshot)
            .where(
                UsageSnapshot.provider_config_id == config.id,
                or_(
                    UsageSnapshot.config_revision == config.usage_revision,
                    and_(UsageSnapshot.config_revision.is_(None), config.usage_revision == 1),
                ),
            )
            .order_by(desc(UsageSnapshot.checked_at), desc(UsageSnapshot.id))
            .limit(1)
        )
    ).scalar_one_or_none()

    last_success = (
        await session.execute(
            select(UsageSnapshot)
            .where(
                UsageSnapshot.provider_config_id == config.id,
                or_(
                    UsageSnapshot.config_revision == config.usage_revision,
                    and_(UsageSnapshot.config_revision.is_(None), config.usage_revision == 1),
                ),
                UsageSnapshot.status != "error",
            )
            .order_by(desc(UsageSnapshot.checked_at), desc(UsageSnapshot.id))
            .limit(1)
        )
    ).scalar_one_or_none()

    last_failure = (
        await session.execute(
            select(UsageSnapshot)
            .where(
                UsageSnapshot.provider_config_id == config.id,
                or_(
                    UsageSnapshot.config_revision == config.usage_revision,
                    and_(UsageSnapshot.config_revision.is_(None), config.usage_revision == 1),
                ),
                UsageSnapshot.status == "error",
            )
            .order_by(desc(UsageSnapshot.checked_at), desc(UsageSnapshot.id))
            .limit(1)
        )
    ).scalar_one_or_none()

    last_success_at = last_success.checked_at if last_success is not None else None
    if last_success_at is not None:
        consecutive = (
            await session.execute(
                select(func.count(UsageSnapshot.id)).where(
                    UsageSnapshot.provider_config_id == config.id,
                    or_(
                        UsageSnapshot.config_revision == config.usage_revision,
                        and_(UsageSnapshot.config_revision.is_(None), config.usage_revision == 1),
                    ),
                    UsageSnapshot.status == "error",
                    UsageSnapshot.checked_at > last_success_at,
                )
            )
        ).scalar_one()
    else:
        consecutive = (
            await session.execute(
                select(func.count(UsageSnapshot.id)).where(
                    UsageSnapshot.provider_config_id == config.id,
                    or_(
                        UsageSnapshot.config_revision == config.usage_revision,
                        and_(UsageSnapshot.config_revision.is_(None), config.usage_revision == 1),
                    ),
                    UsageSnapshot.status == "error",
                )
            )
        ).scalar_one()

    # Only surface error details when the *latest* attempt failed; a later
    # success clears stale error state so a healthy provider never shows an old
    # error from before its most recent good sync.
    latest_is_error = latest is not None and latest.status == "error"
    health = derive_health(
        latest_status=latest.status if latest is not None else None,
        last_attempt_at=latest.checked_at if latest is not None else None,
        last_success_at=last_success_at,
        last_failure_at=last_failure.checked_at if last_failure is not None else None,
        consecutive_failures=int(consecutive or 0),
        latest_error=last_failure.error if (latest_is_error and last_failure is not None) else None,
        latest_error_details=last_failure.error_details if (latest_is_error and last_failure is not None) else None,
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
        alerts = (
            build_alerts(alert_source.metrics if alert_source else [], config.alert_thresholds) if alert_source else []
        )
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
    return HomepagePayload(
        configured_providers=configured,
        healthy_providers=healthy,
        degraded_providers=degraded,
        latest_check=checked,
        summary=f"{healthy}/{configured} providers healthy" if configured else "No providers configured",
        metrics=metrics,
        list=_homepage_provider_rows(rows),
    )
