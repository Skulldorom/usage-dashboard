from functools import lru_cache
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    app_name: str = "Usage Dashboard"
    api_v1_prefix: str = "/api/v1"
    database_url: str = "sqlite+aiosqlite:///./usage-dashboard.db"
    encryption_key: str = Field(..., min_length=32)
    admin_token: str | None = Field(default=None, min_length=16)
    backend_cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    request_timeout_seconds: float = 20.0
    snapshot_retention_days: int = 90
    custom_http_allowed_hosts_raw: str = Field(default="", alias="CUSTOM_HTTP_ALLOWED_HOSTS")
    homepage_allowed_hosts_raw: str = Field(default="", alias="HOMEPAGE_ALLOWED_HOSTS")

    @field_validator("admin_token", mode="before")
    @classmethod
    def _blank_admin_token_to_none(cls, value: str | None) -> str | None:
        if isinstance(value, str) and not value.strip():
            return None
        return value

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
