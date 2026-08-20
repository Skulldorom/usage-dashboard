from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    app_name: str = "Usage Dashboard"
    api_v1_prefix: str = "/api/v1"
    database_url: str = "sqlite+aiosqlite:///./usage-dashboard.db"
    encryption_key: str = Field(..., min_length=32)
    admin_session_expire_hours: int = Field(default=24, ge=1)
    admin_recovery_code_expire_minutes: int = Field(default=30, ge=1)
    backend_cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    request_timeout_seconds: float = 20.0
    snapshot_retention_days: int = 90
    auto_poll_enabled: bool = True
    auto_poll_interval_minutes: int = Field(default=60, ge=1)
    custom_http_allowed_hosts_raw: str = Field(default="", alias="CUSTOM_HTTP_ALLOWED_HOSTS")
    homepage_allowed_hosts_raw: str = Field(default="", alias="HOMEPAGE_ALLOWED_HOSTS")

    @staticmethod
    def _parse_hosts(value: str) -> set[str]:
        return {host.strip().rstrip(".").lower() for host in value.split(",") if host.strip()}

    @property
    def custom_http_allowed_hosts(self) -> set[str]:
        return self._parse_hosts(self.custom_http_allowed_hosts_raw)

    @property
    def homepage_allowed_hosts(self) -> set[str]:
        return self._parse_hosts(self.homepage_allowed_hosts_raw)

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.backend_cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
