import logging

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.database import get_session
from app.main import app
from app.models import Base


@pytest_asyncio.fixture
async def auth_db(tmp_path, monkeypatch):
    db_path = tmp_path / "auth.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    monkeypatch.setattr(settings, "admin_session_expire_hours", 24)
    monkeypatch.setattr(settings, "admin_recovery_code_expire_minutes", 30)

    async def override_session():
        async with Session() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    yield Session
    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.mark.asyncio
async def test_first_run_setup_uses_backend_log_code(auth_db, caplog):
    caplog.set_level(logging.WARNING, logger="app.core.auth")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        status = await client.get("/api/v1/auth/status")
        assert status.status_code == 200
        assert status.json()["is_configured"] is False
        assert status.json()["setup_required"] is True

        missing_code = await client.post("/api/v1/auth/setup", json={"code": "wrong", "password": "correct horse battery staple"})
        assert missing_code.status_code == 400

        setup_code = next(record.message.rsplit(" ", 1)[-1] for record in caplog.records if "Admin setup code:" in record.message)
        configured = await client.post("/api/v1/auth/setup", json={"code": setup_code, "password": "correct horse battery staple"})
        assert configured.status_code == 200, configured.text
        token = configured.json()["access_token"]
        assert len(token) >= 32

        status = await client.get("/api/v1/auth/status")
        assert status.json()["is_configured"] is True
        assert status.json()["setup_required"] is False

        protected = await client.get("/api/v1/configs", headers={"Authorization": f"Bearer {token}"})
        assert protected.status_code == 200

        second_setup = await client.post("/api/v1/auth/setup", json={"code": setup_code, "password": "another correct password"})
        assert second_setup.status_code == 409


@pytest.mark.asyncio
async def test_login_and_logout_session_tokens(auth_db, caplog):
    caplog.set_level(logging.WARNING, logger="app.core.auth")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.get("/api/v1/auth/status")
        setup_code = next(record.message.rsplit(" ", 1)[-1] for record in caplog.records if "Admin setup code:" in record.message)
        await client.post("/api/v1/auth/setup", json={"code": setup_code, "password": "correct horse battery staple"})

        bad_login = await client.post("/api/v1/auth/login", json={"password": "wrong password"})
        assert bad_login.status_code == 401

        login = await client.post("/api/v1/auth/login", json={"password": "correct horse battery staple"})
        assert login.status_code == 200, login.text
        token = login.json()["access_token"]

        authorized = await client.get("/api/v1/configs", headers={"Authorization": f"Bearer {token}"})
        assert authorized.status_code == 200

        logged_out = await client.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {token}"})
        assert logged_out.status_code == 204

        rejected = await client.get("/api/v1/configs", headers={"Authorization": f"Bearer {token}"})
        assert rejected.status_code == 401


@pytest.mark.asyncio
async def test_password_reset_uses_backend_log_code(auth_db, caplog):
    caplog.set_level(logging.WARNING, logger="app.core.auth")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.get("/api/v1/auth/status")
        setup_code = next(record.message.rsplit(" ", 1)[-1] for record in caplog.records if "Admin setup code:" in record.message)
        await client.post("/api/v1/auth/setup", json={"code": setup_code, "password": "old correct password"})

        requested = await client.post("/api/v1/auth/reset/request")
        assert requested.status_code == 202
        reset_code = next(record.message.rsplit(" ", 1)[-1] for record in caplog.records if "Admin password reset code:" in record.message)

        wrong_code = await client.post("/api/v1/auth/reset/complete", json={"code": "wrong", "password": "new correct password"})
        assert wrong_code.status_code == 400

        reset = await client.post("/api/v1/auth/reset/complete", json={"code": reset_code, "password": "new correct password"})
        assert reset.status_code == 200, reset.text
        token = reset.json()["access_token"]

        old_login = await client.post("/api/v1/auth/login", json={"password": "old correct password"})
        assert old_login.status_code == 401

        new_login = await client.post("/api/v1/auth/login", json={"password": "new correct password"})
        assert new_login.status_code == 200

        protected = await client.get("/api/v1/configs", headers={"Authorization": f"Bearer {token}"})
        assert protected.status_code == 200
