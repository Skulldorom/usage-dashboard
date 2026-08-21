"""API tests for the analytics endpoints and scope enforcement."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.analytics.capabilities import analytics_spec, metric_spec
from app.core.auth import _hash_secret
from app.core.config import settings
from app.core.crypto import CryptoService
from app.database import get_session
from app.main import app
from app.models import AdminCredential, Base, ProviderConfig, UsageObservation
from app.providers.base import Metric, ProviderAdapter, ProviderUsage
from app.providers.registry import ADAPTERS

DB = Path("/tmp/usage_dashboard_test_analytics.db")
TEST_DATABASE_URL = f"sqlite+aiosqlite:///{DB}"

ADMIN_AUTH = {"Authorization": "Bearer test-admin-session-token-123"}


@pytest_asyncio.fixture(autouse=True)
async def sqlite_db(monkeypatch):
    monkeypatch.setattr(settings, "homepage_allowed_hosts_raw", "")
    monkeypatch.setattr(settings, "snapshot_retention_days", 90)
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
                session_tokens=[
                    {"token_hash": _hash_secret("test-admin-session-token-123"), "expires_at": "2999-01-01T00:00:00+00:00"}
                ],
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


async def _seed_observations(Session, config, observations):
    async with Session() as session:
        for obs in observations:
            session.add(
                UsageObservation(
                    provider_config_id=config.id,
                    provider=config.provider,
                    metric=obs["metric"],
                    value=obs["value"],
                    unit=obs.get("unit"),
                    kind=obs.get("kind", "delta"),
                    source=obs.get("source", "snapshot"),
                    observed_at=obs["observed_at"],
                    window_start=obs.get("window_start"),
                    window_end=obs.get("window_end"),
                    reset_at=obs.get("reset_at"),
                )
            )
        await session.commit()


async def _create_config(Session, provider="deepseek"):
    encrypted = CryptoService(settings.encryption_key).encrypt("sk-test")
    async with Session() as session:
        config = ProviderConfig(provider=provider, label="main", encrypted_api_key=encrypted, is_enabled=True)
        session.add(config)
        await session.commit()
        await session.refresh(config)
        return config


@pytest.mark.asyncio
async def test_provider_analytics_info(sqlite_db):
    Session = sqlite_db
    config = await _create_config(Session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/api/v1/analytics/providers/{config.id}", headers=ADMIN_AUTH)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["provider"] == "deepseek"
    assert payload["supported"] is True
    assert payload["native_history"] is False
    metric_labels = [m["label"] for m in payload["metrics"]]
    assert "total_balance" in metric_labels
    assert payload["preferred_metric"] == "total_balance"


@pytest.mark.asyncio
async def test_timeseries_sums_counter_deltas(sqlite_db):
    Session = sqlite_db
    config = await _create_config(Session, provider="openrouter")
    base = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    await _seed_observations(
        Session,
        config,
        [
            {"metric": "usage_daily", "value": 10.0, "observed_at": base, "kind": "delta", "source": "snapshot"},
            {"metric": "usage_daily", "value": 15.0, "observed_at": base + timedelta(hours=6), "kind": "delta", "source": "snapshot"},
        ],
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            f"/api/v1/analytics/providers/{config.id}/timeseries",
            params={"metric": "usage_daily", "interval": "day"},
            headers=ADMIN_AUTH,
        )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["metric"] == "usage_daily"
    assert payload["metric_type"] == "counter"
    totals = [b["total"] for b in payload["buckets"] if b["total"]]
    assert sum(totals) == 25.0


@pytest.mark.asyncio
async def test_forecast_endpoint_reports_confidence(sqlite_db):
    Session = sqlite_db
    config = await _create_config(Session, provider="deepseek")
    base = datetime.now(UTC) - timedelta(days=5)
    observations = [
        {"metric": "total_balance", "value": 100.0, "observed_at": base, "kind": "point", "source": "snapshot"},
    ]
    for day in range(1, 5):
        observations.append({"metric": "total_balance", "value": 2.0, "observed_at": base + timedelta(days=day), "kind": "delta", "source": "snapshot"})
    await _seed_observations(Session, config, observations)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            f"/api/v1/analytics/providers/{config.id}/forecast",
            params={"metric": "total_balance"},
            headers=ADMIN_AUTH,
        )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["metric"] == "total_balance"
    assert payload["metric_type"] == "balance"
    assert "confidence" in payload
    assert payload["confidence"]["level"] in ("high", "medium", "low")
    assert payload["estimated_remaining_days"] is not None


@pytest.mark.asyncio
async def test_analytics_requires_analytics_read_scope(sqlite_db):
    Session = sqlite_db
    config = await _create_config(Session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        no_scope = await client.post(
            "/api/v1/api-tokens",
            json={"name": "Usage", "scopes": ["usage:read"]},
            headers=ADMIN_AUTH,
        )
        assert no_scope.status_code == 201
        usage_token = {"Authorization": f"Bearer {no_scope.json()['token']}"}

        forbidden = await client.get(f"/api/v1/analytics/providers/{config.id}", headers=usage_token)
        assert forbidden.status_code == 403

        scoped = await client.post(
            "/api/v1/api-tokens",
            json={"name": "Analytics", "scopes": ["analytics:read"]},
            headers=ADMIN_AUTH,
        )
        assert scoped.status_code == 201
        analytics_token = {"Authorization": f"Bearer {scoped.json()['token']}"}

        allowed = await client.get(f"/api/v1/analytics/providers/{config.id}", headers=analytics_token)
        assert allowed.status_code == 200


class AnalyticsFakeAdapter(ProviderAdapter):
    id = "analyticsfake"
    name = "Analytics Fake"
    description = "Fake provider with analytics metadata"
    default_base_url = "https://fake.example"
    metric_names = ["used"]
    analytics = analytics_spec(
        supported=True,
        metrics={"used": metric_spec(type_="counter", unit="credits", direction="increasing")},
    )
    responses: list[float] = [100.0]

    async def fetch_usage(self) -> ProviderUsage:
        value = self.responses[0]
        return ProviderUsage(status="healthy", summary="ok", metrics=[Metric("used", value, "credits")], raw={})


@pytest.mark.asyncio
async def test_poll_ingests_observations(sqlite_db, monkeypatch):
    Session = sqlite_db
    monkeypatch.setitem(ADAPTERS, "analyticsfake", AnalyticsFakeAdapter)
    config = await _create_config(Session, provider="analyticsfake")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first = await client.post(f"/api/v1/configs/{config.id}/poll", headers=ADMIN_AUTH)
        assert first.status_code == 200, first.text

    async with Session() as session:
        rows = (await session.execute(select(UsageObservation).where(UsageObservation.provider_config_id == config.id))).scalars().all()
        kinds = sorted({row.kind for row in rows})
    assert kinds == ["point"]

    # Second poll at a higher value must produce a delta observation.
    AnalyticsFakeAdapter.responses = [140.0]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        second = await client.post(f"/api/v1/configs/{config.id}/poll", headers=ADMIN_AUTH)
        assert second.status_code == 200, second.text

    async with Session() as session:
        rows = (await session.execute(select(UsageObservation).where(UsageObservation.provider_config_id == config.id))).scalars().all()
        deltas = [row.value for row in rows if row.kind == "delta"]
    assert deltas == [40.0]
