"""Tests for the data source abstraction, ingestion, and Hermes API."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import pytest_asyncio
import httpx
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.auth import _hash_secret
from app.core.config import settings
from app.database import get_session
from app.datasources.base import DataSourceFetchResult, expand_observation_records
from app.datasources.base import DataSourceRetryError
from app.datasources.ninerouter import NineRouterDataSource
from app.datasources.service import _persist_observations, sync_data_source
from app.main import app
from app.models import (
    AdminCredential,
    Base,
    DataSourceConfig,
    ProviderConfig,
    UsageObservation,
)

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
                    {
                        "token_hash": _hash_secret("test-admin-session-token-123"),
                        "expires_at": "2999-01-01T00:00:00+00:00",
                    }
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
        {
            "timestamp": "2026-08-22T12:00:00+00:00",
            "provider": "x",
            "input_tokens": "NaN",
        },
        {
            "timestamp": "2026-08-22T12:00:00+00:00",
            "provider": "x",
        },  # no numeric metrics
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
        provider = ProviderConfig(
            provider="anthropic",
            label="main",
            encrypted_api_key="encrypted",
            is_enabled=True,
        )
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
        catalog_by_id = {item["id"]: item for item in catalog.json()}
        assert catalog_by_id["hermes"]["default_poll_interval_minutes"] == 60
        assert catalog_by_id["9router"]["default_poll_interval_minutes"] == 1

        created = await client.post(
            "/api/v1/datasources/configs",
            json={
                "kind": "hermes",
                "base_url": "http://hermes.local",
                "token": "secret-token",
                "mute_unmapped_provider_alerts": True,
            },
            headers=AUTH,
        )
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["token_masked"] == "••••••••"
        assert "token" not in body
        assert body["mute_unmapped_provider_alerts"] is True
        assert body["poll_interval_minutes"] == 60
        assert body["status"]["status"] == "never_connected"

        updated = await client.patch(
            f"/api/v1/datasources/configs/{body['id']}",
            json={"mute_unmapped_provider_alerts": False},
            headers=AUTH,
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["mute_unmapped_provider_alerts"] is False

        status = await client.get(f"/api/v1/datasources/configs/{body['id']}/status", headers=AUTH)
        assert status.json()["status"] == "never_connected"

        deleted = await client.delete(f"/api/v1/datasources/configs/{body['id']}", headers=AUTH)
        assert deleted.status_code == 204


@pytest.mark.asyncio
async def test_ninerouter_connection_inspection_accepts_paginated_result(sqlite_db, monkeypatch):
    async def fake_fetch(self, base_url, token, extra, timeout):
        return DataSourceFetchResult(records=[{"id": "1"}], cursor="1")

    monkeypatch.setattr(NineRouterDataSource, "fetch_observations", fake_fetch)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = await client.post(
            "/api/v1/datasources/configs",
            json={"kind": "9router", "base_url": "http://router.local", "token": "dashboard-password"},
            headers=AUTH,
        )
        assert created.status_code == 201, created.text
        assert created.json()["poll_interval_minutes"] == 1
        response = await client.post(f"/api/v1/datasources/configs/{created.json()['id']}/test", headers=AUTH)

    assert response.status_code == 200, response.text
    assert response.json() == {"ok": True, "records": 1}


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

        # Estimated cost from model + token classes (claude-sonnet-4 pricing).
        estimate = body["cost_estimate"]
        assert estimate is not None
        assert estimate["currency"] == "USD"
        assert estimate["pricing_version"]
        # input 1000 → 0.003, output 500 → 0.0075, total 0.0105
        assert estimate["total_cost"] == 0.0105
        assert estimate["total_tokens"] == 1500.0
        assert estimate["unpriced_tokens"] == 0.0
        assert len(estimate["groups"]) == 1
        assert estimate["groups"][0]["provider"] == "anthropic"
        assert estimate["groups"][0]["model"] == "claude-sonnet-4"
        by_model = {row["key"]: row for row in body["by_model"]}
        assert by_model["claude-sonnet-4"]["estimated_cost"] == 0.0105
        by_provider = {row["key"]: row for row in body["by_provider"]}
        assert by_provider["anthropic"]["estimated_cost"] == 0.0105

        attribution = await client.get(f"/api/v1/analytics/providers/{provider_id}/attribution", headers=AUTH)
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


@pytest.mark.asyncio
async def test_sync_result_reports_diagnostics(sqlite_db, monkeypatch):
    class FakeHermes:
        async def fetch_observations(self, base_url, token, extra, timeout):
            return [
                _record(event_id="evt-1", input_tokens=100, output_tokens=50, requests=1),
                _record(
                    event_id="evt-2",
                    provider="mystery",
                    profile="blocked",
                    input_tokens=9,
                ),
                _record(timestamp="not-a-date", event_id="bad-time", input_tokens=1),
                _record(event_id="bad-metric", input_tokens="nope"),
                _record(event_id="empty", input_tokens=None),
            ]

    monkeypatch.setattr("app.datasources.service.get_data_source", lambda kind: FakeHermes)
    source_id = await _make_source(sqlite_db)
    async with sqlite_db() as session:
        source = await session.get(DataSourceConfig, source_id)
        source.extra = {
            "profiles": ["coder"],
            "provider_mappings": {"mystery": "missing-provider"},
        }
        session.add(
            ProviderConfig(
                provider="anthropic",
                label="main",
                encrypted_api_key="encrypted",
                is_enabled=True,
            )
        )
        await session.commit()

    async with sqlite_db() as session:
        source = await session.get(DataSourceConfig, source_id)
        result = await sync_data_source(
            session,
            source,
            crypto=type("C", (), {"decrypt": lambda self, value: value})(),
        )

    assert result["status"] == "healthy"
    assert result["records_fetched"] == 5
    assert result["observations_produced"] == 4
    assert result["observations_accepted"] == 3
    assert result["inserted"] == 3
    assert result["duplicates_skipped"] == 0
    assert result["records_skipped_invalid_timestamp"] == 1
    assert result["metrics_skipped_invalid"] == 1
    assert result["observations_skipped_profile_filter"] == 1
    assert result["providers_discovered"] == ["anthropic", "mystery"]
    assert result["profiles_discovered"] == ["blocked", "coder"]
    assert result["unmapped_providers"] == ["mystery"]
    assert result["earliest_observation_at"] is not None
    assert result["latest_observation_at"] is not None

    async with sqlite_db() as session:
        source = await session.get(DataSourceConfig, source_id)
        duplicate = await sync_data_source(
            session,
            source,
            crypto=type("C", (), {"decrypt": lambda self, value: value})(),
        )
    assert duplicate["inserted"] == 0
    assert duplicate["duplicates_skipped"] == 3


@pytest.mark.asyncio
async def test_sync_result_can_mute_unmapped_provider_alerts(sqlite_db, monkeypatch):
    class FakeHermes:
        async def fetch_observations(self, base_url, token, extra, timeout):
            return [_record(event_id="evt-1", provider="mystery", input_tokens=100)]

    monkeypatch.setattr("app.datasources.service.get_data_source", lambda kind: FakeHermes)
    source_id = await _make_source(sqlite_db)
    async with sqlite_db() as session:
        source = await session.get(DataSourceConfig, source_id)
        source.extra = {"mute_unmapped_provider_alerts": True}
        session.add(
            ProviderConfig(
                provider="anthropic",
                label="main",
                encrypted_api_key="encrypted",
                is_enabled=True,
            )
        )
        await session.commit()

    async with sqlite_db() as session:
        source = await session.get(DataSourceConfig, source_id)
        result = await sync_data_source(
            session,
            source,
            crypto=type("C", (), {"decrypt": lambda self, value: value})(),
        )

    assert result["status"] == "healthy"
    assert result["providers_discovered"] == ["mystery"]
    assert result["unmapped_providers"] == []


@pytest.mark.asyncio
async def test_data_source_observations_endpoint_returns_safe_recent_rows(sqlite_db):
    source_id, provider_id = await _seed_source_and_provider(sqlite_db)
    await _seed_observations(sqlite_db, source_id, provider_id)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            f"/api/v1/datasources/configs/{source_id}/observations?limit=2",
            headers=AUTH,
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["source"]["id"] == source_id
    assert len(body["observations"]) == 2
    first = body["observations"][0]
    assert set(first) == {
        "id",
        "observed_at",
        "provider",
        "provider_mapping",
        "model",
        "profile",
        "session_id",
        "metric",
        "value",
        "unit",
        "cost_type",
        "source_event_id",
    }
    assert "raw" not in first
    assert "token" not in first


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


async def _persist_result(Session, source_id, records):
    observations = expand_observation_records(records)
    async with Session() as session:
        source = await session.get(DataSourceConfig, source_id)
        return await _persist_observations(session, source, observations)


async def _persist(Session, source_id, records):
    return (await _persist_result(Session, source_id, records))["inserted"]


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
    inserted = await _persist(
        sqlite_db,
        source_id,
        [_record(model="claude-sonnet-4"), _record(model="claude-opus-4")],
    )
    assert inserted == 2


@pytest.mark.asyncio
async def test_explicit_event_id_dedupes(sqlite_db):
    source_id = await _make_source(sqlite_db)
    assert await _persist(sqlite_db, source_id, [_record(event_id="evt-1")]) == 1
    assert await _persist(sqlite_db, source_id, [_record(event_id="evt-1")]) == 0


@pytest.mark.asyncio
async def test_long_explicit_event_id_is_preserved_and_deduped(sqlite_db):
    source_id = await _make_source(sqlite_db)
    long_event_id = "dcff445dee81ac202a47ae878e64fa9a725f870d12f42a58" * 2

    assert await _persist(sqlite_db, source_id, [_record(event_id=long_event_id)]) == 1
    assert await _persist(sqlite_db, source_id, [_record(event_id=long_event_id)]) == 0

    async with sqlite_db() as session:
        stored_id = await session.scalar(
            select(UsageObservation.source_event_id).where(UsageObservation.data_source_id == source_id)
        )

    assert stored_id == f"{long_event_id}:input_tokens"
    assert len(stored_id) > 64


@pytest.mark.asyncio
async def test_explicit_event_id_preserves_all_metrics(sqlite_db):
    """One Hermes event expands into several metric rows; they must not collide.

    A single event_id on a multi-metric record must persist every metric (the
    source_event_id is metric-suffixed), and a re-sync must remain idempotent.
    """
    source_id = await _make_source(sqlite_db)
    record = _record(event_id="evt-1", input_tokens=100, output_tokens=40, cost=0.01)

    assert await _persist(sqlite_db, source_id, [record]) == 3  # input, output, cost
    assert await _persist(sqlite_db, source_id, [record]) == 0

    async with sqlite_db() as session:
        ids = (
            (
                await session.execute(
                    select(UsageObservation.source_event_id).where(UsageObservation.data_source_id == source_id)
                )
            )
            .scalars()
            .all()
        )
    assert sorted(ids) == ["evt-1:cost", "evt-1:input_tokens", "evt-1:output_tokens"]


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
                data_source_id=source_id,
                provider="anthropic",
                metric="input_tokens",
                value=1.0,
                unit="tokens",
                kind="delta",
                source="hermes",
                observed_at=now,
                source_event_id="dup-1",
            )
        )
        await session.commit()
        session.add(
            UsageObservation(
                data_source_id=source_id,
                provider="anthropic",
                metric="input_tokens",
                value=1.0,
                unit="tokens",
                kind="delta",
                source="hermes",
                observed_at=now,
                source_event_id="dup-1",
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


@pytest.mark.asyncio
async def test_sync_failure_rolls_back_before_updating_source_state(sqlite_db, monkeypatch):
    class FakeHermes:
        async def fetch_observations(self, base_url, token, extra, timeout):
            return [_record(event_id="evt-fail")]

    async def failed_persist(session, source, observations):
        session.add(UsageObservation(data_source_id=source.id))
        try:
            await session.commit()
        except IntegrityError as exc:
            raise RuntimeError("synthetic persistence failure") from exc

    monkeypatch.setattr("app.datasources.service.get_data_source", lambda kind: FakeHermes)
    monkeypatch.setattr("app.datasources.service._persist_observations", failed_persist)
    source_id = await _make_source(sqlite_db)

    async with sqlite_db() as session:
        source = await session.get(DataSourceConfig, source_id)
        result = await sync_data_source(
            session,
            source,
            crypto=type("C", (), {"decrypt": lambda self, value: value})(),
        )

    assert result["status"] == "error"
    assert result["error"] == "synthetic persistence failure"

    async with sqlite_db() as session:
        source = await session.get(DataSourceConfig, source_id)
        assert source.consecutive_failures == 1
        assert source.latest_error == "synthetic persistence failure"
        assert source.last_failure_at is not None


@pytest.mark.asyncio
async def test_long_session_id_is_preserved_and_resync_remains_idempotent(sqlite_db):
    source_id = await _make_source(sqlite_db)
    session_id = "hermes:company:" + "x" * 140
    record = _record(event_id="evt-long-session", session_id=session_id)

    assert await _persist(sqlite_db, source_id, [record]) == 1
    duplicate = await _persist_result(sqlite_db, source_id, [record])
    assert duplicate == {"inserted": 0, "duplicates_skipped": 1, "invalid_fields_skipped": 0}

    async with sqlite_db() as session:
        stored_session_id = await session.scalar(
            select(UsageObservation.session_id).where(UsageObservation.data_source_id == source_id)
        )

    assert stored_session_id == session_id
    assert len(stored_session_id) > 128


@pytest.mark.asyncio
async def test_sync_skips_malformed_row_without_blocking_valid_observations(sqlite_db, monkeypatch):
    class FakeHermes:
        async def fetch_observations(self, base_url, token, extra, timeout):
            return [
                _record(event_id="evt-valid", input_tokens=100),
                _record(event_id="evt-malformed", model="x" * 129, input_tokens=50),
            ]

    monkeypatch.setattr("app.datasources.service.get_data_source", lambda kind: FakeHermes)
    source_id = await _make_source(sqlite_db)

    async with sqlite_db() as session:
        source = await session.get(DataSourceConfig, source_id)
        result = await sync_data_source(
            session,
            source,
            crypto=type("C", (), {"decrypt": lambda self, value: value})(),
        )

    assert result["status"] == "healthy"
    assert result["inserted"] == 1
    assert result["observations_skipped_invalid_fields"] == 1

    async with sqlite_db() as session:
        valid = await session.scalar(
            select(UsageObservation).where(UsageObservation.source_event_id == "evt-valid:input_tokens")
        )
        assert valid is not None
        assert valid.value == 100

    async with sqlite_db() as session:
        source = await session.get(DataSourceConfig, source_id)
        assert source.last_success_at is not None
        assert source.consecutive_failures == 0
        assert await _count(sqlite_db, source_id) == 1

        duplicate = await sync_data_source(
            session,
            source,
            crypto=type("C", (), {"decrypt": lambda self, value: value})(),
        )

    assert duplicate["status"] == "healthy"
    assert duplicate["inserted"] == 0
    assert duplicate["duplicates_skipped"] == 1
    assert duplicate["observations_skipped_invalid_fields"] == 1


def test_ninerouter_catalog_is_registered():
    from app.datasources.registry import list_data_sources

    assert any(item["id"] == "9router" for item in list_data_sources())


@pytest.mark.asyncio
async def test_ninerouter_adapter_uses_fixed_window_and_discards_sensitive_detail_fields(monkeypatch):
    class Response:
        def __init__(self, payload, status_code=200):
            self.payload = payload
            self.status_code = status_code

        def json(self):
            return self.payload

    class Cookie:
        name = "auth_token"
        value = "ephemeral-session"

    class Client:
        def __init__(self):
            self.pages = []
            self.cookies = type("Cookies", (), {"jar": [Cookie()]})()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, json):
            assert url == "http://router.test/api/auth/login"
            assert json == {"password": "secret"}
            return Response({"success": True})

        async def get(self, url, params):
            assert url == "http://router.test/api/usage/request-details"
            self.pages.append(params.copy())
            if params["page"] == 1:
                return Response(
                    {
                        "details": [
                            {
                                "id": "2026-10-18T12:00:00.000Z-a-cls",
                                "timestamp": "2026-10-18T12:00:00Z",
                                "provider": "OpenRouter",
                                "model": "anthropic/claude-sonnet-4",
                                "connectionId": "provider-account-not-a-session",
                                "tokens": {
                                    "prompt_tokens": 11,
                                    "completion_tokens": 7,
                                    "cached_tokens": 3,
                                },
                                "request": {"prompt": "SUPER_SECRET_PROMPT"},
                                "providerRequest": {"key": "SUPER_SECRET_API_KEY"},
                                "providerResponse": {"text": "SUPER_SECRET_RESPONSE"},
                                "response": {"text": "SUPER_SECRET_RESPONSE"},
                            }
                        ],
                        "pagination": {"page": 1, "pageSize": 100, "totalItems": 101, "totalPages": 2, "hasNext": True},
                    }
                )
            return Response(
                {
                    "details": [
                        {
                            "id": "2026-10-18T12:01:00.000Z-b-gpt",
                            "timestamp": "2026-10-18T12:01:00Z",
                            "provider": "openai",
                            "model": "gpt-5",
                            "connectionId": "another-provider-account",
                            "tokens": {"prompt_tokens": 0, "completion_tokens": 0},
                        }
                    ],
                    "pagination": {"page": 2, "pageSize": 100, "totalItems": 101, "totalPages": 2, "hasNext": False},
                }
            )

    client = Client()
    monkeypatch.setattr("app.datasources.ninerouter.httpx.AsyncClient", lambda **kwargs: client)
    result = await NineRouterDataSource().fetch_observations(
        "http://router.test/", "secret", {"cursor": "2026-10-18T12:10:00+00:00"}, 5
    )

    assert [page["page"] for page in client.pages] == [1, 2]
    assert all(page["pageSize"] == 100 for page in client.pages)
    assert all(page["startDate"] == "2026-10-18T12:00:00+00:00" for page in client.pages)
    assert len({page["endDate"] for page in client.pages}) == 1
    assert result.cursor == client.pages[0]["endDate"]
    assert result.records == [
        {
            "id": "2026-10-18T12:00:00.000Z-a-cls",
            "timestamp": "2026-10-18T12:00:00Z",
            "provider": "OpenRouter",
            "model": "anthropic/claude-sonnet-4",
            "requests": 1,
            "input_tokens": 11,
            "output_tokens": 7,
            "cache_read_tokens": 3,
        },
        {
            "id": "2026-10-18T12:01:00.000Z-b-gpt",
            "timestamp": "2026-10-18T12:01:00Z",
            "provider": "openai",
            "model": "gpt-5",
            "requests": 1,
        },
    ]
    assert "SUPER_SECRET_PROMPT" not in repr(result.records)
    assert "SUPER_SECRET_API_KEY" not in repr(result.records)
    assert "SUPER_SECRET_RESPONSE" not in repr(result.records)


@pytest.mark.asyncio
async def test_ninerouter_adapter_rejects_login_failure_without_a_session(monkeypatch):
    class Response:
        status_code = 200

        @staticmethod
        def json():
            return {"success": True}

    class Client:
        cookies = type("Cookies", (), {"jar": []})()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, json):
            return Response()

    monkeypatch.setattr("app.datasources.ninerouter.httpx.AsyncClient", lambda **kwargs: Client())
    with pytest.raises(ValueError, match="did not establish a session"):
        await NineRouterDataSource().fetch_observations("http://router.test", "secret", {}, 5)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "message", "retry_after"),
    [
        (401, "authentication failed", 15 * 60),
        (403, "access was denied", 30 * 60),
    ],
)
async def test_ninerouter_adapter_backoffs_persistent_login_failures(monkeypatch, status_code, message, retry_after):
    class Response:
        def __init__(self):
            self.status_code = status_code
            self.headers = {}

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, json):
            assert json == {"password": "wrong"}
            return Response()

    monkeypatch.setattr("app.datasources.ninerouter.httpx.AsyncClient", lambda **kwargs: Client())
    with pytest.raises(DataSourceRetryError, match=message) as caught:
        await NineRouterDataSource().fetch_observations("http://router.test", "wrong", {}, 5)
    assert caught.value.retry_after_seconds == retry_after
    assert "wrong" not in str(caught.value)


@pytest.mark.asyncio
@pytest.mark.parametrize("retry_after", ["120", None, "invalid", "-1"])
async def test_ninerouter_adapter_respects_login_rate_limit(monkeypatch, retry_after):
    class Response:
        status_code = 429
        headers = {} if retry_after is None else {"Retry-After": retry_after}

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, json):
            return Response()

    monkeypatch.setattr("app.datasources.ninerouter.httpx.AsyncClient", lambda **kwargs: Client())
    with pytest.raises(DataSourceRetryError, match="temporarily locked") as caught:
        await NineRouterDataSource().fetch_observations("http://router.test", "secret", {}, 5)
    assert caught.value.retry_after_seconds == (120 if retry_after == "120" else 10 * 60)
    assert "secret" not in str(caught.value)

@pytest.mark.asyncio
async def test_ninerouter_adapter_fails_when_auth_expires_during_pagination(monkeypatch):
    class Response:
        def __init__(self, payload=None, status_code=200):
            self.payload = payload
            self.status_code = status_code

        def json(self):
            return self.payload

    class Cookie:
        name = "auth_token"
        value = "ephemeral-session"

    class Client:
        cookies = type("Cookies", (), {"jar": [Cookie()]})()
        calls = 0

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, json):
            return Response({"success": True})

        async def get(self, url, params):
            self.calls += 1
            if self.calls == 1:
                return Response(
                    {"details": [], "pagination": {"page": 1, "pageSize": 100, "totalItems": 101, "totalPages": 2, "hasNext": True}}
                )
            return Response(status_code=401)

    monkeypatch.setattr("app.datasources.ninerouter.httpx.AsyncClient", lambda **kwargs: Client())
    with pytest.raises(ValueError, match="request-details returned HTTP 401"):
        await NineRouterDataSource().fetch_observations("http://router.test", "secret", {}, 5)


@pytest.mark.asyncio
async def test_ninerouter_adapter_retries_an_unstable_window_once(monkeypatch):
    class Response:
        status_code = 200

        def __init__(self, payload):
            self.payload = payload

        def json(self):
            return self.payload

    class Cookie:
        name = "auth_token"
        value = "ephemeral-session"

    class Client:
        cookies = type("Cookies", (), {"jar": [Cookie()]})()

        def __init__(self):
            self.pages = []

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, json):
            return Response({"success": True})

        async def get(self, url, params):
            self.pages.append(params.copy())
            sequence = len(self.pages)
            total = 101 if sequence in (1, 3, 4) else 100
            page = params["page"]
            return Response(
                {
                    "details": [],
                    "pagination": {
                        "page": page,
                        "pageSize": 100,
                        "totalItems": total,
                        "totalPages": 2 if total == 101 else 1,
                        "hasNext": page < (2 if total == 101 else 1),
                    },
                }
            )

    client = Client()
    monkeypatch.setattr("app.datasources.ninerouter.httpx.AsyncClient", lambda **kwargs: client)
    result = await NineRouterDataSource().fetch_observations("http://router.test", "secret", {}, 5)
    assert result.records == []
    assert [page["page"] for page in client.pages] == [1, 2, 1, 2]
    assert len({page["endDate"] for page in client.pages}) == 1


@pytest.mark.asyncio
async def test_ninerouter_adapter_rejects_persistently_unstable_pagination(monkeypatch):
    class Response:
        status_code = 200

        def __init__(self, payload):
            self.payload = payload

        def json(self):
            return self.payload

    class Cookie:
        name = "auth_token"
        value = "ephemeral-session"

    class Client:
        cookies = type("Cookies", (), {"jar": [Cookie()]})()
        call = 0

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, json):
            return Response({"success": True})

        async def get(self, url, params):
            self.call += 1
            total = 101 if self.call % 2 else 100
            return Response(
                {
                    "details": [],
                    "pagination": {
                        "page": params["page"],
                        "pageSize": 100,
                        "totalItems": total,
                        "totalPages": 2 if total == 101 else 1,
                        "hasNext": params["page"] == 1,
                    },
                }
            )

    monkeypatch.setattr("app.datasources.ninerouter.httpx.AsyncClient", lambda **kwargs: Client())
    with pytest.raises(ValueError, match="changed during pagination"):
        await NineRouterDataSource().fetch_observations("http://router.test", "secret", {}, 5)

@pytest.mark.asyncio
async def test_ninerouter_overlapping_polls_are_idempotent(sqlite_db, monkeypatch):
    class FakeNineRouter:
        async def fetch_observations(self, base_url, token, extra, timeout):
            return DataSourceFetchResult(records=[_record(event_id="detail-1", input_tokens=10)], cursor="2026-10-18T12:10:00+00:00")

    monkeypatch.setattr("app.datasources.service.get_data_source", lambda kind: FakeNineRouter)
    source_id = await _make_source(sqlite_db, name="router-overlap")
    async with sqlite_db() as session:
        source = await session.get(DataSourceConfig, source_id)
        source.kind = "9router"
        source.extra = {"cursor": "2026-10-18T12:00:00+00:00"}
        await session.commit()

    for expected_inserted in (1, 0):
        async with sqlite_db() as session:
            source = await session.get(DataSourceConfig, source_id)
            result = await sync_data_source(session, source, crypto=type("C", (), {"decrypt": lambda self, value: value})())
        assert result["status"] == "healthy"
        assert result["inserted"] == expected_inserted

    async with sqlite_db() as session:
        source = await session.get(DataSourceConfig, source_id)
        assert source.extra["cursor"] == "2026-10-18T12:10:00+00:00"
        assert await _count(sqlite_db, source_id) == 1


@pytest.mark.asyncio
async def test_cursor_advances_only_after_successful_persistence(sqlite_db, monkeypatch):
    class FakeNineRouter:
        async def fetch_observations(self, base_url, token, extra, timeout):
            return DataSourceFetchResult(records=[_record(event_id="42", input_tokens=10)], cursor="42")

    monkeypatch.setattr("app.datasources.service.get_data_source", lambda kind: FakeNineRouter)
    source_id = await _make_source(sqlite_db, name="router")
    async with sqlite_db() as session:
        source = await session.get(DataSourceConfig, source_id)
        source.kind = "9router"
        source.extra = {"cursor": "41"}
        await session.commit()

    async with sqlite_db() as session:
        source = await session.get(DataSourceConfig, source_id)
        result = await sync_data_source(session, source, crypto=type("C", (), {"decrypt": lambda self, value: value})())
    assert result["status"] == "healthy"

    async with sqlite_db() as session:
        source = await session.get(DataSourceConfig, source_id)
        assert source.extra["cursor"] == "42"
        stored = (await session.execute(select(UsageObservation).where(UsageObservation.data_source_id == source_id))).scalars().all()
        assert {row.source for row in stored} == {"9router"}
        assert {row.source_event_id for row in stored} == {"42:input_tokens"}


@pytest.mark.asyncio
async def test_cursor_is_not_advanced_when_persistence_fails(sqlite_db, monkeypatch):
    class FakeNineRouter:
        async def fetch_observations(self, base_url, token, extra, timeout):
            return DataSourceFetchResult(records=[_record(event_id="42", input_tokens=10)], cursor="42")

    async def failed_persist(session, source, observations):
        raise RuntimeError("synthetic persistence failure")

    monkeypatch.setattr("app.datasources.service.get_data_source", lambda kind: FakeNineRouter)
    monkeypatch.setattr("app.datasources.service._persist_observations", failed_persist)
    source_id = await _make_source(sqlite_db, name="router")
    async with sqlite_db() as session:
        source = await session.get(DataSourceConfig, source_id)
        source.kind = "9router"
        source.extra = {"cursor": "41"}
        await session.commit()

    async with sqlite_db() as session:
        source = await session.get(DataSourceConfig, source_id)
        result = await sync_data_source(session, source, crypto=type("C", (), {"decrypt": lambda self, value: value})())
    assert result["status"] == "error"

    async with sqlite_db() as session:
        source = await session.get(DataSourceConfig, source_id)
        assert source.extra["cursor"] == "41"

@pytest.mark.asyncio
async def test_ninerouter_adapter_requires_password_login():
    with pytest.raises(ValueError, match="dashboard password is required"):
        await NineRouterDataSource().fetch_observations("http://router.test", None, {}, 5)


@pytest.mark.asyncio
async def test_ninerouter_adapter_wraps_login_network_failure(monkeypatch):
    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, json):
            raise httpx.ConnectError("connection refused")

    monkeypatch.setattr("app.datasources.ninerouter.httpx.AsyncClient", lambda **kwargs: Client())
    with pytest.raises(ValueError, match="9Router connection failed: connection refused"):
        await NineRouterDataSource().fetch_observations("http://router.test", "secret", {}, 5)

@pytest.mark.asyncio
async def test_ninerouter_manual_connection_test_attempts_login_once_on_rate_limit(sqlite_db, monkeypatch):
    attempts = 0

    class Response:
        status_code = 429
        headers = {"Retry-After": "120"}

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, json):
            nonlocal attempts
            attempts += 1
            return Response()

    monkeypatch.setattr("app.datasources.ninerouter.httpx.AsyncClient", lambda **kwargs: Client())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = await client.post(
            "/api/v1/datasources/configs",
            json={"kind": "9router", "base_url": "http://router.test", "token": "test-password"},
            headers=AUTH,
        )
        assert created.status_code == 201, created.text
        response = await client.post(f"/api/v1/datasources/configs/{created.json()['id']}/test", headers=AUTH)

    assert response.status_code == 400
    assert attempts == 1
    assert response.json()["detail"] == "9Router dashboard login is temporarily locked. Retry after 120 seconds."
    assert "test-password" not in response.text

    async with sqlite_db() as session:
        source = await session.get(DataSourceConfig, created.json()["id"])
        assert source.next_attempt_at is not None
        assert source.next_attempt_at > source.last_failure_at


@pytest.mark.asyncio
async def test_replacing_data_source_token_clears_automatic_backoff(sqlite_db):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = await client.post(
            "/api/v1/datasources/configs",
            json={"kind": "9router", "base_url": "http://router.test", "token": "old-password"},
            headers=AUTH,
        )
        source_id = created.json()["id"]

    async with sqlite_db() as session:
        source = await session.get(DataSourceConfig, source_id)
        source.next_attempt_at = datetime.now(UTC) + timedelta(minutes=10)
        await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        updated = await client.patch(
            f"/api/v1/datasources/configs/{source_id}",
            json={"token": "corrected-password"},
            headers=AUTH,
        )

    assert updated.status_code == 200, updated.text
    assert updated.json()["status"]["next_attempt_at"] is None
    assert "corrected-password" not in updated.text
