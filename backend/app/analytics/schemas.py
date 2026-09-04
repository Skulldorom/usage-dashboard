"""Pydantic response models for the analytics API."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas import ProviderConfigRead


class AnalyticsMetricInfo(BaseModel):
    label: str
    type: str
    unit: str | None = None
    direction: str = "increasing"
    aggregations: list[str] = []
    deltas: bool = True
    maximum: float | int | None = None
    reset_metric: str | None = None
    window: str | None = None


class AnalyticsProviderInfo(BaseModel):
    config: ProviderConfigRead
    provider: str
    supported: bool
    native_history: bool
    metrics: list[AnalyticsMetricInfo]
    preferred_metric: str | None = None


class AnalyticsBucket(BaseModel):
    start: datetime
    end: datetime
    total: float | None = None
    value: float | None = None
    min: float | None = None
    max: float | None = None
    avg: float | None = None
    samples: int = 0
    delta_samples: int = 0
    coverage: float = 0.0


class CoverageInfo(BaseModel):
    expected: int
    actual: int
    coverage: float
    span_seconds: float
    median_gap_seconds: float | None = None


class HermesOverlay(BaseModel):
    """Hermes-observed usage aligned to a provider's native timeseries.

    ``compatible`` is False when the provider metric has no comparable Hermes
    counterpart (state/percent/credits), the provider is unmapped, or there is
    no Hermes data for the selected range - ``reason`` explains which.
    """

    compatible: bool = False
    metric: str | None = None
    hermes_metrics: list[str] = Field(default_factory=list)
    unit: str | None = None
    buckets: list[AnalyticsBucket] = Field(default_factory=list)
    reason: str | None = None


class AnalyticsTimeseries(BaseModel):
    metric: str
    metric_type: str
    unit: str | None = None
    interval: str
    timezone: str
    buckets: list[AnalyticsBucket]
    coverage: CoverageInfo
    hermes_overlay: HermesOverlay | None = None


class AnalyticsDailyRow(BaseModel):
    date: str
    start: datetime
    usage: float | None = None
    value: float | None = None
    peak_hour: int | None = None
    change_pct: float | None = None
    samples: int = 0


class AnalyticsHourlyRow(BaseModel):
    hour: int
    start: datetime
    value: float | None = None
    total: float | None = None
    samples: int = 0


class AnalyticsComparison(BaseModel):
    metric: str
    current: float | None = None
    previous: float | None = None
    change_pct: float | None = None
    current_window: dict
    previous_window: dict


class AnalyticsSummaryCard(BaseModel):
    provider_config_id: int
    provider: str
    label: str
    metric: str
    metric_type: str
    unit: str | None = None
    usage_today: float | None = None
    usage_week: float | None = None
    avg_per_day: float | None = None
    current_rate: float | None = None
    projected_at_reset: float | None = None
    trend_pct: float | None = None
    coverage: float = 0.0
    confidence: str = "low"


class AnalyticsSummary(BaseModel):
    providers: list[AnalyticsSummaryCard]


class OverviewProvider(BaseModel):
    config_id: int
    provider: str
    label: str
    metric: str | None = None
    unit: str | None = None
    value: float | None = None
    share_pct: float | None = None
    utilization_metric: str | None = None
    utilization_pct: float | None = None
    remaining_pct: float | None = None
    overage_pct: float | None = None
    reset_at: datetime | None = None
    trend_pct: float | None = None
    utilization_trend_pct: float | None = None
    forecast_pct: float | None = None
    quality: str = "limited"
    data_state: str = "limited"
    exclusion_reason: str | None = None
    coverage: float = 0.0
    confidence: str = "low"
    authoritative_source: str | None = None
    corroborating_sources: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    hermes_activity: dict[str, float] = Field(default_factory=dict)
    attribution: list[dict] = Field(default_factory=list)
    audit: dict = Field(default_factory=dict)
    estimated_cost: float | None = None
    estimated_cost_source: str | None = None
    disambiguate: bool = False


class OverviewCoverage(BaseModel):
    measurable_provider_count: int = 0
    total_provider_count: int = 0
    providers_with_history: int = 0
    providers_with_forecasts: int = 0
    stale_or_unavailable_provider_count: int = 0


class OverviewPressure(BaseModel):
    provider_pressure_pct: float | None = None
    measurable_provider_count: int = 0
    total_provider_count: int = 0
    trend_pct: float | None = None
    coverage: OverviewCoverage


class OverviewRisk(BaseModel):
    config_id: int
    provider: str
    label: str
    utilization_pct: float
    remaining_pct: float | None = None
    overage_pct: float | None = None
    reset_at: datetime | None = None
    forecast_pct: float | None = None
    confidence: str = "low"
    state: str = "normal"
    reason: str
    disambiguate: bool = False


class OverviewComparisonSeries(BaseModel):
    config_id: int
    provider: str
    label: str
    metric: str
    window: str | None = None
    display_name: str | None = None
    source: str | None = None
    confidence: str = "low"
    buckets: list[AnalyticsBucket]
    disambiguate: bool = False


class OverviewActivityProvider(BaseModel):
    config_id: int
    provider: str
    label: str
    metric: str
    unit: str
    value: float | None = None
    share_pct: float | None = None
    source: str | None = None
    confidence: str = "low"
    buckets: list[AnalyticsBucket] = Field(default_factory=list)
    disambiguate: bool = False


class OverviewActivityDimension(BaseModel):
    dimension: str
    unit: str
    total: float = 0.0
    providers: list[OverviewActivityProvider] = Field(default_factory=list)


class ProviderCapacity(BaseModel):
    config_id: int
    provider: str
    label: str
    metric: str | None = None
    window: str | None = None
    capacity_used_pct: float | None = None
    capacity_remaining_pct: float | None = None
    overage_pct: float | None = None
    reset_at: datetime | None = None
    window_start: datetime | None = None
    window_end: datetime | None = None
    source: str | None = None
    confidence: str = "low"
    pace_ratio: float | None = None
    sustainable_rate: float | None = None
    burn_rate: float | None = None
    quota_impact: dict | None = None
    buckets: list[AnalyticsBucket] = Field(default_factory=list)


class AnalyticsOverview(BaseModel):
    period: dict
    totals: dict[str, float]
    provider_pressure_pct: float | None = None
    measurable_provider_count: int = 0
    total_provider_count: int = 0
    pressure: OverviewPressure | None = None
    highest_utilization: OverviewProvider | None = None
    coverage: OverviewCoverage | None = None
    risks: list[OverviewRisk] = []
    providers: list[OverviewProvider]
    comparison: list[OverviewComparisonSeries]
    activity: list[OverviewActivityDimension] = Field(default_factory=list)


class EconomicsMoney(BaseModel):
    amount: float | None = None
    currency: str = "USD"
    kind: str
    estimated: bool = False
    allocation: str | None = None
    source: str | None = None
    comparable: bool = True
    reason: str | None = None


class EconomicsObserved(BaseModel):
    tokens: float = 0.0
    priced_tokens: float = 0.0
    unpriced_tokens: float = 0.0
    priced_token_pct: float | None = None
    attribution_state: str = "insufficient"
    pricing_coverage: dict = Field(default_factory=dict)
    attribution_confidence: dict = Field(default_factory=dict)


class EconomicsApiEquivalent(BaseModel):
    value: float | None = None
    currency: str = "USD"
    pricing_version: str | None = None
    partial: bool = False
    groups: list[dict] = Field(default_factory=list)
    unpriced: dict = Field(default_factory=dict)


class EconomicsMetrics(BaseModel):
    value_multiplier: float | None = None
    savings_vs_api: float | None = None
    savings_pct: float | None = None
    effective_cost_per_1m_tokens: float | None = None
    tokens_per_dollar: float | None = None
    actual_cost_per_1m_tokens: float | None = None


class EconomicsProvider(BaseModel):
    config_id: int
    provider: str
    label: str
    pricing_model: str
    cost_basis: EconomicsMoney
    actual_spend: EconomicsMoney | None = None
    subscription_cost_basis: EconomicsMoney | None = None
    observed: EconomicsObserved
    api_equivalent: EconomicsApiEquivalent
    economics: EconomicsMetrics
    confidence: str = "insufficient"
    pricing_coverage: dict = Field(default_factory=dict)
    attribution_confidence: dict = Field(default_factory=dict)
    disambiguate: bool = False
    attribution_ambiguous: bool = False
    comparison_eligible: bool = False
    exclusion_reason: str | None = None
    explanation: list[str] = Field(default_factory=list)


class EconomicsProviderLevel(BaseModel):
    """Provider-level economics for shared Hermes workload that cannot be
    attributed to a single config. Reported once so aggregate economics never
    double-counts the same observations."""

    provider: str
    config_count: int
    attribution: str = "provider_level"
    observed: EconomicsObserved
    api_equivalent: EconomicsApiEquivalent
    note: str = ""


class EconomicsSummary(BaseModel):
    cost_basis: EconomicsMoney
    api_equivalent_value: EconomicsMoney
    savings_vs_api: EconomicsMoney
    value_multiplier: float | None = None
    eligible_provider_count: int = 0


class EconomicsResponse(BaseModel):
    period: dict
    summary: EconomicsSummary
    providers: list[EconomicsProvider]
    provider_level: list[EconomicsProviderLevel] = Field(default_factory=list)
