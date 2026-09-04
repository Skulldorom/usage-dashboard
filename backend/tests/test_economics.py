"""Regression tests for provider billing and value analytics."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.analytics.economics import _periods, subscription_cost_basis
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


async def _seed_tokens(Session, provider="anthropic", *, start: datetime, days: int, model="claude-sonnet-4", include_unknown: bool = False):
    async with Session() as session:
        rows = []
        for index in range(days):
            model_name = "mystery-model" if include_unknown and index == days - 1 else model
            rows.append(
                UsageObservation(
                    provider=provider,
                    provider_mapping=provider,
                    metric="input_tokens",
                    value=1_000_000,
                    unit="tokens",
                    kind="delta",
                    source="hermes",
                    observed_at=start + timedelta(days=index),
                    model=model_name,
                )
            )
        session.add_all(rows)
        await session.commit()


def _config_obj(**kwargs):
    defaults = {
        "subscription_amount": 31,
        "subscription_currency": "USD",
        "billing_cadence": "monthly",
        "billing_anchor": datetime(2026, 9, 15, tzinfo=UTC),
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_periods_work_before_anchor_and_multiple_periods_after_anchor():
    anchor = datetime(2026, 9, 15, tzinfo=UTC)
    before = list(_periods(anchor, "monthly", datetime(2026, 8, 1, tzinfo=UTC), datetime(2026, 9, 1, tzinfo=UTC)))
    assert before == [
        (datetime(2026, 7, 15, tzinfo=UTC), datetime(2026, 8, 15, tzinfo=UTC)),
        (datetime(2026, 8, 15, tzinfo=UTC), datetime(2026, 9, 15, tzinfo=UTC)),
    ]

    after = list(_periods(anchor, "monthly", datetime(2027, 1, 1, tzinfo=UTC), datetime(2027, 3, 1, tzinfo=UTC)))
    assert after[0] == (datetime(2026, 12, 15, tzinfo=UTC), datetime(2027, 1, 15, tzinfo=UTC))
    assert after[-1] == (datetime(2027, 2, 15, tzinfo=UTC), datetime(2027, 3, 15, tzinfo=UTC))


def test_periods_preserve_real_calendar_months_and_leap_years():
    jan31 = datetime(2026, 1, 31, tzinfo=UTC)
    periods = list(_periods(jan31, "monthly", datetime(2026, 2, 1, tzinfo=UTC), datetime(2026, 5, 1, tzinfo=UTC)))
    assert periods == [
        (datetime(2026, 1, 31, tzinfo=UTC), datetime(2026, 2, 28, tzinfo=UTC)),
        (datetime(2026, 2, 28, tzinfo=UTC), datetime(2026, 3, 31, tzinfo=UTC)),
        (datetime(2026, 3, 31, tzinfo=UTC), datetime(2026, 4, 30, tzinfo=UTC)),
        (datetime(2026, 4, 30, tzinfo=UTC), datetime(2026, 5, 31, tzinfo=UTC)),
    ]

    leap = list(_periods(jan31, "monthly", datetime(2024, 2, 1, tzinfo=UTC), datetime(2024, 4, 1, tzinfo=UTC)))
    assert leap[0][1] == datetime(2024, 2, 29, tzinfo=UTC)
    assert leap[1] == (datetime(2024, 2, 29, tzinfo=UTC), datetime(2024, 3, 31, tzinfo=UTC))


def test_yearly_periods_work_before_anchor_without_30_day_fallback():
    anchor = datetime(2026, 9, 15, tzinfo=UTC)
    periods = list(_periods(anchor, "yearly", datetime(2024, 8, 1, tzinfo=UTC), datetime(2026, 10, 1, tzinfo=UTC)))
    assert periods == [
        (datetime(2023, 9, 15, tzinfo=UTC), datetime(2024, 9, 15, tzinfo=UTC)),
        (datetime(2024, 9, 15, tzinfo=UTC), datetime(2025, 9, 15, tzinfo=UTC)),
        (datetime(2025, 9, 15, tzinfo=UTC), datetime(2026, 9, 15, tzinfo=UTC)),
        (datetime(2026, 9, 15, tzinfo=UTC), datetime(2027, 9, 15, tzinfo=UTC)),
    ]


def test_subscription_cost_basis_prorates_range_before_anchor():
    basis = subscription_cost_basis(_config_obj(), datetime(2026, 8, 1, tzinfo=UTC), datetime(2026, 9, 1, tzinfo=UTC))
    # 14/31 of Jul15-Aug15 plus 17/31 of Aug15-Sep15 for a $31 monthly subscription.
    assert basis["amount"] == pytest.approx(31.0, abs=0.0001)


@pytest.mark.asyncio
async def test_economics_subscription_prorates_real_month_overlap(sqlite_db):
    Session = sqlite_db
    await _config(
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
    await _seed_tokens(Session, start=start, days=30)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/analytics/economics", params={"from": start.isoformat(), "to": end.isoformat()}, headers=ADMIN_AUTH)

    assert response.status_code == 200, response.text
    row = response.json()["providers"][0]
    assert row["subscription_cost_basis"]["amount"] == pytest.approx(29.928571, abs=0.0001)
    assert row["observed"]["pricing_coverage"]["level"] == "high"
    assert row["observed"]["attribution_confidence"]["level"] in {"medium", "high"}
    assert row["comparison_eligible"] is True


@pytest.mark.asyncio
async def test_economics_mixed_currency_does_not_silently_aggregate_as_usd(sqlite_db):
    Session = sqlite_db
    config = await _config(Session, provider="openai", pricing_model="payg", subscription_currency="EUR")
    start = datetime.now(UTC) - timedelta(days=40)
    async with Session() as session:
        session.add(UsageObservation(provider_config_id=config.id, provider="openai", metric="daily_cost", value=20, unit="EUR", kind="delta", source="native", observed_at=start + timedelta(days=30)))
        await session.commit()
    await _seed_tokens(Session, provider="openai", start=start, days=30, model="gpt-4o")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/analytics/economics", headers=ADMIN_AUTH)

    assert response.status_code == 200, response.text
    payload = response.json()
    row = payload["providers"][0]
    assert row["actual_spend"]["currency"] == "EUR"
    assert row["cost_basis"]["currency"] == "EUR"
    assert row["api_equivalent"]["currency"] == "USD"
    assert row["economics"]["value_multiplier"] is None
    assert row["economics"]["savings_vs_api"] is None
    assert row["comparison_eligible"] is False
    assert "currency" in row["exclusion_reason"]
    assert payload["summary"]["eligible_provider_count"] == 0
    assert payload["summary"]["cost_basis"]["amount"] is None


@pytest.mark.asyncio
async def test_economics_actual_spend_rejects_mixed_provider_spend_units(sqlite_db):
    Session = sqlite_db
    config = await _config(Session, provider="openai", pricing_model="payg")
    now = datetime.now(UTC)
    async with Session() as session:
        session.add_all([
            UsageObservation(provider_config_id=config.id, provider="openai", metric="daily_cost", value=10, unit="USD", kind="delta", source="native", observed_at=now - timedelta(days=2)),
            UsageObservation(provider_config_id=config.id, provider="openai", metric="daily_cost", value=10, unit="GBP", kind="delta", source="native", observed_at=now - timedelta(days=1)),
        ])
        await session.commit()
    await _seed_tokens(Session, provider="openai", start=now - timedelta(days=30), days=30, model="gpt-4o")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/analytics/economics", headers=ADMIN_AUTH)

    row = response.json()["providers"][0]
    assert row["actual_spend"]["currency"] == "MIXED"
    assert row["actual_spend"]["comparable"] is False
    assert row["cost_basis"]["amount"] is None
    assert row["comparison_eligible"] is False


@pytest.mark.asyncio
async def test_pricing_coverage_and_attribution_confidence_are_separate(sqlite_db):
    Session = sqlite_db
    await _config(Session, provider="anthropic", pricing_model="subscription", subscription_amount=20, subscription_currency="USD", billing_cadence="monthly")
    now = datetime.now(UTC)
    await _seed_tokens(Session, start=now - timedelta(days=1), days=1)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/analytics/economics", headers=ADMIN_AUTH)

    row = response.json()["providers"][0]
    assert row["observed"]["pricing_coverage"]["level"] == "high"
    assert row["observed"]["attribution_confidence"]["level"] == "low"
    assert row["confidence"] == "low"
    assert row["comparison_eligible"] is False
    assert "attribution confidence" in row["exclusion_reason"]


@pytest.mark.asyncio
async def test_partial_pricing_coverage_can_still_have_strong_attribution(sqlite_db):
    Session = sqlite_db
    await _config(Session, provider="anthropic", pricing_model="subscription", subscription_amount=20, subscription_currency="USD", billing_cadence="monthly")
    now = datetime.now(UTC)
    await _seed_tokens(Session, start=now - timedelta(days=20), days=10, include_unknown=True)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/analytics/economics", headers=ADMIN_AUTH)

    row = response.json()["providers"][0]
    assert row["observed"]["pricing_coverage"]["level"] == "partial"
    assert row["observed"]["attribution_confidence"]["level"] in {"medium", "high"}
    assert row["comparison_eligible"] is True


@pytest.mark.asyncio
async def test_insufficient_pricing_coverage_with_strong_attribution_is_ineligible(sqlite_db):
    Session = sqlite_db
    await _config(Session, provider="anthropic", pricing_model="subscription", subscription_amount=20, subscription_currency="USD", billing_cadence="monthly")
    now = datetime.now(UTC)
    await _seed_tokens(Session, start=now - timedelta(days=20), days=10, include_unknown=True)
    async with Session() as session:
        # Add enough unknown tokens to drop coverage below the 80% comparison floor while preserving observation history quality.
        for index in range(10):
            session.add(UsageObservation(provider="anthropic", provider_mapping="anthropic", metric="output_tokens", value=1_000_000, unit="tokens", kind="delta", source="hermes", observed_at=now - timedelta(days=20 - index), model="unknown-output-model"))
        await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/analytics/economics", headers=ADMIN_AUTH)

    row = response.json()["providers"][0]
    assert row["observed"]["pricing_coverage"]["level"] == "insufficient"
    assert row["observed"]["attribution_confidence"]["level"] in {"medium", "high"}
    assert row["comparison_eligible"] is False
    assert "pricing coverage" in row["exclusion_reason"]


@pytest.mark.asyncio
async def test_high_pricing_coverage_and_strong_attribution_are_eligible(sqlite_db):
    Session = sqlite_db
    await _config(Session, provider="anthropic", pricing_model="subscription", subscription_amount=20, subscription_currency="USD", billing_cadence="monthly")
    now = datetime.now(UTC)
    await _seed_tokens(Session, start=now - timedelta(days=40), days=30)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/analytics/economics", headers=ADMIN_AUTH)

    row = response.json()["providers"][0]
    assert row["observed"]["pricing_coverage"]["level"] == "high"
    assert row["observed"]["attribution_confidence"]["level"] in {"medium", "high"}
    assert row["comparison_eligible"] is True


@pytest.mark.asyncio
async def test_economics_filters_by_config_id(sqlite_db):
    Session = sqlite_db
    first = await _config(Session, provider="anthropic", label="Work", pricing_model="subscription", subscription_amount=20, subscription_currency="USD", billing_cadence="monthly")
    await _config(Session, provider="openai", label="Personal", pricing_model="payg")
    now = datetime.now(UTC)
    await _seed_tokens(Session, start=now - timedelta(days=30), days=30)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/analytics/economics", params={"config_id": first.id}, headers=ADMIN_AUTH)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert [row["config_id"] for row in payload["providers"]] == [first.id]


@pytest.mark.asyncio
async def test_economics_single_config_attributes_hermes_workload(sqlite_db):
    Session = sqlite_db
    await _config(Session, provider="anthropic", label="main", pricing_model="subscription", subscription_amount=20, subscription_currency="USD", billing_cadence="monthly")
    now = datetime.now(UTC)
    await _seed_tokens(Session, start=now - timedelta(days=30), days=30)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/analytics/economics", headers=ADMIN_AUTH)

    assert response.status_code == 200, response.text
    payload = response.json()
    row = payload["providers"][0]
    assert row["attribution_ambiguous"] is False
    assert row["api_equivalent"]["value"] is not None
    assert row["api_equivalent"]["value"] > 0
    assert payload["provider_level"] == []


@pytest.mark.asyncio
async def test_economics_two_configs_same_provider_do_not_double_count(sqlite_db):
    Session = sqlite_db
    await _config(Session, provider="anthropic", label="Work", pricing_model="subscription", subscription_amount=20, subscription_currency="USD", billing_cadence="monthly")
    await _config(Session, provider="anthropic", label="Personal", pricing_model="subscription", subscription_amount=20, subscription_currency="USD", billing_cadence="monthly")
    now = datetime.now(UTC)
    await _seed_tokens(Session, provider="anthropic", start=now - timedelta(days=30), days=30)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/analytics/economics", headers=ADMIN_AUTH)

    assert response.status_code == 200, response.text
    payload = response.json()
    rows = payload["providers"]
    assert len(rows) == 2

    # Neither config claims the shared Hermes workload.
    for row in rows:
        assert row["attribution_ambiguous"] is True
        assert row["comparison_eligible"] is False
        assert row["observed"]["tokens"] == 0
        assert row["api_equivalent"]["value"] is None
        assert "cannot be uniquely attributed" in row["exclusion_reason"]

    # The provider-level workload is reported exactly once, not doubled.
    assert len(payload["provider_level"]) == 1
    rollup = payload["provider_level"][0]
    assert rollup["provider"] == "anthropic"
    assert rollup["config_count"] == 2
    assert rollup["api_equivalent"]["value"] is not None
    assert rollup["api_equivalent"]["value"] > 0

    # Aggregate economics must not double-count the workload.
    assert payload["summary"]["eligible_provider_count"] == 0
    assert payload["summary"]["api_equivalent_value"]["amount"] is None


@pytest.mark.asyncio
async def test_economics_config_id_filter_does_not_hide_ambiguity(sqlite_db):
    """Filtering to one config must not make shared Hermes data look unique.

    The frontend requests /analytics/economics?config_id=<id> for the
    single-provider view. If multiplicity were computed from the filtered result,
    a shared provider would collapse to config_count=1 and the full provider-level
    workload would be attributed to that one config. Multiplicity is global.
    """
    Session = sqlite_db
    first = await _config(Session, provider="anthropic", label="Work", pricing_model="subscription", subscription_amount=20, subscription_currency="USD", billing_cadence="monthly")
    await _config(Session, provider="anthropic", label="Personal", pricing_model="subscription", subscription_amount=20, subscription_currency="USD", billing_cadence="monthly")
    now = datetime.now(UTC)
    await _seed_tokens(Session, provider="anthropic", start=now - timedelta(days=30), days=30)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/analytics/economics", params={"config_id": first.id}, headers=ADMIN_AUTH)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert [row["config_id"] for row in payload["providers"]] == [first.id]

    row = payload["providers"][0]
    # The filtered response still marks the config ambiguous and attributes no
    # config-level Hermes workload, because the provider has two configs.
    assert row["attribution_ambiguous"] is True
    assert row["comparison_eligible"] is False
    assert row["observed"]["tokens"] == 0
    assert row["api_equivalent"]["value"] is None
    assert "cannot be uniquely attributed" in row["exclusion_reason"]
    # Ambiguous configs get no per-billing-period value trend either.
    assert row["trend"] == []

    # The shared provider-level workload is still surfaced exactly once.
    assert len(payload["provider_level"]) == 1
    rollup = payload["provider_level"][0]
    assert rollup["provider"] == "anthropic"
    assert rollup["config_count"] == 2
    assert rollup["api_equivalent"]["value"] is not None
    assert rollup["api_equivalent"]["value"] > 0


@pytest.mark.asyncio
async def test_economics_ambiguous_subscription_gets_empty_trend(sqlite_db):
    """Two subscriptions of the same provider must not each receive the full
    provider workload in their per-billing-period value trend."""
    Session = sqlite_db
    await _config(Session, provider="anthropic", label="Work", pricing_model="subscription", subscription_amount=20, subscription_currency="USD", billing_cadence="monthly", billing_anchor=datetime(2026, 1, 31, tzinfo=UTC))
    await _config(Session, provider="anthropic", label="Personal", pricing_model="subscription", subscription_amount=20, subscription_currency="USD", billing_cadence="monthly", billing_anchor=datetime(2026, 1, 31, tzinfo=UTC))
    start = datetime(2026, 2, 10, tzinfo=UTC)
    end = datetime(2026, 3, 10, tzinfo=UTC)
    async with Session() as session:
        for observed_at in (datetime(2026, 2, 12, tzinfo=UTC), datetime(2026, 3, 5, tzinfo=UTC)):
            session.add(UsageObservation(provider="anthropic", provider_mapping="anthropic", metric="input_tokens", value=1_000_000, unit="tokens", kind="delta", source="hermes", observed_at=observed_at, model="claude-sonnet-4"))
        await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/analytics/economics", params={"from": start.isoformat(), "to": end.isoformat()}, headers=ADMIN_AUTH)

    assert response.status_code == 200, response.text
    rows = response.json()["providers"]
    assert len(rows) == 2
    for row in rows:
        assert row["attribution_ambiguous"] is True
        assert row["trend"] == []


@pytest.mark.asyncio
async def test_economics_rejects_invalid_date_ranges(sqlite_db):
    await _config(sqlite_db, provider="anthropic", pricing_model="subscription", subscription_amount=20, subscription_currency="USD", billing_cadence="monthly")
    now = datetime.now(UTC)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/analytics/economics", params={"from": now.isoformat(), "to": (now - timedelta(days=1)).isoformat()}, headers=ADMIN_AUTH)

    assert response.status_code == 400


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


async def _create_subscription_config(client):
    created = await client.post(
        "/api/v1/configs",
        json={
            "provider": "deepseek",
            "label": "Sub config",
            "api_key": "sk-test",
            "pricing_model": "subscription",
            "subscription_amount": 20,
            "subscription_currency": "usd",
            "billing_cadence": "monthly",
            "billing_anchor": "2026-01-15T00:00:00Z",
        },
        headers=ADMIN_AUTH,
    )
    assert created.status_code == 201, created.text
    return created.json()


@pytest.mark.asyncio
async def test_billing_payg_to_subscription_transition(sqlite_db):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = await client.post(
            "/api/v1/configs",
            json={"provider": "deepseek", "label": "Payg config", "api_key": "sk-test", "pricing_model": "payg"},
            headers=ADMIN_AUTH,
        )
        assert created.status_code == 201, created.text
        config_id = created.json()["id"]

        updated = await client.patch(
            f"/api/v1/configs/{config_id}",
            json={"pricing_model": "subscription", "subscription_amount": 25, "billing_cadence": "monthly"},
            headers=ADMIN_AUTH,
        )
        assert updated.status_code == 200, updated.text
        body = updated.json()
        assert body["pricing_model"] == "subscription"
        assert body["subscription_amount"] == 25
        assert body["billing_cadence"] == "monthly"


@pytest.mark.asyncio
async def test_billing_subscription_to_payg_clears_subscription_fields(sqlite_db):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        payload = await _create_subscription_config(client)
        config_id = payload["id"]

        updated = await client.patch(
            f"/api/v1/configs/{config_id}",
            json={"pricing_model": "payg"},
            headers=ADMIN_AUTH,
        )
        assert updated.status_code == 200, updated.text
        body = updated.json()
        assert body["pricing_model"] == "payg"
        assert body["subscription_amount"] is None
        assert body["billing_cadence"] is None
        assert body["billing_anchor"] is None


@pytest.mark.asyncio
async def test_billing_subscription_to_free_clears_subscription_fields(sqlite_db):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        payload = await _create_subscription_config(client)
        config_id = payload["id"]

        updated = await client.patch(
            f"/api/v1/configs/{config_id}",
            json={"pricing_model": "free"},
            headers=ADMIN_AUTH,
        )
        assert updated.status_code == 200, updated.text
        body = updated.json()
        assert body["pricing_model"] == "free"
        assert body["subscription_amount"] is None
        assert body["billing_cadence"] is None
        assert body["billing_anchor"] is None


@pytest.mark.asyncio
async def test_billing_update_amount_only_keeps_subscription_valid(sqlite_db):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        payload = await _create_subscription_config(client)
        config_id = payload["id"]

        updated = await client.patch(
            f"/api/v1/configs/{config_id}",
            json={"subscription_amount": 99},
            headers=ADMIN_AUTH,
        )
        assert updated.status_code == 200, updated.text
        body = updated.json()
        assert body["pricing_model"] == "subscription"
        assert body["subscription_amount"] == 99
        assert body["billing_cadence"] == "monthly"


@pytest.mark.asyncio
async def test_billing_subscription_without_cadence_is_rejected(sqlite_db):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        payload = await _create_subscription_config(client)
        config_id = payload["id"]

        # Switch to subscription semantics while clearing the cadence -> invalid persisted state.
        updated = await client.patch(
            f"/api/v1/configs/{config_id}",
            json={"billing_cadence": None},
            headers=ADMIN_AUTH,
        )
        assert updated.status_code == 422
        assert "billing_cadence" in updated.json()["detail"]


@pytest.mark.asyncio
async def test_billing_negative_amount_is_rejected(sqlite_db):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        payload = await _create_subscription_config(client)
        config_id = payload["id"]

        updated = await client.patch(
            f"/api/v1/configs/{config_id}",
            json={"subscription_amount": -5},
            headers=ADMIN_AUTH,
        )
        assert updated.status_code == 422


@pytest.mark.asyncio
async def test_billing_unsupported_model_is_rejected(sqlite_db):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        payload = await _create_subscription_config(client)
        config_id = payload["id"]

        updated = await client.patch(
            f"/api/v1/configs/{config_id}",
            json={"pricing_model": "enterprise"},
            headers=ADMIN_AUTH,
        )
        assert updated.status_code == 422


@pytest.mark.asyncio
async def test_economics_payg_reconciliation_surfaces_disagreement(sqlite_db):
    Session = sqlite_db
    config = await _config(Session, provider="openai", pricing_model="payg")
    now = datetime.now(UTC)
    async with Session() as session:
        # Provider-reported actual spend far above the reconstructed token value.
        session.add(UsageObservation(provider_config_id=config.id, provider="openai", metric="daily_cost", value=100, unit="USD", kind="delta", source="native", observed_at=now - timedelta(days=2)))
        # 1M gpt-4o input tokens reconstructs to $2.50.
        session.add(UsageObservation(provider="openai", provider_mapping="openai", metric="input_tokens", value=1_000_000, unit="tokens", kind="delta", source="hermes", observed_at=now - timedelta(days=5), model="gpt-4o"))
        await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/analytics/economics", headers=ADMIN_AUTH)

    row = response.json()["providers"][0]
    assert row["pricing_model"] == "payg"
    assert row["payg_reconciliation"]["authoritative"] == "actual_spend"
    assert row["payg_reconciliation"]["actual_spend"] == 100
    assert row["payg_reconciliation"]["disagreement"] is True
    # Actual spend is authoritative; reconstructed value is not summed/averaged into cost basis.
    assert row["actual_spend"]["amount"] == 100


@pytest.mark.asyncio
async def test_economics_payg_reconciliation_agrees_when_close(sqlite_db):
    Session = sqlite_db
    config = await _config(Session, provider="openai", pricing_model="payg")
    now = datetime.now(UTC)
    async with Session() as session:
        # Actual spend close to the reconstructed $2.50 for 1M gpt-4o input tokens.
        session.add(UsageObservation(provider_config_id=config.id, provider="openai", metric="daily_cost", value=2.4, unit="USD", kind="delta", source="native", observed_at=now - timedelta(days=2)))
        session.add(UsageObservation(provider="openai", provider_mapping="openai", metric="input_tokens", value=1_000_000, unit="tokens", kind="delta", source="hermes", observed_at=now - timedelta(days=5), model="gpt-4o"))
        await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/analytics/economics", headers=ADMIN_AUTH)

    row = response.json()["providers"][0]
    assert row["payg_reconciliation"]["disagreement"] is False


@pytest.mark.asyncio
async def test_economics_subscription_value_trend_by_billing_period(sqlite_db):
    Session = sqlite_db
    await _config(
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
        for observed_at in (
            datetime(2026, 2, 12, tzinfo=UTC),
            datetime(2026, 2, 20, tzinfo=UTC),
            datetime(2026, 2, 27, tzinfo=UTC),
            datetime(2026, 3, 5, tzinfo=UTC),
        ):
            session.add(UsageObservation(provider="anthropic", provider_mapping="anthropic", metric="input_tokens", value=1_000_000, unit="tokens", kind="delta", source="hermes", observed_at=observed_at, model="claude-sonnet-4"))
        await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/analytics/economics", params={"from": start.isoformat(), "to": end.isoformat()}, headers=ADMIN_AUTH)

    row = response.json()["providers"][0]
    assert len(row["trend"]) == 2
    # Two complete billing periods (Jan 31-Feb 28, Feb 28-Mar 31) overlap the range.
    assert row["trend"][0]["period_start"].startswith("2026-01-31")
    assert row["trend"][0]["value_multiplier"] is not None
    assert row["trend"][0]["allocated_cost"]["amount"] > 0
    assert row["trend"][1]["value_multiplier"] is not None
