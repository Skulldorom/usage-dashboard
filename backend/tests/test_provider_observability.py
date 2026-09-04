"""API-level tests for provider health/error observability (#192)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.auth import _hash_secret
from app.core.config import settings
from app.core.crypto import CryptoService
from app.database import get_session
from app.main import app
from app.models import AdminCredential, Base, ProviderConfig, UsageSnapshot

DB = Path("/tmp/usage_dashboard_test_observability.db")
TEST_DATABASE_URL = f"sqlite+aiosqlite:///{DB}"
ADMIN_AUTH = {"Authorization": "Bearer test-admin-session-token-123"}


@pytest_asyncio.fixture(autouse=True)
async def sqlite_db(monkeypatch):
    monkeypatch.setattr(settings, "homepage_allowed_hosts_raw", "")
    if DB.exists():
        DB.unlink()
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        session.add(
            AdminCredential(
                password_hash="test-only",
                session_tokens=[{"token_hash": _hash_secret("test-admin-session-token-123"), "expires_at": "2999-01-01T00:00:00+00:00"}],
            )
        )
        await session.commit()

    async def override_session():
        async with Session() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    yield Session
    app.dependency_overrides.clear()
    await engine.dispose()
    if DB.exists():
        DB.unlink()


async def _config(Session, provider="anthropic"):
    encrypted = CryptoService(settings.encryption_key).encrypt("sk-test")
    async with Session() as session:
        config = ProviderConfig(provider=provider, label="main", encrypted_api_key=encrypted, is_enabled=True)
        session.add(config)
        await session.commit()
        await session.refresh(config)
        return config


async def _snapshot(Session, config, *, status, error=None, error_details=None, checked_at=None, metrics=None):
    async with Session() as session:
        snap = UsageSnapshot(
            provider_config_id=config.id,
            provider=config.provider,
            status=status,
            summary="",
            metrics=metrics or [],
            raw={},
            error=error,
            error_details=error_details,
            checked_at=checked_at or datetime.now(UTC),
        )
        session.add(snap)
        await session.commit()
        await session.refresh(snap)
        return snap


@pytest.mark.asyncio
async def test_last_successful_usage_retained_after_failure(sqlite_db):
    Session = sqlite_db
    config = await _config(Session, provider="codex")
    now = datetime.now(UTC)
    await _snapshot(
        Session, config, status="healthy",
        metrics=[{"label": "plan_type", "value": "Pro"}],
        checked_at=now - timedelta(minutes=10),
    )
    await _snapshot(
        Session, config, status="error",
        error="Too Many Requests",
        error_details={"category": "rate_limit", "message": "Too Many Requests", "http_status": 429, "stage": "fetch_usage", "retryable": True, "occurred_at": now.isoformat()},
        checked_at=now,
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/usage", headers=ADMIN_AUTH)

    assert response.status_code == 200, response.text
    row = response.json()[0]
    assert row["latest"]["status"] == "error"
    # Last-known-good usage is still surfaced for the frontend.
    assert row["last_good"] is not None
    assert row["last_good"]["status"] == "healthy"
    assert row["health"]["latest_error_details"]["category"] == "rate_limit"
    assert row["health"]["latest_error_details"]["http_status"] == 429


@pytest.mark.asyncio
async def test_latest_normalized_error_returned_through_api(sqlite_db):
    Session = sqlite_db
    config = await _config(Session, provider="codex")
    now = datetime.now(UTC)
    await _snapshot(
        Session, config, status="error",
        error="Codex access token rejected - re-authorize the Codex provider",
        error_details={"category": "authentication", "message": "Codex access token rejected - re-authorize the Codex provider", "http_status": 401, "stage": "fetch_usage", "retryable": False, "occurred_at": now.isoformat()},
        checked_at=now,
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/usage", headers=ADMIN_AUTH)

    row = response.json()[0]
    details = row["health"]["latest_error_details"]
    assert details["category"] == "authentication"
    assert details["http_status"] == 401
    assert details["stage"] == "fetch_usage"
    assert details["retryable"] is False
    assert details["occurred_at"] is not None
    # The sanitized error message carries no secrets.
    assert "sk-" not in row["health"]["latest_error"]


@pytest.mark.asyncio
async def test_healthy_success_clears_stale_error(sqlite_db):
    Session = sqlite_db
    config = await _config(Session, provider="codex")
    now = datetime.now(UTC)
    await _snapshot(
        Session, config, status="error",
        error="Too Many Requests",
        error_details={"category": "rate_limit", "message": "Too Many Requests", "http_status": 429, "stage": "fetch_usage", "retryable": True, "occurred_at": now.isoformat()},
        checked_at=now - timedelta(minutes=10),
    )
    await _snapshot(
        Session, config, status="healthy",
        metrics=[{"label": "plan_type", "value": "Pro"}],
        checked_at=now,
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/usage", headers=ADMIN_AUTH)

    row = response.json()[0]
    assert row["latest"]["status"] == "healthy"
    assert row["health"]["status"] == "healthy"
    assert row["health"]["latest_error"] is None
    assert row["health"]["latest_error_details"] is None
