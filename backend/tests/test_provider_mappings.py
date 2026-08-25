"""Tests for editable Hermes provider mappings (issue #155)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.auth import _hash_secret
from app.core.config import settings
from app.database import get_session
from app.main import app
from app.models import AdminCredential, Base, DataSourceConfig, ProviderConfig, UsageObservation

DB = Path("/tmp/usage_dashboard_test_mappings.db")
TEST_DATABASE_URL = f"sqlite+aiosqlite:///{DB}"
AUTH = {"Authorization": "Bearer test-admin-session-token-123"}


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


def _unit_for(metric: str) -> str:
    if metric == "cost":
        return "USD"
    if metric == "requests":
        return "count"
    return "tokens"


async def _seed(Session) -> int:
    now = datetime.now(UTC)
    async with Session() as session:
        source = DataSourceConfig(kind="hermes", name="main", base_url="http://hermes.local", is_enabled=True)
        session.add(source)
        await session.flush()
        source_id = source.id
        session.add_all(
            [
                ProviderConfig(provider="codex", label="main", encrypted_api_key="e", is_enabled=True),
                ProviderConfig(provider="deepseek", label="main", encrypted_api_key="e", is_enabled=True),
                ProviderConfig(provider="openai", label="main", encrypted_api_key="e", is_enabled=False),  # disabled
            ]
        )
        await session.flush()
        rows = [
            ("openai-codex", "input_tokens", 400.0),
            ("openai-codex", "output_tokens", 100.0),
            ("openai-codex", "cost", 0.5),
            ("openai-codex", "requests", 3.0),
            ("auto", "input_tokens", 50.0),
            ("auto", "requests", 1.0),
            ("unknown", "input_tokens", 10.0),
        ]
        for raw, metric, value in rows:
            session.add(
                UsageObservation(
                    data_source_id=source_id,
                    provider=raw,
                    provider_mapping=raw,
                    metric=metric,
                    value=value,
                    unit=_unit_for(metric),
                    kind="delta",
                    source="hermes",
                    observed_at=now - timedelta(minutes=10),
                )
            )
        await session.commit()
        return source_id


def _observed(body):
    return {row["raw_provider"]: row for row in body["observed"]}


@pytest.mark.asyncio
async def test_get_returns_observed_providers_with_aggregates(sqlite_db):
    source_id = await _seed(sqlite_db)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/api/v1/datasources/configs/{source_id}/provider-mappings", headers=AUTH)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["source_id"] == source_id
    assert {row["provider"] for row in body["configured_providers"]} == {"codex", "deepseek", "openai"}
    observed = _observed(body)
    assert set(observed) == {"auto", "openai-codex", "unknown"}

    codex = observed["openai-codex"]
    assert codex["cost"] == 0.5
    assert codex["tokens"] == 500.0
    assert codex["requests"] == 3.0
    assert codex["observations"] == 4
    assert codex["last_observed_at"] is not None
    assert codex["status"] == "unmapped"

    assert observed["auto"]["tokens"] == 50.0
    assert observed["unknown"]["tokens"] == 10.0
    assert body["mapped_count"] == 0
    assert body["unmapped_count"] == 3
    assert body["unmapped_observations"] == 7


@pytest.mark.asyncio
async def test_data_source_config_exposes_unmapped_alert_mute(sqlite_db):
    source_id = await _seed(sqlite_db)
    async with sqlite_db() as session:
        source = await session.get(DataSourceConfig, source_id)
        source.extra = {"mute_unmapped_provider_alerts": True}
        await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/datasources/configs", headers=AUTH)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body[0]["id"] == source_id
    assert body[0]["mute_unmapped_provider_alerts"] is True


@pytest.mark.asyncio
async def test_put_creates_many_to_one_and_clears_mappings(sqlite_db):
    source_id = await _seed(sqlite_db)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = await client.put(
            f"/api/v1/datasources/configs/{source_id}/provider-mappings",
            json={"mappings": {"openai-codex": "codex", "auto": "codex"}},
            headers=AUTH,
        )
        assert created.status_code == 200, created.text
        body = created.json()
        observed = _observed(body)
        # many-to-one: two raw providers map to the same target
        assert observed["openai-codex"]["mapped_to"] == "codex"
        assert observed["openai-codex"]["status"] == "mapped"
        assert observed["auto"]["mapped_to"] == "codex"
        assert observed["auto"]["status"] == "mapped"
        assert observed["unknown"]["status"] == "unmapped"
        assert body["mapped_count"] == 2
        assert body["unmapped_count"] == 1

        # clear one mapping (null), keep the other
        cleared = await client.put(
            f"/api/v1/datasources/configs/{source_id}/provider-mappings",
            json={"mappings": {"auto": None}},
            headers=AUTH,
        )
        assert cleared.status_code == 200, cleared.text
        observed = _observed(cleared.json())
        assert observed["auto"]["status"] == "unmapped"
        assert observed["openai-codex"]["status"] == "mapped"

    async with sqlite_db() as session:
        source = await session.get(DataSourceConfig, source_id)
        assert (source.extra or {}).get("provider_mappings") == {"openai-codex": "codex"}


@pytest.mark.asyncio
async def test_put_rejects_unknown_target(sqlite_db):
    source_id = await _seed(sqlite_db)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.put(
            f"/api/v1/datasources/configs/{source_id}/provider-mappings",
            json={"mappings": {"openai-codex": "not-a-provider"}},
            headers=AUTH,
        )
    assert response.status_code == 400
    assert "Unknown provider" in response.json()["detail"]


@pytest.mark.asyncio
async def test_mapping_to_disabled_provider_is_invalid(sqlite_db):
    source_id = await _seed(sqlite_db)
    async with sqlite_db() as session:
        source = await session.get(DataSourceConfig, source_id)
        source.extra = {"provider_mappings": {"openai-codex": "openai"}}  # openai is disabled
        await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/api/v1/datasources/configs/{source_id}/provider-mappings", headers=AUTH)

    assert response.status_code == 200, response.text
    codex = _observed(response.json())["openai-codex"]
    assert codex["status"] == "invalid"
    assert codex["mapped_to"] == "openai"
    assert "disabled" in codex["reason"]


@pytest.mark.asyncio
async def test_mapping_to_deleted_provider_is_invalid(sqlite_db):
    source_id = await _seed(sqlite_db)
    async with sqlite_db() as session:
        source = await session.get(DataSourceConfig, source_id)
        source.extra = {"provider_mappings": {"openai-codex": "anthropic"}}  # not configured
        await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/api/v1/datasources/configs/{source_id}/provider-mappings", headers=AUTH)

    assert response.status_code == 200, response.text
    codex = _observed(response.json())["openai-codex"]
    assert codex["status"] == "invalid"
    assert codex["mapped_to"] == "anthropic"
    assert "no longer exists" in codex["reason"]


@pytest.mark.asyncio
async def test_mapping_requires_admin(sqlite_db):
    source_id = await _seed(sqlite_db)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/api/v1/datasources/configs/{source_id}/provider-mappings")
    assert response.status_code == 401
