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
from app.models import AdminCredential, Base, DataSourceConfig, ProviderConfig, UsageObservation
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
    # Use a completed day so the endpoint's default `to=now` range does not
    # make the later same-day observation look like future data in early-UTC CI.
    base = (datetime.now(UTC) - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
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


class NativeFakeAdapter(ProviderAdapter):
    id = "nativefake"
    name = "Native Fake"
    description = "Fake provider with native history"
    default_base_url = "https://fake.example"
    metric_names = ["tokens"]
    analytics = analytics_spec(
        supported=True,
        native_history=True,
        metrics={"tokens": metric_spec(type_="counter", unit="tokens", direction="increasing")},
    )
    native: list[dict] = []

    async def fetch_usage(self) -> ProviderUsage:
        return ProviderUsage(status="healthy", summary="ok", metrics=[Metric("tokens", 10, "tokens")], raw={})

    @staticmethod
    def native_observations(raw):
        return NativeFakeAdapter.native


@pytest.mark.asyncio
async def test_native_history_upsert_persists_dedupes_and_updates(sqlite_db, monkeypatch):
    Session = sqlite_db
    monkeypatch.setitem(ADAPTERS, "nativefake", NativeFakeAdapter)
    config = await _create_config(Session, provider="nativefake")
    base = datetime(2026, 8, 20, 0, 0, tzinfo=UTC)

    def buckets(start_hour, end_hour, factor):
        return [
            {
                "metric": "tokens",
                "value": float(hour) * factor,
                "unit": "tokens",
                "observed_at": base + timedelta(hours=hour),
                "window_start": base + timedelta(hours=hour),
                "window_end": base + timedelta(hours=hour + 1),
                "kind": "delta",
            }
            for hour in range(start_hour, end_hour + 1)
        ]

    # Poll 1: native hours 1..24 at factor 1.0.
    NativeFakeAdapter.native = buckets(1, 24, factor=1.0)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.post(f"/api/v1/configs/{config.id}/poll", headers=ADMIN_AUTH)).status_code == 200

    # Poll 2: rolling window advances - native hours 2..25 at factor 2.0, so the
    # overlapping hours 2..24 arrive again with *different* values.
    NativeFakeAdapter.native = buckets(2, 25, factor=2.0)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.post(f"/api/v1/configs/{config.id}/poll", headers=ADMIN_AUTH)).status_code == 200

    async with Session() as session:
        rows = (
            await session.execute(
                select(UsageObservation).where(
                    UsageObservation.provider_config_id == config.id,
                    UsageObservation.source == "native",
                )
            )
        ).scalars().all()

    naive_base = base.replace(tzinfo=None)
    by_start = {row.window_start: row.value for row in rows}

    # All 25 hours exist and nothing was duplicated.
    assert len(rows) == 25
    assert set(by_start) == {naive_base + timedelta(hours=h) for h in range(1, 26)}
    # Hour 1 fell out of the provider's rolling window but must survive.
    assert by_start[naive_base + timedelta(hours=1)] == 1.0
    # Overlapping hours were updated in place to the poll-2 values.
    assert by_start[naive_base + timedelta(hours=2)] == 4.0
    assert by_start[naive_base + timedelta(hours=24)] == 48.0
    # New hour 25 was inserted.
    assert by_start[naive_base + timedelta(hours=25)] == 50.0


@pytest.mark.asyncio
async def test_overview_totals_and_like_unit_share(sqlite_db):
    Session = sqlite_db
    anthropic = await _create_config(Session, provider="anthropic")
    openai = await _create_config(Session, provider="openai")
    openrouter = await _create_config(Session, provider="openrouter")
    base = datetime.now(UTC) - timedelta(days=2)

    await _seed_observations(Session, anthropic, [
        {"metric": "input_tokens", "value": 100.0, "unit": "tokens", "kind": "delta", "observed_at": base},
    ])
    await _seed_observations(Session, openai, [
        {"metric": "daily_cost", "value": 5.0, "unit": "USD", "kind": "delta", "observed_at": base},
    ])
    await _seed_observations(Session, openrouter, [
        {"metric": "usage_monthly", "value": 10.0, "unit": "credits", "kind": "delta", "observed_at": base},
    ])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/analytics/overview", headers=ADMIN_AUTH)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["totals"]["tokens"] == 100.0
    assert payload["totals"]["USD"] == 5.0
    assert payload["totals"]["credits"] == 10.0

    by_provider = {p["provider"]: p for p in payload["providers"]}
    # Each provider is the only one in its like-unit group, so share is 100%.
    assert by_provider["anthropic"]["unit"] == "tokens"
    assert by_provider["anthropic"]["share_pct"] == 100.0
    assert by_provider["openai"]["unit"] == "USD"
    assert by_provider["openrouter"]["unit"] == "credits"


@pytest.mark.asyncio
async def test_overview_activity_dimensions_group_and_share(sqlite_db):
    """Activity dimensions group compatible units and share within a dimension."""
    Session = sqlite_db
    anthropic = await _create_config(Session, provider="anthropic")
    openrouter = await _create_config(Session, provider="openrouter")
    firecrawl = await _create_config(Session, provider="firecrawl")
    base = datetime.now(UTC) - timedelta(days=2)

    # Anthropic tokens: input 100 + output 50 = 150 tokens; requests = 30.
    await _seed_observations(Session, anthropic, [
        {"metric": "input_tokens", "value": 100.0, "unit": "tokens", "kind": "delta", "observed_at": base},
        {"metric": "output_tokens", "value": 50.0, "unit": "tokens", "kind": "delta", "observed_at": base},
        {"metric": "num_requests", "value": 30.0, "unit": "requests", "kind": "delta", "observed_at": base},
    ])
    # OpenRouter credits: 10; Firecrawl credits: 40 (both credits → shared).
    await _seed_observations(Session, openrouter, [
        {"metric": "usage_monthly", "value": 10.0, "unit": "credits", "kind": "delta", "observed_at": base},
    ])
    await _seed_observations(Session, firecrawl, [
        {"metric": "credits_used", "value": 40.0, "unit": "credits", "kind": "delta", "observed_at": base},
    ])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/analytics/overview", headers=ADMIN_AUTH)

    assert response.status_code == 200, response.text
    payload = response.json()
    dims = {d["dimension"]: d for d in payload["activity"]}

    # tokens: only anthropic, sum of input+output (150), 100% share.
    tokens = dims["tokens"]
    assert tokens["unit"] == "tokens"
    assert tokens["total"] == 150.0
    assert len(tokens["providers"]) == 1
    assert tokens["providers"][0]["value"] == 150.0
    assert tokens["providers"][0]["share_pct"] == 100.0

    # requests: only anthropic.
    requests = dims["requests"]
    assert requests["total"] == 30.0
    assert requests["providers"][0]["provider"] == "anthropic"

    # credits: openrouter (10) + firecrawl (40) share one dimension.
    credits = dims["credits"]
    assert credits["total"] == 50.0
    by_provider = {p["provider"]: p for p in credits["providers"]}
    assert by_provider["openrouter"]["share_pct"] == 20.0
    assert by_provider["firecrawl"]["share_pct"] == 80.0

    # No cost dimension (no USD counter deltas).
    assert "cost" not in dims


@pytest.mark.asyncio
async def test_overview_activity_excludes_state_and_percent(sqlite_db):
    """Balances, remaining, and % utilization never appear as activity."""
    Session = sqlite_db
    deepseek = await _create_config(Session, provider="deepseek")
    codex = await _create_config(Session, provider="codex")
    base = datetime.now(UTC) - timedelta(days=2)

    await _seed_observations(Session, deepseek, [
        {"metric": "total_balance", "value": 42.0, "unit": "USD", "kind": "point", "observed_at": base},
    ])
    await _seed_observations(Session, codex, [
        {"metric": "weekly_remaining_percent", "value": 50.0, "unit": "%", "kind": "point", "observed_at": base, "reset_at": base + timedelta(days=5)},
    ])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/analytics/overview", headers=ADMIN_AUTH)

    assert response.status_code == 200, response.text
    payload = response.json()
    # DeepSeek balance is state, Codex % is capacity — no activity dimensions.
    assert payload["activity"] == []


@pytest.mark.asyncio
async def test_provider_capacity_summary_and_history(sqlite_db):
    """Capacity endpoint returns used/remaining/overage, reset, and history."""
    Session = sqlite_db
    codex = await _create_config(Session, provider="codex")
    base = datetime.now(UTC) - timedelta(days=2)
    reset = base + timedelta(days=5)
    await _seed_observations(Session, codex, [
        {"metric": "weekly_remaining_percent", "value": -28.0, "unit": "%", "kind": "point", "source": "native", "observed_at": base, "reset_at": reset},
        {"metric": "weekly_remaining_percent", "value": -30.0, "unit": "%", "kind": "point", "source": "native", "observed_at": base + timedelta(hours=1), "reset_at": reset},
    ])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/api/v1/analytics/providers/{codex.id}/capacity", headers=ADMIN_AUTH)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["provider"] == "codex"
    assert payload["capacity_used_pct"] == 130.0
    assert payload["capacity_remaining_pct"] == 0.0
    assert payload["overage_pct"] == 30.0
    assert payload["source"] == "native"
    assert payload["reset_at"] is not None
    # Utilization history buckets exist (not empty).
    assert len(payload["buckets"]) > 0
    assert any(b["value"] is not None for b in payload["buckets"])


@pytest.mark.asyncio
async def test_provider_capacity_graceful_for_non_quota_provider(sqlite_db):
    """Non-quota providers return null utilization, never fabricated 0%."""
    Session = sqlite_db
    anthropic = await _create_config(Session, provider="anthropic")
    base = datetime.now(UTC) - timedelta(days=2)
    await _seed_observations(Session, anthropic, [
        {"metric": "input_tokens", "value": 100.0, "unit": "tokens", "kind": "delta", "source": "native", "observed_at": base},
    ])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/api/v1/analytics/providers/{anthropic.id}/capacity", headers=ADMIN_AUTH)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["provider"] == "anthropic"
    assert payload["capacity_used_pct"] is None
    assert payload["overage_pct"] is None
    assert payload["buckets"] == []


@pytest.mark.asyncio
async def test_overview_utilization_comparison(sqlite_db):
    Session = sqlite_db
    codex = await _create_config(Session, provider="codex")
    base = datetime.now(UTC) - timedelta(days=2)
    await _seed_observations(Session, codex, [
        {"metric": "weekly_remaining_percent", "value": 60.0, "unit": "%", "kind": "point", "observed_at": base},
        {"metric": "weekly_remaining_percent", "value": 50.0, "unit": "%", "kind": "point", "observed_at": base + timedelta(hours=24)},
    ])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/analytics/overview", headers=ADMIN_AUTH)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["comparison"], "codex should appear in the utilization comparison"
    series = next(s for s in payload["comparison"] if s["provider"] == "codex")
    assert series["metric"] == "weekly_remaining_percent"
    values = [b["value"] for b in series["buckets"] if b["value"] is not None]
    # remaining 60 -> 40% consumed; remaining 50 -> 50% consumed.
    assert 40.0 in values
    assert 50.0 in values


@pytest.mark.asyncio
async def test_overview_preserves_over_limit_utilization_and_audit_source(sqlite_db):
    Session = sqlite_db
    codex = await _create_config(Session, provider="codex")
    base = datetime.now(UTC) - timedelta(days=2)
    reset = base + timedelta(days=5)
    await _seed_observations(Session, codex, [
        {"metric": "weekly_remaining_percent", "value": -28.0, "unit": "%", "kind": "point", "source": "native", "observed_at": base, "reset_at": reset},
    ])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/analytics/overview", headers=ADMIN_AUTH)

    assert response.status_code == 200, response.text
    payload = response.json()
    provider = next(p for p in payload["providers"] if p["provider"] == "codex")
    assert provider["utilization_pct"] == 128.0
    assert provider["remaining_pct"] == 0.0
    assert provider["overage_pct"] == 28.0
    assert provider["authoritative_source"] == "native"
    assert provider["sources"] == ["native"]
    assert provider["audit"]["capacity"]["value"] == 128.0
    assert payload["highest_utilization"]["utilization_pct"] == 128.0
    assert payload["provider_pressure_pct"] == 128.0
    assert payload["risks"][0]["state"] == "exhausted"
    assert "28.0% over allowance" in payload["risks"][0]["reason"]
    series = next(s for s in payload["comparison"] if s["provider"] == "codex")
    assert series["source"] == "native"
    values = [b["value"] for b in series["buckets"] if b["value"] is not None]
    assert 128.0 in values


@pytest.mark.asyncio
async def test_overview_uses_declared_headline_not_sum(sqlite_db):
    """Overlapping same-unit deltas must not inflate the headline or totals."""
    Session = sqlite_db
    openrouter = await _create_config(Session, provider="openrouter")
    base = datetime.now(UTC) - timedelta(days=2)
    # daily + weekly + monthly all report credits but overlap; only usage_monthly
    # is declared the overview metric, so it alone should count.
    await _seed_observations(Session, openrouter, [
        {"metric": "usage_daily", "value": 10.0, "unit": "credits", "kind": "delta", "observed_at": base},
        {"metric": "usage_weekly", "value": 20.0, "unit": "credits", "kind": "delta", "observed_at": base},
        {"metric": "usage_monthly", "value": 30.0, "unit": "credits", "kind": "delta", "observed_at": base},
    ])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/analytics/overview", headers=ADMIN_AUTH)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["totals"]["credits"] == 30.0  # not 60.0
    row = next(p for p in payload["providers"] if p["provider"] == "openrouter")
    assert row["value"] == 30.0
    assert row["unit"] == "credits"


@pytest.mark.asyncio
async def test_overview_provider_pressure_excludes_unknown_utilization(sqlite_db):
    Session = sqlite_db
    codex = await _create_config(Session, provider="codex")
    openrouter = await _create_config(Session, provider="openrouter")
    deepseek = await _create_config(Session, provider="deepseek")
    base = datetime.now(UTC) - timedelta(days=2)

    await _seed_observations(Session, codex, [
        {"metric": "weekly_remaining_percent", "value": 50.0, "unit": "%", "kind": "point", "observed_at": base, "reset_at": base + timedelta(days=5)},
    ])
    await _seed_observations(Session, openrouter, [
        {"metric": "limit", "value": 100.0, "unit": "credits", "kind": "point", "observed_at": base},
        {"metric": "limit_remaining", "value": 25.0, "unit": "credits", "kind": "point", "observed_at": base, "reset_at": base + timedelta(days=28)},
        {"metric": "usage_monthly", "value": 10.0, "unit": "credits", "kind": "delta", "observed_at": base},
    ])
    await _seed_observations(Session, deepseek, [
        {"metric": "total_balance", "value": 42.0, "unit": "USD", "kind": "point", "observed_at": base},
    ])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/analytics/overview", headers=ADMIN_AUTH)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["provider_pressure_pct"] == 62.5
    assert payload["measurable_provider_count"] == 2
    assert payload["total_provider_count"] == 3
    assert payload["coverage"]["measurable_provider_count"] == 2
    assert payload["highest_utilization"]["provider"] == "openrouter"
    assert payload["highest_utilization"]["utilization_pct"] == 75.0
    assert payload["totals"]["credits"] == 10.0
    assert payload["totals"]["USD"] == 42.0

    by_provider = {p["provider"]: p for p in payload["providers"]}
    assert by_provider["codex"]["utilization_pct"] == 50.0
    assert by_provider["codex"]["remaining_pct"] == 50.0
    assert by_provider["deepseek"]["utilization_pct"] is None
    assert by_provider["deepseek"]["exclusion_reason"] == "No normalizable quota/capacity metric"
    assert payload["risks"][0]["provider"] == "openrouter"
    assert payload["risks"][0]["state"] == "warning"


@pytest.mark.asyncio
async def test_overview_maps_hermes_activity_to_provider_without_double_counting(sqlite_db):
    Session = sqlite_db
    anthropic = await _create_config(Session, provider="anthropic")
    base = datetime.now(UTC) - timedelta(days=2)
    await _seed_observations(Session, anthropic, [
        {"metric": "input_tokens", "value": 2000.0, "unit": "tokens", "kind": "delta", "source": "native", "observed_at": base},
    ])
    async with Session() as session:
        session.add_all([
            UsageObservation(
                provider="claude",
                provider_mapping="anthropic",
                metric="input_tokens",
                value=900.0,
                unit="tokens",
                kind="delta",
                source="hermes",
                observed_at=base + timedelta(hours=1),
                model="claude-sonnet-4",
                session_id="s1",
            ),
            UsageObservation(
                provider="claude",
                provider_mapping="anthropic",
                metric="requests",
                value=7.0,
                unit="count",
                kind="delta",
                source="hermes",
                observed_at=base + timedelta(hours=1),
                model="claude-sonnet-4",
                session_id="s1",
            ),
        ])
        await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/analytics/overview", headers=ADMIN_AUTH)

    assert response.status_code == 200, response.text
    payload = response.json()
    # Provider-native totals remain authoritative; Hermes is corroborating telemetry, not added on top.
    assert payload["totals"]["tokens"] == 2000.0
    row = next(p for p in payload["providers"] if p["provider"] == "anthropic")
    assert row["sources"] == ["hermes", "native"]
    assert row["authoritative_source"] == "native"
    assert row["corroborating_sources"] == ["hermes"]
    assert row["hermes_activity"] == {"input_tokens": 900.0, "requests": 7.0}
    input_attr = next(item for item in row["attribution"] if item["metric"] == "input_tokens")
    assert input_attr["provider_total"] == 2000.0
    assert input_attr["hermes_observed"] == 900.0
    assert input_attr["attribution_pct"] == 45.0
    assert input_attr["status"] == "partial"
    assert row["audit"]["activity"]["hermes_activity"]["input_tokens"] == 900.0
    assert "not added" in row["audit"]["activity"]["note"]


@pytest.mark.asyncio
async def test_hermes_breakdown_includes_source_diagnostics_and_keeps_totals_supplemental(sqlite_db):
    Session = sqlite_db
    provider = await _create_config(Session, provider="anthropic")
    now = datetime.now(UTC)
    async with Session() as session:
        source = DataSourceConfig(
            kind="hermes",
            name="Hermes main",
            base_url="http://hermes.local",
            is_enabled=True,
            last_attempt_at=now - timedelta(minutes=3),
            last_success_at=now - timedelta(minutes=3),
            consecutive_failures=0,
            extra={"profiles": ["coder"], "provider_mappings": {"claude": "anthropic"}},
        )
        session.add(source)
        await session.commit()
        await session.refresh(source)
        session.add_all([
            UsageObservation(
                data_source_id=source.id,
                provider="claude",
                provider_mapping="anthropic",
                metric="input_tokens",
                value=900.0,
                unit="tokens",
                kind="delta",
                source="hermes",
                observed_at=now - timedelta(hours=2),
                profile="coder",
                model="claude-sonnet-4",
                session_id="s1",
            ),
            UsageObservation(
                provider_config_id=provider.id,
                provider="anthropic",
                metric="input_tokens",
                value=2000.0,
                unit="tokens",
                kind="delta",
                source="native",
                observed_at=now - timedelta(hours=2),
            ),
        ])
        await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        breakdown = await client.get("/api/v1/analytics/hermes", headers=ADMIN_AUTH)
        overview = await client.get("/api/v1/analytics/overview", headers=ADMIN_AUTH)

    assert breakdown.status_code == 200, breakdown.text
    payload = breakdown.json()
    assert payload["sources"][0]["name"] == "Hermes main"
    assert payload["sources"][0]["status"] == "healthy"
    assert payload["sources"][0]["observations_in_range"] == 1
    assert payload["sources"][0]["latest_observation_at"] is not None
    assert payload["sources"][0]["providers_observed"] == ["claude"]
    assert payload["sources"][0]["providers_unmapped"] == []
    assert any("filtered to profiles: coder" in item["message"] for item in payload["diagnostics"])
    totals = {item["metric"]: item["value"] for item in payload["totals"]}
    assert totals["tokens"] == 900.0

    assert overview.status_code == 200, overview.text
    # Hermes is supplemental; overview totals stay provider-authoritative only.
    assert overview.json()["totals"]["tokens"] == 2000.0


@pytest.mark.asyncio
async def test_hermes_breakdown_explains_empty_range_and_unmapped_providers(sqlite_db):
    Session = sqlite_db
    await _create_config(Session, provider="anthropic")
    now = datetime.now(UTC)
    async with Session() as session:
        source = DataSourceConfig(
            kind="hermes",
            name="Hermes stale",
            base_url="http://hermes.local",
            is_enabled=True,
            last_attempt_at=now - timedelta(days=10),
            last_success_at=now - timedelta(days=10),
            consecutive_failures=0,
        )
        session.add(source)
        await session.commit()
        await session.refresh(source)
        session.add(
            UsageObservation(
                data_source_id=source.id,
                provider="mystery",
                provider_mapping="mystery",
                metric="requests",
                value=3.0,
                unit="count",
                kind="delta",
                source="hermes",
                observed_at=now - timedelta(days=40),
            )
        )
        await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/analytics/hermes", headers=ADMIN_AUTH)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["sources"][0]["observations_in_range"] == 0
    assert payload["sources"][0]["total_observations"] == 1
    assert payload["sources"][0]["providers_unmapped"] == ["mystery"]
    messages = [item["message"] for item in payload["diagnostics"]]
    assert any("outside the selected range" in message for message in messages)
    assert any("unmapped providers: mystery" in message for message in messages)
    assert any("No Hermes observations between" in message for message in messages)


@pytest.mark.asyncio
async def test_overview_reconciliation_flags_activity_disagreement(sqlite_db):
    """A Hermes observation materially above the native headline must show as a
    disagreement in audit.activity.reconciliation and reduce confidence."""
    Session = sqlite_db
    anthropic = await _create_config(Session, provider="anthropic")
    now = datetime.now(UTC)
    base = now - timedelta(hours=2)

    # Native headline: 1000 input tokens (authoritative).
    await _seed_observations(Session, anthropic, [
        {"metric": "input_tokens", "value": 1000.0, "unit": "tokens", "kind": "delta", "source": "native", "observed_at": base},
    ])

    # Hermes observed 2000 input tokens for the same provider/window.
    async with Session() as session:
        source = DataSourceConfig(kind="hermes", name="Hermes rec", base_url="http://hermes.local", is_enabled=True)
        session.add(source)
        await session.commit()
        await session.refresh(source)
        session.add(
            UsageObservation(
                data_source_id=source.id,
                provider="anthropic",
                provider_mapping="anthropic",
                metric="input_tokens",
                value=2000.0,
                unit="tokens",
                kind="delta",
                source="hermes",
                observed_at=base,
                model="claude-sonnet-4",
            )
        )
        await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/analytics/overview", headers=ADMIN_AUTH)

    assert response.status_code == 200, response.text
    payload = response.json()
    row = next(p for p in payload["providers"] if p["provider"] == "anthropic")
    activity = row["audit"]["activity"]
    assert activity["reconciliation"]["has_disagreement"] is True
    assert activity["reconciliation"]["authoritative_source"] == "native"
    assert activity["reconciliation"]["disagreements"][0]["source"] == "hermes"
    assert activity["reconciliation"]["confidence_impact"] < 0
    # The provider-level confidence must be demoted below the raw level (low).
    assert row["confidence"] == "low"


@pytest.mark.asyncio
async def test_overview_reconciliation_clean_when_hermes_agrees(sqlite_db):
    """A Hermes observation within tolerance produces no disagreement."""
    Session = sqlite_db
    anthropic = await _create_config(Session, provider="anthropic")
    now = datetime.now(UTC)
    base = now - timedelta(hours=2)

    await _seed_observations(Session, anthropic, [
        {"metric": "input_tokens", "value": 1000.0, "unit": "tokens", "kind": "delta", "source": "native", "observed_at": base},
    ])
    async with Session() as session:
        source = DataSourceConfig(kind="hermes", name="Hermes rec", base_url="http://hermes.local", is_enabled=True)
        session.add(source)
        await session.commit()
        await session.refresh(source)
        session.add(
            UsageObservation(
                data_source_id=source.id,
                provider="anthropic",
                provider_mapping="anthropic",
                metric="input_tokens",
                value=1100.0,  # within 50% relative tolerance
                unit="tokens",
                kind="delta",
                source="hermes",
                observed_at=base,
                model="claude-sonnet-4",
            )
        )
        await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/analytics/overview", headers=ADMIN_AUTH)

    assert response.status_code == 200, response.text
    payload = response.json()
    row = next(p for p in payload["providers"] if p["provider"] == "anthropic")
    activity = row["audit"]["activity"]
    assert activity["reconciliation"]["has_disagreement"] is False
    assert activity["reconciliation"]["confidence_impact"] == 0
