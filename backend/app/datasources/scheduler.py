"""Background polling for enabled data sources.

Runs alongside the provider auto-poll loop. Each enabled data source is polled
on its own ``poll_interval_minutes``, with per-source locking to avoid
overlapping syncs and failure isolation so one broken source can't stop the
others.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.config import settings
from app.core.crypto import CryptoService
from app.database import engine
from app.datasources.service import sync_data_source
from app.models import DataSourceConfig

logger = logging.getLogger(__name__)

# How often the poller wakes to check for due sources. Due-ness is computed from
# each source's last_attempt_at and its own poll_interval_minutes, so this tick
# only bounds the scheduling granularity (not the per-source cadence).
TICK_SECONDS = 60

_task: asyncio.Task | None = None


def is_due(last_attempt_at: datetime | None, interval_minutes: int, now: datetime | None = None) -> bool:
    """Whether a source is due for a poll."""
    current = now or datetime.now(UTC)
    if last_attempt_at is None:
        return True
    last = last_attempt_at if last_attempt_at.tzinfo else last_attempt_at.replace(tzinfo=UTC)
    return (current - last) >= timedelta(minutes=max(interval_minutes, 1))


async def discover_due_sources(session_factory: async_sessionmaker) -> list[int]:
    """Return the ids of enabled data sources that are due for a poll."""
    async with session_factory() as session:
        sources = (
            await session.execute(
                select(DataSourceConfig).where(DataSourceConfig.is_enabled.is_(True))
            )
        ).scalars().all()
        now = datetime.now(UTC)
        return [s.id for s in sources if is_due(s.last_attempt_at, s.poll_interval_minutes, now)]


async def poll_one(source_id: int, session_factory: async_sessionmaker) -> None:
    """Sync a single data source.

    Each source gets its own session; ``sync_data_source`` serializes concurrent
    syncs of the same source via a per-source lock, and a failure here never
    affects other sources (callers gather with ``return_exceptions=True``).
    """
    async with session_factory() as session:
        source = await session.get(DataSourceConfig, source_id)
        if source is None or not source.is_enabled:
            return
        await sync_data_source(session, source, CryptoService(settings.encryption_key))


async def poll_due_sources(session_factory: async_sessionmaker) -> None:
    """Poll all due data sources with failure isolation."""
    due = await discover_due_sources(session_factory)
    if not due:
        return
    results = await asyncio.gather(
        *(poll_one(source_id, session_factory) for source_id in due),
        return_exceptions=True,
    )
    for source_id, result in zip(due, results):
        if isinstance(result, Exception):
            logger.warning("Data source %s poll failed: %s", source_id, result)


async def _loop() -> None:
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    while True:
        await asyncio.sleep(TICK_SECONDS)
        try:
            await poll_due_sources(session_factory)
        except Exception:  # noqa: BLE001 - a scheduler hiccup must not kill the loop
            logger.exception("Data source poller iteration failed")


def start_data_source_polling() -> None:
    """Start the background data source poller (idempotent)."""
    global _task
    if _task is None or _task.done():
        _task = asyncio.create_task(_loop())


async def stop_data_source_polling() -> None:
    """Cancel the background poller and await its termination."""
    global _task
    if _task is not None:
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
    _task = None
