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
from app.datasources.service import _persist_observations, sync_data_source
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


@pytest.mark.asyncio
async def test_sync_result_reports_diagnostics(sqlite_db, monkeypatch):
    class FakeHermes:
        async def fetch_observations(self, base_url, token, extra, timeout):
            return [
                _record(event_id="evt-1", input_tokens=100, output_tokens=50, requests=1),
                _record(event_id="evt-2", provider="mystery", profile="blocked", input_tokens=9),
                _record(timestamp="not-a-date", event_id="bad-time", input_tokens=1),
                _record(event_id="bad-metric", input_tokens="nope"),
                _record(event_id="empty", input_tokens=None),
            ]

    monkeypatch.setattr("app.datasources.service.get_data_source", lambda kind: FakeHermes)
    source_id = await _make_source(sqlite_db)
    async with sqlite_db() as session:
        source = await session.get(DataSourceConfig, source_id)
        source.extra = {"profiles": ["coder"], "provider_mappings": {"mystery": "missing-provider"}}
        session.add(ProviderConfig(provider="anthropic", label="main", encrypted_api_key="encrypted", is_enabled=True))
        await session.commit()

    async with sqlite_db() as session:
        source = await session.get(DataSourceConfig, source_id)
        result = await sync_data_source(session, source, crypto=type("C", (), {"decrypt": lambda self, value: value})())

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
        duplicate = await sync_data_source(session, source, crypto=type("C", (), {"decrypt": lambda self, value: value})())
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
        session.add(ProviderConfig(provider="anthropic", label="main", encrypted_api_key="encrypted", is_enabled=True))
        await session.commit()

    async with sqlite_db() as session:
        source = await session.get(DataSourceConfig, source_id)
        result = await sync_data_source(session, source, crypto=type("C", (), {"decrypt": lambda self, value: value})())

    assert result["status"] == "healthy"
    assert result["providers_discovered"] == ["mystery"]
    assert result["unmapped_providers"] == []


@pytest.mark.asyncio
async def test_data_source_observations_endpoint_returns_safe_recent_rows(sqlite_db):
    source_id, provider_id = await _seed_source_and_provider(sqlite_db)
    await _seed_observations(sqlite_db, source_id, provider_id)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/api/v1/datasources/configs/{source_id}/observations?limit=2", headers=AUTH)

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


async def _persist(Session, source_id, records):
    observations = expand_observation_records(records)
    async with Session() as session:
        source = await session.get(DataSourceConfig, source_id)
        return (await _persist_observations(session, source, observations))["inserted"]


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
            await session.execute(
                select(UsageObservation.source_event_id).where(UsageObservation.data_source_id == source_id)
            )
        ).scalars().all()
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
        result = await sync_data_source(session, source, crypto=type("C", (), {"decrypt": lambda self, value: value})())

    assert result["status"] == "error"
    assert result["error"] == "synthetic persistence failure"

    async with sqlite_db() as session:
        source = await session.get(DataSourceConfig, source_id)
        assert source.consecutive_failures == 1
        assert source.latest_error == "synthetic persistence failure"
        assert source.last_failure_at is not None
