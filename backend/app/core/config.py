from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    app_name: str = "Usage Dashboard"
    api_v1_prefix: str = "/api/v1"
    database_url: str = "sqlite+aiosqlite:///./usage-dashboard.db"
    encryption_key: str = Field(..., min_length=32)
    backend_cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    request_timeout_seconds: float = 20.0

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.backend_cors_origins.split(",") if o.strip()]

@lru_cache
def get_settings() -> Settings:
    return Settings()

settings = get_settings()
