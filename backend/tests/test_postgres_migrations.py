"""PostgreSQL-only migration regressions run after Alembic reaches head."""

from __future__ import annotations

import os

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

pytestmark = pytest.mark.skipif(
    os.getenv("POSTGRES_MIGRATION_TEST") != "1",
    reason="requires a PostgreSQL database migrated to head",
)


@pytest.mark.asyncio
async def test_session_id_text_round_trip_after_migration():
    session_id = "hermes:company:" + "x" * 140
    engine = create_async_engine(os.environ["DATABASE_URL"])
    try:
        async with engine.begin() as connection:
            column_type = await connection.scalar(
                text(
                    "SELECT data_type FROM information_schema.columns WHERE table_name = 'usage_observations' AND column_name = 'session_id'"
                )
            )
            stored_session_id = await connection.scalar(
                text(
                    """
                    INSERT INTO usage_observations
                        (provider, metric, value, kind, source, observed_at, session_id)
                    VALUES
                        ('anthropic', 'input_tokens', 1, 'delta', 'hermes', now(), :session_id)
                    RETURNING session_id
                    """
                ),
                {"session_id": session_id},
            )
    finally:
        await engine.dispose()

    assert column_type == "text"
    assert stored_session_id == session_id
    assert len(stored_session_id) > 128
