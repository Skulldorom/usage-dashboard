from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, field_validator

class ProviderInfo(BaseModel):
    id: str
    name: str
    description: str
    metrics: list[str]

class ProviderConfigCreate(BaseModel):
    provider: str = Field(..., examples=["firecrawl"])
    label: str | None = Field(default=None, max_length=120)
    api_key: str = Field(..., min_length=1)
    base_url: str | None = None
    extra: dict = Field(default_factory=dict)
    is_enabled: bool = True
    is_visible: bool = True
    display_order: int | None = Field(default=None, ge=0)

    @field_validator("label", mode="before")
    @classmethod
    def _blank_label_to_none(cls, value: str | None) -> str | None:
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value

class ProviderConfigUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=120)
    api_key: str | None = Field(default=None, min_length=1)
    base_url: str | None = None
    extra: dict | None = None
    is_enabled: bool | None = None
    is_visible: bool | None = None
    display_order: int | None = Field(default=None, ge=0)

    def has_update_for(self, field_name: str) -> bool:
        return field_name in self.model_fields_set

class ProviderConfigRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    provider: str
    label: str
    base_url: str | None
    extra: dict
    is_enabled: bool
    is_visible: bool
    display_order: int
    created_at: datetime
    updated_at: datetime
    api_key_masked: str = "••••••••"

class ProviderConfigOrderUpdate(BaseModel):
    config_ids: list[int] = Field(..., min_length=1)


class UsageMetric(BaseModel):
    label: str
    value: float | int | str | bool | None
    unit: str | None = None
    maximum: float | int | None = None

class UsageSnapshotRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    provider_config_id: int
    provider: str
    status: str
    summary: str
    metrics: list[UsageMetric]
    raw: dict
    error: str | None
    checked_at: datetime

class ProviderUsageRead(BaseModel):
    status: str
    summary: str
    metrics: list[UsageMetric]
    raw: dict

class DashboardConfigUsage(BaseModel):
    config: ProviderConfigRead
    latest: UsageSnapshotRead | None = None

class HomepageProviderRow(BaseModel):
    provider: str
    config_id: int
    label: str
    value: str
    status: str

class HomepagePayload(BaseModel):
    configured_providers: int
    healthy_providers: int
    degraded_providers: int
    latest_check: str | None
    summary: str
    metrics: dict[str, float | int | str | bool | None]
    list: list[HomepageProviderRow]


class PollStatusRead(BaseModel):
    auto_poll_enabled: bool
    interval_seconds: int
    is_polling: bool
    last_polled_at: str | None
    next_poll_at: str | None
