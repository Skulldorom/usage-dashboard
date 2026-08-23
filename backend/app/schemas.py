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



API_TOKEN_SCOPES = {"usage:read", "poll:write", "configs:read", "history:read", "analytics:read", "datasources:read"}

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
    config_id: int | None = Field(default=None, ge=1)

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
    config_id: int | None = Field(default=None, ge=1)

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

class ProviderHealth(BaseModel):
    status: str
    last_attempt_at: datetime | None = None
    last_success_at: datetime | None = None
    last_failure_at: datetime | None = None
    consecutive_failures: int = 0
    latest_error: str | None = None
    age_seconds: float | None = None
    is_stale: bool = False


class DashboardConfigUsage(BaseModel):
    config: ProviderConfigRead
    latest: UsageSnapshotRead | None = None
    last_good: UsageSnapshotRead | None = None
    health: ProviderHealth | None = None
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


# ---------------------------------------------------------------------------
# Data sources (observed telemetry) — distinct from providers.
# ---------------------------------------------------------------------------


class DataSourceInfo(BaseModel):
    id: str
    name: str
    description: str
    metrics: list[str]


class DataSourceConfigCreate(BaseModel):
    kind: str = Field(..., examples=["hermes"])
    name: str | None = Field(default=None, max_length=120)
    base_url: str | None = None
    token: str | None = None
    profiles: list[str] | None = None
    provider_mappings: dict[str, str] | None = None
    poll_interval_minutes: int = Field(default=60, ge=1)
    is_enabled: bool = True


class DataSourceConfigUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    base_url: str | None = None
    token: str | None = None
    profiles: list[str] | None = None
    provider_mappings: dict[str, str] | None = None
    poll_interval_minutes: int | None = Field(default=None, ge=1)
    is_enabled: bool | None = None

    def has_update_for(self, field_name: str) -> bool:
        return field_name in self.model_fields_set


class DataSourceStatus(BaseModel):
    status: str
    last_attempt_at: datetime | None = None
    last_success_at: datetime | None = None
    last_failure_at: datetime | None = None
    consecutive_failures: int = 0
    latest_error: str | None = None


class DataSourceConfigRead(BaseModel):
    id: int
    kind: str
    name: str
    base_url: str | None
    profiles: list[str] = Field(default_factory=list)
    provider_mappings: dict[str, str] = Field(default_factory=dict)
    poll_interval_minutes: int
    is_enabled: bool
    created_at: datetime
    updated_at: datetime
    token_masked: str = "••••••••"
    status: DataSourceStatus | None = None


class DataSourceSyncResult(BaseModel):
    status: str
    inserted: int = 0
    observed: int = 0
    duplicates_skipped: int = 0
    records_fetched: int = 0
    records_accepted: int = 0
    observations_produced: int = 0
    observations_accepted: int = 0
    records_skipped_invalid_timestamp: int = 0
    records_skipped_no_supported_metrics: int = 0
    metrics_skipped_invalid: int = 0
    observations_skipped_profile_filter: int = 0
    earliest_observation_at: datetime | None = None
    latest_observation_at: datetime | None = None
    providers_discovered: list[str] = Field(default_factory=list)
    profiles_discovered: list[str] = Field(default_factory=list)
    unmapped_providers: list[str] = Field(default_factory=list)
    error: str | None = None


class DataSourceObservationRead(BaseModel):
    id: int
    observed_at: datetime
    provider: str
    provider_mapping: str | None = None
    model: str | None = None
    profile: str | None = None
    session_id: str | None = None
    metric: str
    value: float
    unit: str | None = None
    cost_type: str | None = None
    source_event_id: str | None = None


class DataSourceInspection(BaseModel):
    source: DataSourceConfigRead
    observations: list[DataSourceObservationRead]


# ---------------------------------------------------------------------------
# Hermes attribution / breakdown.
# ---------------------------------------------------------------------------


class AttributionMetric(BaseModel):
    metric: str
    unit: str | None = None
    provider_total: float | None = None
    hermes_observed: float | None = None
    attributed: float | None = None
    unattributed: float | None = None
    overage: float | None = None
    attribution_pct: float | None = None
    status: str = "unavailable"


class Attribution(BaseModel):
    provider_config_id: int
    provider: str
    label: str
    period: dict
    metrics: list[AttributionMetric]


class HermesGroupRow(BaseModel):
    key: str
    cost: float | None = None
    tokens: float | None = None
    requests: float | None = None


class HermesBreakdownDaily(BaseModel):
    date: str
    cost: float | None = None
    tokens: float | None = None
    requests: float | None = None


class HermesTotal(BaseModel):
    metric: str
    unit: str | None = None
    value: float | None = None


class HermesSourceSummary(BaseModel):
    id: int
    name: str
    status: str
    is_enabled: bool
    base_url: str | None = None
    last_success_at: datetime | None = None
    last_attempt_at: datetime | None = None
    latest_error: str | None = None
    latest_observation_at: datetime | None = None
    observations_in_range: int = 0
    total_observations: int = 0
    profiles: list[str] = Field(default_factory=list)
    provider_mappings: dict[str, str] = Field(default_factory=dict)
    providers_observed: list[str] = Field(default_factory=list)
    providers_unmapped: list[str] = Field(default_factory=list)


class HermesDiagnostic(BaseModel):
    severity: Literal["info", "warning", "error"] = "info"
    message: str


class HermesBreakdown(BaseModel):
    period: dict
    totals: list[HermesTotal]
    sessions: int = 0
    by_provider: list[HermesGroupRow]
    by_model: list[HermesGroupRow]
    by_profile: list[HermesGroupRow]
    daily: list[HermesBreakdownDaily]
    sources: list[HermesSourceSummary] = Field(default_factory=list)
    diagnostics: list[HermesDiagnostic] = Field(default_factory=list)
