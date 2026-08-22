"""Tests for the data source abstraction, ingestion, and Hermes API."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.auth import _hash_secret
from app.core.config import settings
from app.database import get_session
from app.datasources.base import expand_observation_records
from app.datasources.service import _persist_observations
from app.main import app
from app.models import AdminCredential, Base, DataSourceConfig, ProviderConfig, UsageObservation

DB = Path("/tmp/usage_dashboard_test_datasources.db")
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


# --- expand_observation_records (pure) ---


def test_expand_records_into_per_metric_observations():
    records = [
        {
            "timestamp": "2026-08-22T12:00:00+00:00",
            "provider": "anthropic",
            "model": "claude-sonnet-4",
            "profile": "coder",
            "session_id": "s1",
            "input_tokens": 100,
            "output_tokens": 50,
            "cost": 0.0123,
            "cost_type": "estimated",
        }
    ]
    obs = expand_observation_records(records)
    by_metric = {o["metric"]: o for o in obs}
    assert set(by_metric) == {"input_tokens", "output_tokens", "cost"}
    assert by_metric["input_tokens"]["value"] == 100
    assert by_metric["input_tokens"]["unit"] == "tokens"
    assert by_metric["input_tokens"]["source"] == "hermes"
    assert by_metric["input_tokens"]["provider"] == "anthropic"
    assert by_metric["input_tokens"]["profile"] == "coder"
    assert by_metric["cost"]["cost_type"] == "estimated"
    # cost_type is only attached to the cost metric
    assert by_metric["input_tokens"]["cost_type"] is None


def test_expand_skips_bad_records():
    records = [
        {"timestamp": "not-a-date", "provider": "x", "input_tokens": 1},
        {"provider": "x", "input_tokens": 1},  # no timestamp
        {"timestamp": "2026-08-22T12:00:00+00:00", "provider": "x", "input_tokens": "NaN"},
        {"timestamp": "2026-08-22T12:00:00+00:00", "provider": "x"},  # no numeric metrics
    ]
    assert expand_observation_records(records) == []


def test_expand_normalizes_provider_and_epoch():
    records = [{"timestamp": 1787310000, "provider": " OpenAI ", "requests": 2}]
    obs = expand_observation_records(records)
    assert obs[0]["provider"] == "openai"
    assert obs[0]["provider_mapping"] == "openai"
    assert obs[0]["metric"] == "requests"
    assert obs[0]["value"] == 2.0


# --- data source API + ingestion ---


async def _seed_source_and_provider(Session):
    async with Session() as session:
        source = DataSourceConfig(kind="hermes", name="main", base_url="http://hermes.local", is_enabled=True)
        provider = ProviderConfig(provider="anthropic", label="main", encrypted_api_key="encrypted", is_enabled=True)
        session.add_all([source, provider])
        await session.commit()
        await session.refresh(source)
        await session.refresh(provider)
        return source.id, provider.id


async def _seed_observations(Session, source_id, provider_id):
    now = datetime.now(UTC)
    async with Session() as session:
        session.add_all(
            [
                UsageObservation(
                    data_source_id=source_id,
                    provider="anthropic",
                    provider_mapping="anthropic",
                    metric="input_tokens",
                    value=1000.0,
                    unit="tokens",
                    kind="delta",
                    source="hermes",
                    observed_at=now - timedelta(hours=1),
                    model="claude-sonnet-4",
                    profile="coder",
                    session_id="s1",
                ),
                UsageObservation(
                    data_source_id=source_id,
                    provider="anthropic",
                    provider_mapping="anthropic",
                    metric="output_tokens",
                    value=500.0,
                    unit="tokens",
                    kind="delta",
                    source="hermes",
                    observed_at=now - timedelta(hours=1),
                    model="claude-sonnet-4",
                    profile="coder",
                    session_id="s1",
                ),
                UsageObservation(
                    data_source_id=source_id,
                    provider="anthropic",
                    provider_mapping="anthropic",
                    metric="cost",
                    value=2.5,
                    unit="USD",
                    kind="delta",
                    source="hermes",
                    observed_at=now - timedelta(hours=1),
                    profile="coder",
                    session_id="s1",
                    cost_type="estimated",
                ),
                # Provider-reported observation (authoritative)
                UsageObservation(
                    provider_config_id=provider_id,
                    provider="anthropic",
                    metric="input_tokens",
                    value=2000.0,
                    unit="tokens",
                    kind="delta",
                    source="native",
                    observed_at=now - timedelta(hours=1),
                ),
            ]
        )
        await session.commit()


@pytest.mark.asyncio
async def test_data_source_crud_and_status(sqlite_db):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        catalog = await client.get("/api/v1/datasources", headers=AUTH)
        assert catalog.status_code == 200
        assert any(item["id"] == "hermes" for item in catalog.json())

        created = await client.post(
            "/api/v1/datasources/configs",
            json={"kind": "hermes", "base_url": "http://hermes.local", "token": "secret-token"},
            headers=AUTH,
        )
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["token_masked"] == "••••••••"
        assert "token" not in body
        assert body["status"]["status"] == "never_connected"

        status = await client.get(f"/api/v1/datasources/configs/{body['id']}/status", headers=AUTH)
        assert status.json()["status"] == "never_connected"

        deleted = await client.delete(f"/api/v1/datasources/configs/{body['id']}", headers=AUTH)
        assert deleted.status_code == 204


@pytest.mark.asyncio
async def test_data_source_requires_admin_for_writes(sqlite_db):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/datasources/configs",
            json={"kind": "hermes", "base_url": "http://hermes.local"},
        )
        assert response.status_code == 401


@pytest.mark.asyncio
async def test_hermes_breakdown_and_attribution(sqlite_db):
    source_id, provider_id = await _seed_source_and_provider(sqlite_db)
    await _seed_observations(sqlite_db, source_id, provider_id)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        breakdown = await client.get("/api/v1/analytics/hermes", headers=AUTH)
        assert breakdown.status_code == 200, breakdown.text
        body = breakdown.json()
        totals = {t["metric"]: t["value"] for t in body["totals"]}
        assert totals["input_tokens"] == 1000.0
        assert totals["output_tokens"] == 500.0
        assert totals["cost"] == 2.5
        assert totals["tokens"] == 1500.0
        assert body["sessions"] == 1
        assert body["by_provider"][0]["key"] == "anthropic"
        assert body["by_model"][0]["key"] == "claude-sonnet-4"
        assert body["by_profile"][0]["key"] == "coder"

        attribution = await client.get(
            f"/api/v1/analytics/providers/{provider_id}/attribution", headers=AUTH
        )
        assert attribution.status_code == 200, attribution.text
        metrics = {m["metric"]: m for m in attribution.json()["metrics"]}
        # input_tokens: provider reported 2000, hermes observed 1000 → 50%
        assert metrics["input_tokens"]["provider_total"] == 2000.0
        assert metrics["input_tokens"]["hermes_observed"] == 1000.0
        assert metrics["input_tokens"]["attribution_pct"] == 50.0
        assert metrics["input_tokens"]["unattributed"] == 1000.0
        # cost: provider reports no cost → provider_total None (observed only)
        assert metrics["cost"]["provider_total"] is None
        assert metrics["cost"]["hermes_observed"] == 2.5
        assert metrics["cost"]["status"] == "hermes_only"
        assert metrics["input_tokens"]["status"] == "partial"


# --- deduplication ---


def _record(**overrides):
    base = {
        "timestamp": "2026-08-22T12:00:00+00:00",
        "provider": "anthropic",
        "model": "claude-sonnet-4",
        "profile": "coder",
        "session_id": "s1",
        "input_tokens": 100,
    }
    base.update(overrides)
    return base


async def _make_source(Session, name="main"):
    async with Session() as session:
        source = DataSourceConfig(kind="hermes", name=name, base_url="http://x", is_enabled=True)
        session.add(source)
        await session.commit()
        await session.refresh(source)
        return source.id


async def _persist(Session, source_id, records):
    observations = expand_observation_records(records)
    async with Session() as session:
        source = await session.get(DataSourceConfig, source_id)
        return await _persist_observations(session, source, observations)


async def _count(Session, source_id):
    async with Session() as session:
        return await session.scalar(
            select(func.count(UsageObservation.id)).where(UsageObservation.data_source_id == source_id)
        )


@pytest.mark.asyncio
async def test_resync_is_idempotent(sqlite_db):
    source_id = await _make_source(sqlite_db)
    assert await _persist(sqlite_db, source_id, [_record()]) == 1
    assert await _persist(sqlite_db, source_id, [_record()]) == 0
    assert await _count(sqlite_db, source_id) == 1


@pytest.mark.asyncio
async def test_distinct_observations_at_same_timestamp_preserved(sqlite_db):
    source_id = await _make_source(sqlite_db)
    inserted = await _persist(sqlite_db, source_id, [_record(session_id="s1"), _record(session_id="s2")])
    assert inserted == 2


@pytest.mark.asyncio
async def test_different_models_not_collapsed(sqlite_db):
    source_id = await _make_source(sqlite_db)
    inserted = await _persist(sqlite_db, source_id, [_record(model="claude-sonnet-4"), _record(model="claude-opus-4")])
    assert inserted == 2


@pytest.mark.asyncio
async def test_explicit_event_id_dedupes(sqlite_db):
    source_id = await _make_source(sqlite_db)
    assert await _persist(sqlite_db, source_id, [_record(event_id="evt-1")]) == 1
    assert await _persist(sqlite_db, source_id, [_record(event_id="evt-1")]) == 0


@pytest.mark.asyncio
async def test_different_sources_can_share_event_id(sqlite_db):
    source_a = await _make_source(sqlite_db, name="a")
    source_b = await _make_source(sqlite_db, name="b")
    assert await _persist(sqlite_db, source_a, [_record(event_id="evt-shared")]) == 1
    assert await _persist(sqlite_db, source_b, [_record(event_id="evt-shared")]) == 1
    assert await _count(sqlite_db, source_a) == 1
    assert await _count(sqlite_db, source_b) == 1


@pytest.mark.asyncio
async def test_db_unique_constraint_blocks_duplicate(sqlite_db):
    source_id = await _make_source(sqlite_db)
    now = datetime.now(UTC)
    async with sqlite_db() as session:
        session.add(
            UsageObservation(
                data_source_id=source_id, provider="anthropic", metric="input_tokens",
                value=1.0, unit="tokens", kind="delta", source="hermes",
                observed_at=now, source_event_id="dup-1",
            )
        )
        await session.commit()
        session.add(
            UsageObservation(
                data_source_id=source_id, provider="anthropic", metric="input_tokens",
                value=1.0, unit="tokens", kind="delta", source="hermes",
                observed_at=now, source_event_id="dup-1",
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()
