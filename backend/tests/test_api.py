import asyncio
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import perf_counter

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import Settings, settings
from app.database import get_session
from app.main import app
from app.models import ApiToken, Base, ProviderConfig, UsageSnapshot
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
async def test_providers_include_icons():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/providers")
    assert response.status_code == 200
    by_id = {provider["id"]: provider for provider in response.json()}
    assert by_id["openai"]["icon"]["viewBox"] == "0 0 600 600"
    assert by_id["openai"]["icon"]["path"].startswith("M557 245.5")
    assert by_id["codex"]["icon"]["path"] == by_id["openai"]["icon"]["path"]
    assert by_id["anthropic"]["icon"]["viewBox"] == "0 0 600 600"
    assert by_id["deepseek"]["icon"]["viewBox"] == "0 0 600 600"
    assert by_id["openrouter"]["icon"]["viewBox"] == "0 0 24 24"
    assert by_id["firecrawl"]["icon"]["viewBox"] == "0 0 50 72"
    assert by_id["custom_http"]["icon"] is None


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
        codex = ProviderConfig(provider="codex", label="cloud", encrypted_api_key="encrypted", is_enabled=True)
        disabled = ProviderConfig(provider="deepseek", label="disabled", encrypted_api_key="encrypted", is_enabled=False)
        no_snapshot = ProviderConfig(provider="fake", label="scratch", encrypted_api_key="encrypted", is_enabled=True)
        session.add_all([firecrawl, codex, disabled, no_snapshot])
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
                provider_config_id=codex.id,
                provider="codex",
                status="healthy",
                summary="Pro - 54% session left",
                metrics=[{"label": "session_remaining_percent", "value": 54, "unit": "%", "maximum": 100}],
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
    assert payload["configured_providers"] == 4
    assert payload["summary"] == "3/4 providers healthy"
    assert payload["list"] == [
        {
            "provider": "firecrawl",
            "config_id": firecrawl.id,
            "label": "firecrawl (main)",
            "value": "82% • 1.2k credits left",
            "status": "healthy",
        },
        {
            "provider": "codex",
            "config_id": codex.id,
            "label": "codex (cloud)",
            "value": "54% left",
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
async def test_codex_provider_config_keeps_oauth_tokens_encrypted(sqlite_db):
    from app.api import routes
    from app.core.crypto import CryptoService
    from app.providers.codex import CodexCredentials

    providers = await providers_payload()
    assert any(provider["id"] == "codex" for provider in providers)

    secret = CodexCredentials(
        access_token="old-access-token",
        refresh_token="refresh-token",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        account_id="acct_123",
    ).to_secret_json()
    auth = {"Authorization": "Bearer test-admin-token-123"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        leaked_extra = await client.post(
            "/api/v1/configs/test",
            json={"provider": "codex", "label": "codex", "api_key": secret, "extra": {"refresh_token": "plaintext"}},
            headers=auth,
        )
        assert leaked_extra.status_code == 400
        assert "plaintext extra" in leaked_extra.text

        created = await client.post(
            "/api/v1/configs",
            json={"provider": "codex", "label": "codex", "api_key": secret, "extra": {"note": "safe metadata"}},
            headers=auth,
        )
        assert created.status_code == 201, created.text
        payload = created.json()
        assert payload["api_key_masked"] == "••••••••"
        assert "api_key" not in payload
        assert payload["extra"] == {"note": "safe metadata"}

    async with sqlite_db() as session:
        config = (await session.execute(select(ProviderConfig).where(ProviderConfig.id == payload["id"]))).scalar_one()
        stored_secret = CryptoService(settings.encryption_key).decrypt(config.encrypted_api_key)
        assert json.loads(stored_secret)["refresh_token"] == "refresh-token"
        assert config.extra == {"note": "safe metadata"}

    class RefreshingCodexAdapter(ProviderAdapter):
        id = "codex"
        name = "Codex"
        description = "test"
        default_base_url = "https://chatgpt.com"
        metric_names = []

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.updated_secret = CodexCredentials(
                access_token="new-access-token",
                refresh_token="new-refresh-token",
                expires_at=datetime.now(UTC) + timedelta(hours=1),
                account_id="acct_123",
            ).to_secret_json()

        async def fetch_usage(self) -> ProviderUsage:
            return ProviderUsage(status="healthy", summary="refreshed", metrics=[Metric("session_remaining_percent", 99, "%", 100)], raw={})

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setitem(ADAPTERS, "codex", RefreshingCodexAdapter)
    try:
        async with sqlite_db() as session:
            config = await session.get(ProviderConfig, payload["id"])
            snapshot = await routes._poll_one(config, session)
            assert snapshot.summary == "refreshed"
            stored_secret = CryptoService(settings.encryption_key).decrypt(config.encrypted_api_key)
            assert json.loads(stored_secret)["refresh_token"] == "new-refresh-token"
            assert "refresh_token" not in config.extra
    finally:
        monkeypatch.undo()


@pytest.mark.asyncio
async def test_codex_device_oauth_flow_returns_only_public_code_then_saves_encrypted_provider(sqlite_db, monkeypatch):
    from app.api import routes
    from app.core.crypto import CryptoService
    from app.providers.codex import CodexCredentials

    @dataclass(slots=True)
    class FakeDeviceStart:
        device_code: str = "server-only-device-code"
        user_code: str = "ABCD-1234"
        verification_uri: str = "https://auth.openai.com/codex/device"
        verification_uri_complete: str | None = "https://auth.openai.com/codex/device?user_code=ABCD-1234"
        expires_at: datetime = datetime.now(UTC) + timedelta(minutes=15)
        interval_seconds: int = 5

    async def fake_start_device_authorization(*, timeout: float):
        assert timeout == settings.request_timeout_seconds
        return FakeDeviceStart()

    async def fake_poll_device_authorization(device_code: str, *, timeout: float):
        assert device_code == "server-only-device-code"
        assert timeout == settings.request_timeout_seconds
        return {
            "status": "completed",
            "secret": CodexCredentials(
                access_token="device-access-token",
                refresh_token="device-refresh-token",
                expires_at=datetime.now(UTC) + timedelta(hours=1),
                account_id="acct_from_device",
            ).to_secret_json(),
        }

    monkeypatch.setattr(routes.codex_oauth, "start_device_authorization", fake_start_device_authorization)
    monkeypatch.setattr(routes.codex_oauth, "poll_device_authorization", fake_poll_device_authorization)

    auth = {"Authorization": "Bearer test-admin-token-123"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        started = await client.post("/api/v1/codex/oauth/device/start", headers=auth)
        assert started.status_code == 200, started.text
        start_payload = started.json()
        assert start_payload["flow_id"]
        assert start_payload["user_code"] == "ABCD-1234"
        assert start_payload["verification_uri"] == "https://auth.openai.com/codex/device"
        assert "device_code" not in started.text
        assert "access_token" not in started.text
        assert "refresh_token" not in started.text

        completed = await client.post(
            f"/api/v1/codex/oauth/device/{start_payload['flow_id']}/poll",
            json={"label": "codex-live"},
            headers=auth,
        )
        assert completed.status_code == 200, completed.text
        completed_payload = completed.json()
        assert completed_payload["status"] == "completed"
        assert completed_payload["config"]["provider"] == "codex"
        assert completed_payload["config"]["label"] == "codex-live"
        assert "access_token" not in completed.text
        assert "refresh_token" not in completed.text

    async with sqlite_db() as session:
        config = (await session.execute(select(ProviderConfig).where(ProviderConfig.provider == "codex"))).scalar_one()
        stored_secret = CryptoService(settings.encryption_key).decrypt(config.encrypted_api_key)
        assert json.loads(stored_secret)["refresh_token"] == "device-refresh-token"
        assert config.extra == {"auth_method": "device_code"}


@pytest.mark.asyncio
async def test_codex_device_oauth_poll_hides_raw_oauth_errors(monkeypatch):
    from app.api import routes

    async def fake_start_device_authorization(*, timeout: float):
        return routes.codex_oauth.CodexDeviceStart(
            device_code="device-code",
            user_code="WXYZ-9876",
            verification_uri="https://auth.openai.com/codex/device",
            verification_uri_complete=None,
            expires_at=datetime.now(UTC) + timedelta(minutes=15),
            interval_seconds=5,
        )

    async def fake_poll_device_authorization(device_code: str, *, timeout: float):
        return {"status": "pending", "interval_seconds": 5}

    monkeypatch.setattr(routes.codex_oauth, "start_device_authorization", fake_start_device_authorization)
    monkeypatch.setattr(routes.codex_oauth, "poll_device_authorization", fake_poll_device_authorization)

    auth = {"Authorization": "Bearer test-admin-token-123"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        started = await client.post("/api/v1/codex/oauth/device/start", headers=auth)
        assert started.status_code == 200, started.text
        polled = await client.post(f"/api/v1/codex/oauth/device/{started.json()['flow_id']}/poll", headers=auth)

    assert polled.status_code == 200, polled.text
    assert polled.json() == {"status": "pending", "interval_seconds": 5, "error": None, "config": None}
    assert "device-code" not in polled.text


@pytest.mark.asyncio
async def test_codex_browser_oauth_returns_only_authorization_url_then_saves_encrypted_provider(sqlite_db, monkeypatch):
    from app.api import routes
    from app.core.crypto import CryptoService
    from app.providers.codex import CodexCredentials

    async def fake_exchange(code: str, code_verifier: str, *, timeout: float):
        assert code == "browser-code"
        assert code_verifier
        assert timeout == settings.request_timeout_seconds
        return CodexCredentials(
            access_token="browser-access-token",
            refresh_token="browser-refresh-token",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            account_id="acct_browser",
        ).to_secret_json()

    monkeypatch.setattr(routes.codex_oauth, "exchange_browser_authorization_code", fake_exchange)

    auth = {"Authorization": "Bearer test-admin-token-123"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        started = await client.post("/api/v1/codex/oauth/browser/start", headers=auth)
        assert started.status_code == 200, started.text
        start_payload = started.json()
        assert start_payload["flow_id"]
        assert start_payload["authorization_url"].startswith("https://auth.openai.com/oauth/authorize?")
        assert "code_challenge=" in start_payload["authorization_url"]
        assert "code_verifier" not in started.text
        assert "browser-access-token" not in started.text
        flow = routes._codex_browser_flows[start_payload["flow_id"]]

        completed = await client.post(
            f"/api/v1/codex/oauth/browser/{start_payload['flow_id']}/complete",
            json={"label": "codex-browser", "callback": f"http://localhost:1455/auth/callback?code=browser-code&state={flow.state}"},
            headers=auth,
        )
        assert completed.status_code == 200, completed.text
        completed_payload = completed.json()
        assert completed_payload["status"] == "completed"
        assert completed_payload["config"]["provider"] == "codex"
        assert completed_payload["config"]["label"] == "codex-browser"
        assert "browser-access-token" not in completed.text
        assert "browser-refresh-token" not in completed.text

    async with sqlite_db() as session:
        config = (await session.execute(select(ProviderConfig).where(ProviderConfig.provider == "codex"))).scalar_one()
        stored_secret = CryptoService(settings.encryption_key).decrypt(config.encrypted_api_key)
        assert json.loads(stored_secret)["refresh_token"] == "browser-refresh-token"
        assert config.extra == {"auth_method": "browser_pkce"}


def test_codex_browser_oauth_rejects_state_mismatch():
    from app.providers import codex_oauth

    with pytest.raises(ValueError, match="state mismatch"):
        codex_oauth.authorization_code_from_callback(
            "http://localhost:1455/auth/callback?code=browser-code&state=wrong",
            expected_state="expected",
        )


@pytest.mark.asyncio
async def test_codex_device_oauth_start_403_explains_device_auth_setting(monkeypatch):
    from app.providers import codex_oauth

    original_async_client = httpx.AsyncClient

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, text="Forbidden")

    monkeypatch.setattr(codex_oauth.httpx, "AsyncClient", lambda **kwargs: original_async_client(transport=httpx.MockTransport(handler), **kwargs))

    with pytest.raises(ValueError, match="Enable device code authentication for Codex"):
        await codex_oauth.start_device_authorization(timeout=1)


@pytest.mark.asyncio
async def test_codex_device_oauth_poll_403_explains_device_auth_setting(monkeypatch):
    from app.providers import codex_oauth

    original_async_client = httpx.AsyncClient

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, text="Forbidden")

    monkeypatch.setattr(codex_oauth.httpx, "AsyncClient", lambda **kwargs: original_async_client(transport=httpx.MockTransport(handler), **kwargs))

    result = await codex_oauth.poll_device_authorization("server-only-device-code", timeout=1)

    assert result["status"] == "failed"
    assert "Enable device code authentication for Codex" in result["error"]
    assert "server-only-device-code" not in result["error"]


async def providers_payload():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/providers")
    assert response.status_code == 200, response.text
    return response.json()


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


@pytest.mark.asyncio
async def test_api_tokens_are_hashed_scoped_revocable_and_one_time(sqlite_db):
    admin = {"Authorization": "Bearer test-admin-token-123"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = await client.post(
            "/api/v1/api-tokens",
            json={"name": "Chrome Extension", "scopes": ["usage:read", "poll:write", "configs:read"]},
            headers=admin,
        )
        assert created.status_code == 201, created.text
        payload = created.json()
        token = payload["token"]
        assert token.startswith("udt_")
        assert payload["token_prefix"] == token[:12]
        assert payload["scopes"] == ["configs:read", "poll:write", "usage:read"]

        listed = await client.get("/api/v1/api-tokens", headers=admin)
        assert listed.status_code == 200, listed.text
        listed_payload = listed.json()
        assert listed_payload[0]["name"] == "Chrome Extension"
        assert "token" not in listed_payload[0]
        assert token not in listed.text

        async with sqlite_db() as session:
            record = (await session.execute(select(ApiToken))).scalar_one()
            assert record.token_hash != token
            assert len(record.token_hash) == 64
            token_id = record.id

        scoped = {"Authorization": f"Bearer {token}"}
        configs = await client.get("/api/v1/configs", headers=scoped)
        assert configs.status_code == 200, configs.text

        usage = await client.get("/api/v1/usage", headers=scoped)
        assert usage.status_code == 200, usage.text

        denied_mutation = await client.post("/api/v1/configs", json={"provider": "deepseek", "api_key": "sk-test"}, headers=scoped)
        assert denied_mutation.status_code == 403

        denied_history = await client.get("/api/v1/configs/1/history", headers=scoped)
        assert denied_history.status_code == 403

        revoked = await client.post(f"/api/v1/api-tokens/{token_id}/revoke", headers=admin)
        assert revoked.status_code == 204, revoked.text

        relisted = await client.get("/api/v1/api-tokens", headers=admin)
        assert relisted.status_code == 200, relisted.text
        assert relisted.json() == []

        async with sqlite_db() as session:
            assert await session.get(ApiToken, token_id) is None

        after_revoke = await client.get("/api/v1/usage", headers=scoped)
        assert after_revoke.status_code == 401


@pytest.mark.asyncio
async def test_previously_revoked_api_tokens_can_be_deleted(sqlite_db):
    admin = {"Authorization": "Bearer test-admin-token-123"}
    async with sqlite_db() as session:
        token = ApiToken(
            name="Old revoked token",
            token_hash="a" * 64,
            token_prefix="udt_olddead",
            scopes=["usage:read"],
            revoked_at=datetime.now(UTC),
        )
        session.add(token)
        await session.commit()
        token_id = token.id

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        listed = await client.get("/api/v1/api-tokens", headers=admin)
        assert listed.status_code == 200, listed.text
        assert listed.json()[0]["revoked_at"] is not None

        deleted = await client.post(f"/api/v1/api-tokens/{token_id}/revoke", headers=admin)
        assert deleted.status_code == 204, deleted.text

        relisted = await client.get("/api/v1/api-tokens", headers=admin)
        assert relisted.status_code == 200, relisted.text
        assert relisted.json() == []

    async with sqlite_db() as session:
        assert await session.get(ApiToken, token_id) is None


@pytest.mark.asyncio
async def test_api_token_scope_enforcement_and_admin_backwards_compatibility(sqlite_db):
    admin = {"Authorization": "Bearer test-admin-token-123"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = await client.post("/api/v1/api-tokens", json={"name": "History only", "scopes": ["history:read"]}, headers=admin)
        assert created.status_code == 201, created.text
        token = created.json()["token"]
        scoped = {"Authorization": f"Bearer {token}"}

        assert (await client.get("/api/v1/usage", headers=scoped)).status_code == 403
        assert (await client.post("/api/v1/poll", headers=scoped)).status_code == 403
        assert (await client.get("/api/v1/configs", headers=scoped)).status_code == 403
        assert (await client.get("/api/v1/configs/999/history", headers=scoped)).status_code == 404

        admin_usage = await client.get("/api/v1/usage", headers=admin)
        assert admin_usage.status_code == 200, admin_usage.text
        admin_create_config = await client.post("/api/v1/configs", json={"provider": "deepseek", "api_key": "sk-test"}, headers=admin)
        assert admin_create_config.status_code == 201, admin_create_config.text


@pytest.mark.asyncio
async def test_expired_api_token_is_rejected():
    admin = {"Authorization": "Bearer test-admin-token-123"}
    expired_at = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = await client.post("/api/v1/api-tokens", json={"name": "Expired", "scopes": ["usage:read"], "expires_at": expired_at}, headers=admin)
        assert created.status_code == 201, created.text
        token = created.json()["token"]

        response = await client.get("/api/v1/usage", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401


@pytest.mark.asyncio
async def test_api_token_management_rejects_non_admin_tokens():
    admin = {"Authorization": "Bearer test-admin-token-123"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = await client.post("/api/v1/api-tokens", json={"name": "Usage only", "scopes": ["usage:read"]}, headers=admin)
        token = created.json()["token"]
        scoped = {"Authorization": f"Bearer {token}"}

        list_attempt = await client.get("/api/v1/api-tokens", headers=scoped)
        assert list_attempt.status_code == 403
        create_attempt = await client.post("/api/v1/api-tokens", json={"name": "Nope", "scopes": ["usage:read"]}, headers=scoped)
        assert create_attempt.status_code == 403


@pytest.mark.asyncio
async def test_usage_includes_alert_state_from_thresholds(sqlite_db):
    auth = {"Authorization": "Bearer test-admin-token-123"}
    now = datetime.now(UTC)
    async with sqlite_db() as session:
        config = ProviderConfig(
            provider="firecrawl",
            label="main",
            encrypted_api_key="encrypted",
            alert_thresholds=[
                {"metric": "usage_percent", "direction": "increasing", "warning": 75, "critical": 90},
            ],
        )
        session.add(config)
        await session.flush()
        session.add(
            UsageSnapshot(
                provider_config_id=config.id,
                provider="firecrawl",
                status="healthy",
                summary="test",
                metrics=[{"label": "usage_percent", "value": 92, "unit": "%"}],
                raw={},
                checked_at=now,
            )
        )
        await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/usage", headers=auth)

    assert response.status_code == 200, response.text
    row = response.json()[0]
    assert row["alert_state"] == "critical"
    assert row["alerts"] == [
        {
            "metric": "usage_percent",
            "metric_type": "usage_percent",
            "value": 92,
            "unit": "%",
            "direction": "increasing",
            "alert_state": "critical",
            "thresholds": {"warning": 75, "critical": 90},
        }
    ]


@pytest.mark.asyncio
async def test_usage_without_thresholds_stays_normal(sqlite_db):
    auth = {"Authorization": "Bearer test-admin-token-123"}
    now = datetime.now(UTC)
    async with sqlite_db() as session:
        config = ProviderConfig(provider="deepseek", label="main", encrypted_api_key="encrypted")
        session.add(config)
        await session.flush()
        session.add(
            UsageSnapshot(
                provider_config_id=config.id,
                provider="deepseek",
                status="healthy",
                summary="test",
                metrics=[{"label": "total_balance", "value": 12.5, "unit": "USD"}],
                raw={},
                checked_at=now,
            )
        )
        await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/usage", headers=auth)

    assert response.status_code == 200, response.text
    row = response.json()[0]
    assert row["alert_state"] == "normal"
    assert row["alerts"] == []


@pytest.mark.asyncio
async def test_create_and_update_config_persist_thresholds(sqlite_db):
    auth = {"Authorization": "Bearer test-admin-token-123"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = await client.post(
            "/api/v1/configs",
            json={
                "provider": "firecrawl",
                "label": "main",
                "api_key": "sk-test",
                "alert_thresholds": [
                    {"metric": "usage_percent", "direction": "increasing", "warning": 75, "critical": 90},
                ],
            },
            headers=auth,
        )
        assert created.status_code == 201, created.text
        config_id = created.json()["id"]
        assert created.json()["alert_thresholds"][0]["warning"] == 75

        updated = await client.patch(
            f"/api/v1/configs/{config_id}",
            json={"alert_thresholds": [{"metric": "credits_remaining", "direction": "decreasing", "warning": 10, "exhausted": 0}]},
            headers=auth,
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["alert_thresholds"][0]["metric"] == "credits_remaining"
        assert updated.json()["alert_thresholds"][0]["exhausted"] == 0


@pytest.mark.asyncio
async def test_threshold_rule_requires_at_least_one_value():
    auth = {"Authorization": "Bearer test-admin-token-123"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = await client.post(
            "/api/v1/configs",
            json={
                "provider": "firecrawl",
                "label": "main",
                "api_key": "sk-test",
                "alert_thresholds": [{"metric": "usage_percent", "direction": "increasing"}],
            },
            headers=auth,
        )
        assert created.status_code == 422


@pytest.mark.asyncio
async def test_providers_endpoint_exposes_alert_metrics_catalog():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/providers")

    assert response.status_code == 200, response.text
    by_id = {provider["id"]: provider for provider in response.json()}

    codex = by_id["codex"]["alert_metrics"]
    assert any(m["metric"] == "session_remaining_percent" and m["direction"] == "decreasing" and m["unit"] == "%" for m in codex)

    deepseek = by_id["deepseek"]["alert_metrics"]
    assert any(m["metric"] == "total_balance" and m["direction"] == "decreasing" and m["unit"] == "USD" for m in deepseek)

    firecrawl = by_id["firecrawl"]["alert_metrics"]
    assert any(m["metric"] == "usage_percent" and m["direction"] == "increasing" for m in firecrawl)

    # Custom HTTP has no static metric catalog — the frontend falls back to free-text entry.
    assert by_id["custom_http"]["alert_metrics"] == []
