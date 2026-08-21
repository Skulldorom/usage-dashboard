"""Pydantic response models for the analytics API."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

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


class AnalyticsTimeseries(BaseModel):
    metric: str
    metric_type: str
    unit: str | None = None
    interval: str
    timezone: str
    buckets: list[AnalyticsBucket]
    coverage: CoverageInfo


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
    unit: str | None = None
    value: float | None = None
    share_pct: float | None = None
    utilization_pct: float | None = None
    trend_pct: float | None = None
    coverage: float = 0.0
    confidence: str = "low"


class OverviewComparisonSeries(BaseModel):
    config_id: int
    provider: str
    label: str
    metric: str
    buckets: list[AnalyticsBucket]


class AnalyticsOverview(BaseModel):
    period: dict
    totals: dict[str, float]
    providers: list[OverviewProvider]
    comparison: list[OverviewComparisonSeries]
