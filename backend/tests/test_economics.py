"""Regression tests for provider billing and value analytics."""

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
from app.models import AdminCredential, Base, ProviderConfig, UsageObservation

DB = Path("/tmp/usage_dashboard_test_economics.db")
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


async def _config(Session, provider="anthropic", **kwargs):
    encrypted = CryptoService(settings.encryption_key).encrypt("sk-test")
    async with Session() as session:
        config = ProviderConfig(provider=provider, label=kwargs.pop("label", "main"), encrypted_api_key=encrypted, is_enabled=True, **kwargs)
        session.add(config)
        await session.commit()
        await session.refresh(config)
        return config


@pytest.mark.asyncio
async def test_economics_subscription_prorates_real_month_overlap(sqlite_db):
    Session = sqlite_db
    config = await _config(
        Session,
        provider="anthropic",
        pricing_model="subscription",
        subscription_amount=31,
        subscription_currency="USD",
        billing_cadence="monthly",
        billing_anchor=datetime(2026, 1, 31, tzinfo=UTC),
    )
    start = datetime(2026, 2, 10, tzinfo=UTC)
    end = datetime(2026, 3, 10, tzinfo=UTC)
    async with Session() as session:
        session.add_all([
            UsageObservation(provider="anthropic", provider_mapping="anthropic", metric="input_tokens", value=1_000_000, unit="tokens", kind="delta", source="hermes", observed_at=start + timedelta(days=1), model="claude-sonnet-4"),
            UsageObservation(provider="anthropic", provider_mapping="anthropic", metric="output_tokens", value=1_000_000, unit="tokens", kind="delta", source="hermes", observed_at=start + timedelta(days=1), model="claude-sonnet-4"),
        ])
        await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/analytics/economics", params={"from": start.isoformat(), "to": end.isoformat()}, headers=ADMIN_AUTH)

    assert response.status_code == 200, response.text
    row = response.json()["providers"][0]
    # Jan31-Feb28 has 28 days and Feb28-Mar28 has 28 days. Selection overlaps 18 + 10 days.
    assert row["subscription_cost_basis"]["amount"] == pytest.approx(31.0, abs=0.0001)
    assert row["observed"]["priced_token_pct"] == 100.0
    assert row["api_equivalent"]["value"] == 18.0
    assert row["economics"]["value_multiplier"] == pytest.approx(18 / 31, abs=0.0001)


@pytest.mark.asyncio
async def test_economics_marks_unknown_models_unpriced_and_ineligible(sqlite_db):
    Session = sqlite_db
    await _config(Session, provider="anthropic", pricing_model="subscription", subscription_amount=20, subscription_currency="USD", billing_cadence="monthly")
    now = datetime.now(UTC)
    async with Session() as session:
        session.add(UsageObservation(provider="anthropic", provider_mapping="anthropic", metric="input_tokens", value=1_000_000, unit="tokens", kind="delta", source="hermes", observed_at=now - timedelta(days=1), model="mystery-model"))
        await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/analytics/economics", headers=ADMIN_AUTH)

    assert response.status_code == 200, response.text
    row = response.json()["providers"][0]
    assert row["api_equivalent"]["value"] is None
    assert row["observed"]["unpriced_tokens"] == 1_000_000
    assert row["comparison_eligible"] is False
    assert "priced" in row["exclusion_reason"]


@pytest.mark.asyncio
async def test_economics_payg_actual_spend_is_distinct_from_api_equivalent(sqlite_db):
    Session = sqlite_db
    config = await _config(Session, provider="openai", pricing_model="payg")
    now = datetime.now(UTC)
    async with Session() as session:
        session.add_all([
            UsageObservation(provider_config_id=config.id, provider="openai", metric="daily_cost", value=2.5, unit="USD", kind="delta", source="native", observed_at=now - timedelta(days=1)),
            UsageObservation(provider="openai", provider_mapping="openai", metric="input_tokens", value=1_000_000, unit="tokens", kind="delta", source="hermes", observed_at=now - timedelta(days=1), model="gpt-4o"),
        ])
        await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/analytics/economics", headers=ADMIN_AUTH)

    assert response.status_code == 200, response.text
    row = response.json()["providers"][0]
    assert row["actual_spend"]["amount"] == 2.5
    assert row["cost_basis"]["kind"] == "actual_spend"
    assert row["api_equivalent"]["value"] == 2.5
    assert row["actual_spend"]["amount"] == row["api_equivalent"]["value"]


@pytest.mark.asyncio
async def test_config_api_persists_billing_fields(sqlite_db):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = await client.post(
            "/api/v1/configs",
            json={
                "provider": "deepseek",
                "label": "DeepSeek billing",
                "api_key": "sk-test",
                "pricing_model": "subscription",
                "subscription_amount": 10,
                "subscription_currency": "usd",
                "billing_cadence": "monthly",
                "billing_anchor": "2026-01-15T00:00:00Z",
            },
            headers=ADMIN_AUTH,
        )
        assert created.status_code == 201, created.text
        payload = created.json()
        assert payload["pricing_model"] == "subscription"
        assert payload["subscription_amount"] == 10
        assert payload["subscription_currency"] == "USD"

        updated = await client.patch(
            f"/api/v1/configs/{payload['id']}",
            json={"pricing_model": "payg", "subscription_amount": None, "billing_cadence": None},
            headers=ADMIN_AUTH,
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["pricing_model"] == "payg"
        assert updated.json()["billing_cadence"] is None
