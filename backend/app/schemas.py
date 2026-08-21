from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

class AuthStatusRead(BaseModel):
    is_configured: bool
    setup_required: bool

class AuthPasswordRequest(BaseModel):
    password: str = Field(..., min_length=12, max_length=1024)

class AuthCodePasswordRequest(AuthPasswordRequest):
    code: str = Field(..., min_length=1, max_length=128)

class AuthTokenRead(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime



API_TOKEN_SCOPES = {"usage:read", "poll:write", "configs:read", "history:read", "analytics:read"}

class ApiTokenCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    scopes: list[str] = Field(default_factory=list)
    expires_at: datetime | None = None

    @field_validator("name")
    @classmethod
    def _strip_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Token name is required")
        return stripped

    @field_validator("scopes")
    @classmethod
    def _validate_scopes(cls, value: list[str]) -> list[str]:
        scopes = sorted(set(value))
        invalid = [scope for scope in scopes if scope not in API_TOKEN_SCOPES]
        if invalid:
            raise ValueError(f"Unsupported API token scope: {invalid[0]}")
        if not scopes:
            raise ValueError("At least one scope is required")
        return scopes

class ApiTokenRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    token_prefix: str
    scopes: list[str]
    expires_at: datetime | None
    revoked_at: datetime | None
    last_used_at: datetime | None
    created_at: datetime

class ApiTokenCreated(ApiTokenRead):
    token: str

class ProviderAlertMetric(BaseModel):
    metric: str
    label: str
    unit: str | None = None
    direction: Literal["increasing", "decreasing"] = "increasing"

class ProviderIcon(BaseModel):
    viewBox: str
    path: str

class ProviderInfo(BaseModel):
    id: str
    name: str
    description: str
    metrics: list[str]
    alert_metrics: list[ProviderAlertMetric] = Field(default_factory=list)
    icon: ProviderIcon | None = None

class ThresholdRule(BaseModel):
    metric: str = Field(..., min_length=1, max_length=120)
    direction: Literal["increasing", "decreasing"] = "increasing"
    warning: float | None = Field(default=None)
    critical: float | None = Field(default=None)
    exhausted: float | None = Field(default=None)

    @field_validator("metric")
    @classmethod
    def _strip_metric(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Threshold metric is required")
        return stripped

    @model_validator(mode="after")
    def _at_least_one_threshold(self):
        if self.warning is None and self.critical is None and self.exhausted is None:
            raise ValueError("At least one threshold (warning, critical, or exhausted) is required")
        return self

class ProviderConfigCreate(BaseModel):
    provider: str = Field(..., examples=["firecrawl"])
    label: str | None = Field(default=None, max_length=120)
    api_key: str = Field(..., min_length=1)
    base_url: str | None = None
    extra: dict = Field(default_factory=dict)
    is_enabled: bool = True
    is_visible: bool = True
    display_order: int | None = Field(default=None, ge=0)
    alert_thresholds: list[ThresholdRule] = Field(default_factory=list)

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
    alert_thresholds: list[ThresholdRule] | None = None

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
    alert_thresholds: list[ThresholdRule] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    api_key_masked: str = "••••••••"

class ProviderConfigOrderUpdate(BaseModel):
    config_ids: list[int] = Field(..., min_length=1)


class CodexDevicePollRequest(BaseModel):
    label: str | None = Field(default=None, max_length=120)

    @field_validator("label", mode="before")
    @classmethod
    def _blank_label_to_none(cls, value: str | None) -> str | None:
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value


class CodexDeviceStartRead(BaseModel):
    flow_id: str
    user_code: str
    verification_uri: str
    verification_uri_complete: str | None = None
    expires_at: str
    interval_seconds: int


class CodexDevicePollRead(BaseModel):
    status: str
    interval_seconds: int | None = None
    error: str | None = None
    config: ProviderConfigRead | None = None


class CodexBrowserStartRead(BaseModel):
    flow_id: str
    authorization_url: str
    redirect_uri: str
    expires_at: str


class CodexBrowserCompleteRequest(BaseModel):
    callback: str = Field(..., min_length=1)
    label: str | None = Field(default=None, max_length=120)

    @field_validator("label", mode="before")
    @classmethod
    def _blank_label_to_none(cls, value: str | None) -> str | None:
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value


class CodexBrowserCompleteRead(BaseModel):
    status: str
    error: str | None = None
    config: ProviderConfigRead | None = None


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

class AlertStateRead(BaseModel):
    metric: str
    metric_type: str
    value: float | int | None
    unit: str | None
    direction: str
    alert_state: str
    thresholds: dict[str, float | None]

class DashboardConfigUsage(BaseModel):
    config: ProviderConfigRead
    latest: UsageSnapshotRead | None = None
    alerts: list[AlertStateRead] = Field(default_factory=list)
    alert_state: str = "normal"

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
