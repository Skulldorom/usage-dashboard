"""Tests for data source background polling (app.datasources.scheduler)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.crypto import CryptoService
from app.datasources import scheduler
from app.datasources import service as ds_service
from app.models import Base, DataSourceConfig, UsageObservation

DB = Path("/tmp/usage_dashboard_test_polling.db")


@pytest_asyncio.fixture
async def session_factory():
    if DB.exists():
        DB.unlink()
    engine = create_async_engine(f"sqlite+aiosqlite:///{DB}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    yield Session
    await engine.dispose()
    if DB.exists():
        DB.unlink()


@pytest_asyncio.fixture(autouse=True)
async def _reset_scheduler_state():
    # asyncio.Lock binds to an event loop on first acquire, and pytest-asyncio
    # runs each test on a fresh loop - clear module state so locks/tasks don't
    # leak across tests.
    ds_service._locks.clear()
    scheduler._task = None
    yield
    ds_service._locks.clear()
    scheduler._task = None


class _FakeHermes:
    """Adapter stub: fails for base_url 'fail', otherwise returns one record."""

    id = "hermes"

    async def fetch_observations(self, base_url, token, extra, timeout):
        if base_url == "fail":
            raise ValueError("boom")
        return [{"timestamp": "2026-08-22T12:00:00+00:00", "provider": "anthropic", "input_tokens": 10}]


async def _seed_source(Session, *, base_url="http://ok", is_enabled=True, last_attempt_at=None, interval=60):
    async with Session() as session:
        source = DataSourceConfig(
            kind="hermes",
            name=base_url,
            base_url=base_url,
            is_enabled=is_enabled,
            poll_interval_minutes=interval,
            last_attempt_at=last_attempt_at,
        )
        session.add(source)
        await session.commit()
        await session.refresh(source)
        return source.id


async def _get_source(Session, source_id):
    async with Session() as session:
        return await session.get(DataSourceConfig, source_id)


# --- is_due (pure) ---


def test_is_due_when_never_attempted():
    assert scheduler.is_due(None, 60) is True


def test_is_due_respects_interval():
    now = datetime.now(UTC)
    assert scheduler.is_due(now - timedelta(minutes=61), 60, now=now) is True
    assert scheduler.is_due(now - timedelta(minutes=59), 60, now=now) is False


# --- discover_due_sources ---


@pytest.mark.asyncio
async def test_discover_due_sources_filters_enabled_and_due(session_factory):
    now = datetime.now(UTC)
    due = await _seed_source(session_factory, base_url="due")  # never attempted → due
    not_due = await _seed_source(session_factory, base_url="not-due", last_attempt_at=now)  # recent
    disabled = await _seed_source(session_factory, base_url="disabled", is_enabled=False)

    ids = await scheduler.discover_due_sources(session_factory)
    assert due in ids
    assert not_due not in ids
    assert disabled not in ids


# --- poll_one / poll_due_sources ---


@pytest.mark.asyncio
async def test_poll_one_updates_success_health(monkeypatch, session_factory):
    monkeypatch.setattr(ds_service, "get_data_source", lambda kind: _FakeHermes)
    source_id = await _seed_source(session_factory)

    await scheduler.poll_one(source_id, session_factory)

    source = await _get_source(session_factory, source_id)
    assert source.last_attempt_at is not None
    assert source.last_success_at is not None
    assert source.consecutive_failures == 0
    assert source.latest_error is None


@pytest.mark.asyncio
async def test_poll_one_records_failure(monkeypatch, session_factory):
    monkeypatch.setattr(ds_service, "get_data_source", lambda kind: _FakeHermes)
    source_id = await _seed_source(session_factory, base_url="fail")

    await scheduler.poll_one(source_id, session_factory)

    source = await _get_source(session_factory, source_id)
    assert source.last_attempt_at is not None
    assert source.last_failure_at is not None
    assert source.consecutive_failures == 1
    assert source.latest_error == "boom"


@pytest.mark.asyncio
async def test_poll_due_sources_failure_isolation(monkeypatch, session_factory):
    monkeypatch.setattr(ds_service, "get_data_source", lambda kind: _FakeHermes)
    good_id = await _seed_source(session_factory, base_url="ok")
    bad_id = await _seed_source(session_factory, base_url="fail")

    # Must not raise despite one source failing.
    await scheduler.poll_due_sources(session_factory)

    good = await _get_source(session_factory, good_id)
    bad = await _get_source(session_factory, bad_id)
    assert good.last_success_at is not None
    assert bad.last_failure_at is not None
    assert bad.latest_error == "boom"

    # The good source actually persisted its observation.
    async with session_factory() as session:
        count = await session.scalar(
            select(func.count(UsageObservation.id)).where(UsageObservation.data_source_id == good_id)
        )
    assert count == 1


@pytest.mark.asyncio
async def test_concurrent_syncs_do_not_duplicate(monkeypatch, session_factory):
    monkeypatch.setattr(ds_service, "get_data_source", lambda kind: _FakeHermes)
    source_id = await _seed_source(session_factory)
    crypto = CryptoService(settings.encryption_key)

    async def run():
        async with session_factory() as session:
            source = await session.get(DataSourceConfig, source_id)
            return await ds_service.sync_data_source(session, source, crypto)

    await asyncio.gather(run(), run())

    async with session_factory() as session:
        count = await session.scalar(
            select(func.count(UsageObservation.id)).where(UsageObservation.data_source_id == source_id)
        )
    assert count == 1


# --- lifecycle ---


@pytest.mark.asyncio
async def test_start_stop_cancels_cleanly(monkeypatch):
    monkeypatch.setattr(scheduler, "TICK_SECONDS", 3600)  # long sleep, never fires
    scheduler.start_data_source_polling()
    task = scheduler._task
    assert task is not None and not task.done()

    await scheduler.stop_data_source_polling()

    assert scheduler._task is None
    assert task.done()
