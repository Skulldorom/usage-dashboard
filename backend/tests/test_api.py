import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import perf_counter

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import Settings, settings
from app.database import get_session
from app.main import app
from app.models import Base, ProviderConfig, UsageSnapshot
from app.providers.base import Metric, ProviderAdapter, ProviderUsage
from app.providers.registry import ADAPTERS

DB = Path("/tmp/usage_dashboard_test_api.db")
TEST_DATABASE_URL = f"sqlite+aiosqlite:///{DB}"


@pytest_asyncio.fixture(autouse=True)
async def sqlite_db(monkeypatch):
    monkeypatch.setattr(settings, "admin_token", "test-admin-token-123")
    monkeypatch.setattr(settings, "homepage_allowed_hosts_raw", "")
    monkeypatch.setattr(settings, "snapshot_retention_days", 90)
    if DB.exists():
        DB.unlink()
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async def override_session():
        async with Session() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    yield Session
    app.dependency_overrides.clear()
    await engine.dispose()
    if DB.exists():
        DB.unlink()


class FakeAdapter(ProviderAdapter):
    id = "fake"
    name = "Fake"
    description = "Fake test provider"
    default_base_url = "https://fake.example"
    metric_names = ["remaining"]

    async def fetch_usage(self) -> ProviderUsage:
        await asyncio.sleep(float(self.extra.get("delay", 0)))
        if self.api_key == "bad-key":
            raise ValueError("invalid test key")
        return ProviderUsage(
            status="healthy",
            summary=f"{self.api_key} ok",
            metrics=[Metric(label="remaining", value=42, unit="credits", maximum=100)],
            raw={"ok": True},
        )


@pytest.mark.asyncio
async def test_config_crud_and_homepage():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        providers = await client.get("/api/v1/providers")
        assert providers.status_code == 200
        auth = {"Authorization": "Bearer test-admin-token-123"}
        created = await client.post("/api/v1/configs", json={"provider": "deepseek", "label": "main", "api_key": "sk-test"}, headers=auth)
        assert created.status_code == 201, created.text
        payload = created.json()
        assert payload["api_key_masked"] == "••••••••"
        assert "api_key" not in payload
        configs = await client.get("/api/v1/configs", headers=auth)
        assert len(configs.json()) == 1
        homepage = await client.get("/api/v1/homepage", headers=auth)
        assert homepage.status_code == 200
        assert homepage.json()["configured_providers"] == 1
        deleted = await client.delete(f"/api/v1/configs/{payload['id']}", headers=auth)
        assert deleted.status_code == 204


@pytest.mark.asyncio
async def test_create_config_auto_fills_blank_labels():
    auth = {"Authorization": "Bearer test-admin-token-123"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first = await client.post("/api/v1/configs", json={"provider": "deepseek", "label": "", "api_key": "sk-test"}, headers=auth)
        second = await client.post("/api/v1/configs", json={"provider": "deepseek", "api_key": "sk-test-2"}, headers=auth)

    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert first.json()["label"] == "main"
    assert second.json()["label"] == "deepseek-2"


@pytest.mark.asyncio
async def test_poll_status_reports_auto_poll_schedule(monkeypatch):
    from app.api import routes

    monkeypatch.setattr(settings, "auto_poll_enabled", True)
    monkeypatch.setattr(settings, "auto_poll_interval_minutes", 15)
    monkeypatch.setattr(routes, "_last_auto_polled_at", datetime(2026, 8, 14, 12, 0, tzinfo=UTC))
    monkeypatch.setattr(routes, "_next_auto_poll_at", datetime(2026, 8, 14, 12, 15, tzinfo=UTC))

    auth = {"Authorization": "Bearer test-admin-token-123"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/poll/status", headers=auth)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["auto_poll_enabled"] is True
    assert payload["interval_seconds"] == 900
    assert payload["last_polled_at"] == "2026-08-14T12:00:00+00:00"
    assert payload["next_poll_at"] == "2026-08-14T12:15:00+00:00"


@pytest.mark.asyncio
async def test_patch_config_base_url_null_clears_override(sqlite_db):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        auth = {"Authorization": "Bearer test-admin-token-123"}
        created = await client.post(
            "/api/v1/configs",
            json={
                "provider": "deepseek",
                "label": "main",
                "api_key": "sk-test",
                "base_url": "https://api.example.test",
            },
            headers=auth,
        )
        assert created.status_code == 201, created.text
        config_id = created.json()["id"]

        updated = await client.patch(f"/api/v1/configs/{config_id}", json={"base_url": None}, headers=auth)
        assert updated.status_code == 200, updated.text
        assert updated.json()["base_url"] is None

    async with sqlite_db() as session:
        db_base_url = await session.scalar(select(ProviderConfig.base_url).where(ProviderConfig.id == config_id))
    assert db_base_url is None


def test_blank_admin_token_env_is_treated_as_unconfigured():
    configured = Settings(ENCRYPTION_KEY="x" * 32, ADMIN_TOKEN="")
    assert configured.admin_token is None


@pytest.mark.asyncio
async def test_protected_routes_require_admin_auth():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        unauthorized = await client.get("/api/v1/configs")
        assert unauthorized.status_code == 401

        bad_token = await client.get("/api/v1/usage", headers={"Authorization": "Bearer wrong-token"})
        assert bad_token.status_code == 401

        homepage_without_auth = await client.get("/api/v1/homepage")
        assert homepage_without_auth.status_code == 401

        authorized = await client.get("/api/v1/homepage", headers={"Authorization": "Bearer test-admin-token-123"})
        assert authorized.status_code == 200


@pytest.mark.asyncio
async def test_homepage_allows_configured_hosts_without_admin_auth(monkeypatch):
    monkeypatch.setattr(settings, "homepage_allowed_hosts_raw", "usage.example.com,status.local")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://usage.example.com") as client:
        whitelisted = await client.get("/api/v1/homepage")
        assert whitelisted.status_code == 200, whitelisted.text

        with_port = await client.get("/api/v1/homepage", headers={"host": "status.local:3000"})
        assert with_port.status_code == 200, with_port.text

        not_whitelisted = await client.get("/api/v1/homepage", headers={"host": "private.example.com"})
        assert not_whitelisted.status_code == 401

        configs = await client.get("/api/v1/configs", headers={"host": "usage.example.com"})
        assert configs.status_code == 401


@pytest.mark.asyncio
async def test_homepage_provider_list_has_enabled_rows_with_preferred_usage(sqlite_db):
    now = datetime.now(UTC)
    async with sqlite_db() as session:
        firecrawl = ProviderConfig(provider="firecrawl", label="main", encrypted_api_key="encrypted", is_enabled=True)
        disabled = ProviderConfig(provider="deepseek", label="disabled", encrypted_api_key="encrypted", is_enabled=False)
        no_snapshot = ProviderConfig(provider="fake", label="scratch", encrypted_api_key="encrypted", is_enabled=True)
        session.add_all([firecrawl, disabled, no_snapshot])
        await session.flush()
        session.add_all([
            UsageSnapshot(
                provider_config_id=firecrawl.id,
                provider="firecrawl",
                status="healthy",
                summary="generic account summary",
                metrics=[
                    {"label": "usage_percent", "value": 82, "unit": "%"},
                    {"label": "credits_remaining", "value": 1200, "unit": "credits"},
                ],
                raw={},
                checked_at=now,
            ),
            UsageSnapshot(
                provider_config_id=disabled.id,
                provider="deepseek",
                status="healthy",
                summary="should not render",
                metrics=[{"label": "credits_remaining", "value": 999, "unit": "credits"}],
                raw={},
                checked_at=now,
            ),
        ])
        await session.commit()

    auth = {"Authorization": "Bearer test-admin-token-123"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/homepage", headers=auth)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["configured_providers"] == 3
    assert payload["summary"] == "2/3 providers healthy"
    assert payload["list"] == [
        {
            "provider": "firecrawl",
            "config_id": firecrawl.id,
            "label": "firecrawl (main)",
            "value": "1.2k credits left",
            "status": "healthy",
        },
        {
            "provider": "fake",
            "config_id": no_snapshot.id,
            "label": "fake (scratch)",
            "value": "No usage snapshot yet",
            "status": "unknown",
        },
    ]


@pytest.mark.asyncio
async def test_config_order_and_visibility_controls_dashboard_and_homepage(sqlite_db):
    now = datetime.now(UTC)
    async with sqlite_db() as session:
        first = ProviderConfig(provider="fake", label="first", encrypted_api_key="encrypted", is_enabled=True, is_visible=True, display_order=0)
        second = ProviderConfig(provider="fake", label="second", encrypted_api_key="encrypted", is_enabled=True, is_visible=False, display_order=1)
        third = ProviderConfig(provider="fake", label="third", encrypted_api_key="encrypted", is_enabled=False, is_visible=True, display_order=2)
        session.add_all([first, second, third])
        await session.flush()
        session.add_all([
            UsageSnapshot(provider_config_id=first.id, provider="fake", status="healthy", summary="first", metrics=[{"label": "remaining", "value": 1}], raw={}, checked_at=now),
            UsageSnapshot(provider_config_id=second.id, provider="fake", status="healthy", summary="second", metrics=[{"label": "remaining", "value": 2}], raw={}, checked_at=now),
            UsageSnapshot(provider_config_id=third.id, provider="fake", status="healthy", summary="third", metrics=[{"label": "remaining", "value": 3}], raw={}, checked_at=now),
        ])
        await session.commit()
        ids = {"first": first.id, "second": second.id, "third": third.id}

    auth = {"Authorization": "Bearer test-admin-token-123"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        reordered = await client.patch("/api/v1/configs/order", json={"config_ids": [ids["third"], ids["first"], ids["second"]]}, headers=auth)
        assert reordered.status_code == 200, reordered.text
        assert [row["label"] for row in reordered.json()] == ["third", "first", "second"]
        assert [row["display_order"] for row in reordered.json()] == [0, 1, 2]

        usage_response = await client.get("/api/v1/usage", headers=auth)
        assert usage_response.status_code == 200, usage_response.text
        usage_rows = usage_response.json()
        assert [row["config"]["label"] for row in usage_rows] == ["third", "first", "second"]
        assert usage_rows[0]["config"]["is_visible"] is True
        assert usage_rows[2]["config"]["is_visible"] is False

        homepage_response = await client.get("/api/v1/homepage", headers=auth)
        assert homepage_response.status_code == 200, homepage_response.text
        homepage_rows = homepage_response.json()["list"]
        assert [row["label"] for row in homepage_rows] == ["fake (first)", "fake (second)"]


@pytest.mark.asyncio
async def test_missing_admin_token_returns_401_but_whitelisted_homepage_still_loads(monkeypatch):
    monkeypatch.setattr(settings, "admin_token", None)
    monkeypatch.setattr(settings, "homepage_allowed_hosts_raw", "usage.example.com")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://usage.example.com") as client:
        homepage = await client.get("/api/v1/homepage")
        assert homepage.status_code == 200, homepage.text

        configs = await client.get("/api/v1/configs")
        assert configs.status_code == 401

        homepage_from_other_host = await client.get("/api/v1/homepage", headers={"host": "admin.example.com"})
        assert homepage_from_other_host.status_code == 401


@pytest.mark.asyncio
async def test_config_history_returns_recent_snapshots_in_ascending_order():
    now = datetime.now(UTC)
    engine = create_async_engine(TEST_DATABASE_URL)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        config = ProviderConfig(provider="firecrawl", label="main", encrypted_api_key="encrypted")
        session.add(config)
        await session.flush()
        snapshots = [
            UsageSnapshot(provider_config_id=config.id, provider="firecrawl", status="healthy", summary="old", metrics=[{"label": "remaining_tokens", "value": 900}], raw={}, checked_at=now - timedelta(hours=8)),
            UsageSnapshot(provider_config_id=config.id, provider="firecrawl", status="healthy", summary="new", metrics=[{"label": "remaining_tokens", "value": 700}], raw={}, checked_at=now - timedelta(hours=1)),
            UsageSnapshot(provider_config_id=config.id, provider="firecrawl", status="healthy", summary="outside", metrics=[{"label": "remaining_tokens", "value": 1000}], raw={}, checked_at=now - timedelta(hours=48)),
        ]
        session.add_all(snapshots)
        await session.commit()
        config_id = config.id
    await engine.dispose()

    auth = {"Authorization": "Bearer test-admin-token-123"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/api/v1/configs/{config_id}/history", params={"hours": 24, "limit": 1}, headers=auth)
        assert response.status_code == 200, response.text
        payload = response.json()
        assert [snapshot["summary"] for snapshot in payload] == ["old"]

        response = await client.get(f"/api/v1/configs/{config_id}/history", params={"hours": 24, "limit": 10}, headers=auth)
        assert response.status_code == 200, response.text
        payload = response.json()
        assert [snapshot["summary"] for snapshot in payload] == ["old", "new"]
        assert all(snapshot["provider_config_id"] == config_id for snapshot in payload)


@pytest.mark.asyncio
async def test_config_history_requires_admin_auth():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        unauthorized = await client.get("/api/v1/configs/1/history")
        assert unauthorized.status_code == 401


@pytest.mark.asyncio
async def test_config_test_endpoint_returns_usage_without_persisting(monkeypatch):
    monkeypatch.setitem(ADAPTERS, FakeAdapter.id, FakeAdapter)
    auth = {"Authorization": "Bearer test-admin-token-123"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        tested = await client.post("/api/v1/configs/test", json={"provider": "fake", "label": "scratch", "api_key": "good-key"}, headers=auth)
        assert tested.status_code == 200, tested.text
        assert tested.json()["summary"] == "good-key ok"
        assert tested.json()["metrics"][0]["value"] == 42

        failed = await client.post("/api/v1/configs/test", json={"provider": "fake", "label": "scratch", "api_key": "bad-key"}, headers=auth)
        assert failed.status_code == 400
        assert "invalid test key" in failed.text

        configs = await client.get("/api/v1/configs", headers=auth)
        assert configs.json() == []


@pytest.mark.asyncio
async def test_poll_all_polls_enabled_configs_in_parallel(monkeypatch):
    monkeypatch.setitem(ADAPTERS, FakeAdapter.id, FakeAdapter)
    auth = {"Authorization": "Bearer test-admin-token-123"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for idx in range(3):
            created = await client.post("/api/v1/configs", json={"provider": "fake", "label": f"provider-{idx}", "api_key": f"key-{idx}", "extra": {"delay": 0.15}}, headers=auth)
            assert created.status_code == 201, created.text

        start = perf_counter()
        polled = await client.post("/api/v1/poll", headers=auth)
        elapsed = perf_counter() - start

        assert polled.status_code == 200, polled.text
        assert len(polled.json()) == 3
        assert elapsed < 0.35


@pytest.mark.asyncio
async def test_snapshot_retention_prunes_old_rows_but_preserves_each_latest(monkeypatch):
    monkeypatch.setitem(ADAPTERS, FakeAdapter.id, FakeAdapter)
    monkeypatch.setattr(settings, "snapshot_retention_days", 0)
    auth = {"Authorization": "Bearer test-admin-token-123"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first = await client.post("/api/v1/configs", json={"provider": "fake", "label": "polled", "api_key": "good-key"}, headers=auth)
        second = await client.post("/api/v1/configs", json={"provider": "fake", "label": "old-only", "api_key": "good-key"}, headers=auth)
        assert first.status_code == 201, first.text
        assert second.status_code == 201, second.text
        first_id = first.json()["id"]
        second_id = second.json()["id"]

        engine = create_async_engine(TEST_DATABASE_URL)
        Session = async_sessionmaker(engine, expire_on_commit=False)
        old_time = datetime.now(UTC) - timedelta(days=30)
        async with Session() as session:
            session.add_all([
                UsageSnapshot(provider_config_id=first_id, provider="fake", status="healthy", summary="old polled", metrics=[], raw={}, checked_at=old_time),
                UsageSnapshot(provider_config_id=second_id, provider="fake", status="healthy", summary="old only", metrics=[], raw={}, checked_at=old_time),
            ])
            await session.commit()

        polled = await client.post(f"/api/v1/configs/{first_id}/poll", headers=auth)
        assert polled.status_code == 200, polled.text

        async with Session() as session:
            snapshot_count = await session.scalar(select(func.count()).select_from(UsageSnapshot))
        await engine.dispose()
        assert snapshot_count == 2

        usage = await client.get("/api/v1/usage", headers=auth)
        assert usage.status_code == 200, usage.text
        latest_by_label = {item["config"]["label"]: item["latest"] for item in usage.json()}
        assert latest_by_label["polled"]["summary"] == "good-key ok"
        assert latest_by_label["old-only"]["summary"] == "old only"
