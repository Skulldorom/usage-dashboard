from pathlib import Path
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from app.database import get_session
from app.main import app
from app.models import Base

DB = Path("/tmp/usage_dashboard_test_api.db")
TEST_DATABASE_URL = f"sqlite+aiosqlite:///{DB}"

@pytest_asyncio.fixture(autouse=True)
async def sqlite_db():
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
    yield
    app.dependency_overrides.clear()
    await engine.dispose()
    if DB.exists():
        DB.unlink()

@pytest.mark.asyncio
async def test_config_crud_and_homepage():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        providers = await client.get("/api/v1/providers")
        assert providers.status_code == 200
        created = await client.post("/api/v1/configs", json={"provider": "deepseek", "label": "main", "api_key": "sk-test"})
        assert created.status_code == 201, created.text
        payload = created.json()
        assert payload["api_key_masked"] == "••••••••"
        assert "api_key" not in payload
        configs = await client.get("/api/v1/configs")
        assert len(configs.json()) == 1
        homepage = await client.get("/api/v1/homepage")
        assert homepage.status_code == 200
        assert homepage.json()["configured_providers"] == 1
        deleted = await client.delete(f"/api/v1/configs/{payload['id']}")
        assert deleted.status_code == 204
