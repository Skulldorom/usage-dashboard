"""Analytics API endpoints (scope ``analytics:read``).

Reads the normalized ``UsageObservation`` layer and serves historical
timeseries, daily/hourly breakdowns, previous-period comparisons, forecasts,
and a cross-provider summary. Kept separate from the live ``/usage`` endpoint.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import asc, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics import aggregation
from app.analytics.aggregation import bucketize, fill_buckets, series_coverage
from app.analytics.attribution import ATTRIBUTION_METRICS, attribute, provider_metric_labels
from app.analytics.confidence import confidence_level
from app.analytics.forecast import forecast_for_metric, rates_from_deltas
from app.analytics.schemas import (
    AnalyticsBucket,
    AnalyticsComparison,
    AnalyticsDailyRow,
    AnalyticsHourlyRow,
    AnalyticsMetricInfo,
    AnalyticsOverview,
    AnalyticsProviderInfo,
    AnalyticsSummary,
    AnalyticsSummaryCard,
    AnalyticsTimeseries,
    CoverageInfo,
    HermesOverlay,
    OverviewActivityDimension,
    OverviewActivityProvider,
    OverviewComparisonSeries,
    OverviewCoverage,
    OverviewPressure,
    OverviewProvider,
    OverviewRisk,
    ProviderCapacity,
)
from app.analytics.types import Observation
from app.analytics.capabilities import activity_dimensions, activity_metric_labels, comparison_dimension, overview_metric
from app.analytics.pricing import estimate_cost, normalize_model
from app.analytics.quota_correlation import estimate_quota_impact
from app.analytics.reconciliation import (
    authoritative_source,
    degrade_confidence,
    reconcile,
)
from app.analytics.utilization import utilization_metric, utilization_observations
from app.core.auth import require_scope
from app.database import get_session
from app.models import DataSourceConfig, ProviderConfig, UsageObservation
from app.providers.registry import get_adapter_class
from app.schemas import (
    Attribution,
    AttributionMetric,
    HermesBreakdown,
    HermesBreakdownDaily,
    HermesDiagnostic,
    HermesGroupRow,
    HermesSourceSummary,
    HermesTotal,
    ProviderConfigRead,
)

router = APIRouter()

DEFAULT_RANGE_DAYS = 30
_WINDOW_DURATIONS = {
    "24h": timedelta(days=1),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
    "week": timedelta(days=7),
    "billing": timedelta(days=30),
}


def _capabilities_for(provider: str) -> dict:
    adapter_cls = get_adapter_class(provider)
    return adapter_cls.analytics or {}


def _config_read(config: ProviderConfig) -> ProviderConfigRead:
    return ProviderConfigRead.model_validate(config)


def _aware(value):
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _orm_to_observation(row: UsageObservation) -> Observation:
    return Observation(
        metric=row.metric,
        value=row.value,
        unit=row.unit,
        observed_at=_aware(row.observed_at),
        kind=row.kind,
        source=row.source,
        window_start=_aware(row.window_start),
        window_end=_aware(row.window_end),
        reset_at=_aware(row.reset_at),
        model=row.model,
        provider_mapping=row.provider_mapping,
        profile=row.profile,
        session_id=row.session_id,
        cost_type=row.cost_type,
    )


async def _load_observations(
    session: AsyncSession,
    config_id: int,
    *,
    metric: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
) -> list[Observation]:
    query = select(UsageObservation).where(UsageObservation.provider_config_id == config_id)
    if metric:
        query = query.where(UsageObservation.metric == metric)
    if start is not None:
        query = query.where(UsageObservation.observed_at >= start)
    if end is not None:
        query = query.where(UsageObservation.observed_at < end)
    query = query.order_by(asc(UsageObservation.observed_at), asc(UsageObservation.id))
    rows = (await session.execute(query)).scalars().all()
    return [_orm_to_observation(row) for row in rows]


async def _get_config(session: AsyncSession, config_id: int) -> ProviderConfig:
    config = await session.get(ProviderConfig, config_id)
    if not config:
        raise HTTPException(status_code=404, detail="Provider config not found")
    return config


def _resolve_metric(
    capabilities: dict,
    observations: list[Observation],
    metric: str | None,
) -> tuple[str | None, dict | None]:
    metrics = capabilities.get("metrics") or {}
    if metric:
        return metric, metrics.get(metric)
    if metrics:
        first = next(iter(metrics))
        return first, metrics[first]
    if observations:
        return observations[0].metric, None
    return None, None


def _spec_metric_type(spec: dict | None) -> str:
    return spec.get("type", "gauge") if spec else "gauge"


def _spec_unit(spec: dict | None, observations: list[Observation]) -> str | None:
    if spec and spec.get("unit"):
        return spec["unit"]
    for obs in observations:
        if obs.unit:
            return obs.unit
    return None


def _latest_reset_at(observations: list[Observation]) -> datetime | None:
    resets = [obs.reset_at for obs in observations if obs.reset_at is not None]
    return max(resets) if resets else None


def _window_start(spec: dict | None, reset_at: datetime | None, now: datetime) -> datetime | None:
    if spec is None:
        return None
    window = spec.get("window")
    if window is None:
        return None
    duration = _WINDOW_DURATIONS.get(window)
    if duration is None:
        return None
    return (reset_at - duration) if reset_at else (now - duration)


def _as_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


async def _observed_metrics(session: AsyncSession, config_id: int) -> set[str]:
    rows = (
        await session.execute(
            select(UsageObservation.metric)
            .where(UsageObservation.provider_config_id == config_id)
            .distinct()
        )
    ).scalars().all()
    return set(rows)


@router.get(
    "/providers/{config_id}",
    response_model=AnalyticsProviderInfo,
    dependencies=[Depends(require_scope("analytics:read"))],
)
async def provider_analytics(config_id: int, session: AsyncSession = Depends(get_session)):
    config = await _get_config(session, config_id)
    capabilities = _capabilities_for(config.provider)
    metrics_spec = capabilities.get("metrics") or {}
    observed = await _observed_metrics(session, config_id)

    metric_infos = [AnalyticsMetricInfo(label=label, **spec) for label, spec in metrics_spec.items()]
    for label in sorted(observed - set(metrics_spec)):
        metric_infos.append(AnalyticsMetricInfo(label=label, type="gauge"))

    preferred = next(iter(metrics_spec), None) or (sorted(observed)[0] if observed else None)
    return AnalyticsProviderInfo(
        config=_config_read(config),
        provider=config.provider,
        supported=bool(capabilities.get("supported")),
        native_history=bool(capabilities.get("native_history")),
        metrics=metric_infos,
        preferred_metric=preferred,
    )


@router.get(
    "/providers/{config_id}/capacity",
    response_model=ProviderCapacity,
    dependencies=[Depends(require_scope("analytics:read"))],
)
async def provider_capacity(
    config_id: int,
    interval: str = "day",
    timezone: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    """Capacity summary + history for a provider's quota/utilization metric.

    Returns current utilization (used/remaining/overage), reset/window, source,
    confidence, pace ratio vs sustainable burn, and a bucketed utilization
    history. Providers without a normalizable quota metric return a capacity
    object with null utilization and empty history (never fabricated 0%).
    """
    if interval not in aggregation.INTERVALS:
        raise HTTPException(status_code=400, detail=f"Unsupported interval: {interval}")
    config = await _get_config(session, config_id)
    capabilities = _capabilities_for(config.provider)
    observations = await _load_observations(session, config_id)
    now = datetime.now(UTC)

    util = utilization_metric(capabilities) if capabilities else None
    if util is None:
        return ProviderCapacity(
            config_id=config.id,
            provider=config.provider,
            label=config.label,
            confidence=confidence_level(observations)["level"],
        )

    util_metric_name, util_spec = util
    point_obs = [obs for obs in observations if obs.metric == util_metric_name]
    capacity_obs = (
        [obs for obs in observations if obs.metric == util_spec.get("capacity_metric")]
        if util_spec.get("capacity_metric")
        else None
    )
    util_obs = utilization_observations(
        point_obs, metric=util_metric_name, spec=util_spec, capacity_observations=capacity_obs,
    )

    used_pct = None
    remaining_pct = None
    overage_pct = None
    reset_at = None
    window_start = None
    window_end = None
    source = None
    latest = None
    if util_obs:
        latest = max(util_obs, key=lambda obs: obs.observed_at)
        used_pct = round(latest.value, 4)
        remaining_pct = round(max(0.0, 100.0 - used_pct), 4)
        overage_pct = round(max(0.0, used_pct - 100.0), 4)
        reset_at = latest.reset_at or _latest_reset_at(point_obs)
        source = latest.source
        window_start = latest.window_start
        window_end = latest.window_end

    # Pace ratio: actual burn vs sustainable burn for the remaining window.
    pace_ratio = None
    sustainable_rate = None
    burn_rate = None
    metric_obs = point_obs if point_obs else observations
    rates = rates_from_deltas(metric_obs, now=now)
    avg_7d = rates["avg_7d"] or rates["avg_30d"] or rates["current_24h"]
    if reset_at is not None and avg_7d and avg_7d > 0 and used_pct is not None:
        days_left = max((_as_aware(reset_at) - now).total_seconds() / 86_400.0, 0.0)
        if days_left > 0:
            sustainable_rate = round(remaining_pct / days_left, 4)
            if sustainable_rate and sustainable_rate > 0:
                pace_ratio = round(avg_7d / sustainable_rate, 3)
                burn_rate = round(avg_7d, 4)

    buckets = []
    if util_obs:
        buckets = fill_buckets(
            bucketize(util_obs, metric=util_metric_name, interval=interval, tz=timezone),
            interval=interval,
            tz=timezone,
        )

    # Quota-impact correlation: estimate how Hermes-observed activity tracks
    # quota movement across complete reset windows (never a fixed conversion).
    hermes_observations = await _load_mapped_hermes_observations(
        session, config.provider, start=now - timedelta(days=365), end=now,
    )
    quota_impact = estimate_quota_impact(util_obs, hermes_observations)

    return ProviderCapacity(
        config_id=config.id,
        provider=config.provider,
        label=config.label,
        metric=util_metric_name,
        capacity_used_pct=used_pct,
        capacity_remaining_pct=remaining_pct,
        overage_pct=overage_pct,
        reset_at=reset_at,
        window_start=window_start,
        window_end=window_end,
        source=source,
        confidence=confidence_level(observations)["level"],
        pace_ratio=pace_ratio,
        sustainable_rate=sustainable_rate,
        burn_rate=burn_rate,
        quota_impact=quota_impact,
        buckets=[AnalyticsBucket(**asdict(bucket)) for bucket in buckets],
    )


@router.get(
    "/providers/{config_id}/timeseries",
    response_model=AnalyticsTimeseries,
    dependencies=[Depends(require_scope("analytics:read"))],
)
async def timeseries(
    config_id: int,
    metric: str | None = None,
    interval: str = "day",
    from_: datetime | None = Query(default=None, alias="from"),
    to_: datetime | None = Query(default=None, alias="to"),
    timezone: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    if interval not in aggregation.INTERVALS:
        raise HTTPException(status_code=400, detail=f"Unsupported interval: {interval}")
    config = await _get_config(session, config_id)
    capabilities = _capabilities_for(config.provider)
    observations = await _load_observations(session, config_id)
    resolved, spec = _resolve_metric(capabilities, observations, metric)
    if resolved is None:
        raise HTTPException(status_code=404, detail="No analytics data for this provider")

    metric_type = _spec_metric_type(spec)
    unit = _spec_unit(spec, observations)
    now = datetime.now(UTC)
    end = _as_aware(to_) if to_ is not None else now
    start = _as_aware(from_) if from_ is not None else end - timedelta(days=DEFAULT_RANGE_DAYS)

    metric_obs = [obs for obs in observations if obs.metric == resolved]
    buckets = bucketize(metric_obs, metric=resolved, interval=interval, tz=timezone, start=start, end=end)
    buckets = fill_buckets(buckets, interval=interval, start=start, end=end, tz=timezone)
    cov = series_coverage(metric_obs)
    hermes_overlay = await _hermes_overlay(
        session, config.provider, metric_type, spec, interval=interval, tz=timezone, start=start, end=end,
    )

    return AnalyticsTimeseries(
        metric=resolved,
        metric_type=metric_type,
        unit=unit,
        interval=interval,
        timezone=timezone or "UTC",
        buckets=[AnalyticsBucket(**asdict(bucket)) for bucket in buckets],
        coverage=CoverageInfo(**cov),
        hermes_overlay=hermes_overlay,
    )


def _primary_value(bucket: aggregation.Bucket, metric_type: str) -> float | None:
    """Pick the primary plot value for a metric type."""
    if metric_type in ("counter", "rate_limit"):
        return bucket.total if bucket.delta_samples else None
    return bucket.value


@router.get(
    "/providers/{config_id}/daily",
    response_model=list[AnalyticsDailyRow],
    dependencies=[Depends(require_scope("analytics:read"))],
)
async def daily_breakdown(
    config_id: int,
    metric: str | None = None,
    from_: datetime | None = Query(default=None, alias="from"),
    to_: datetime | None = Query(default=None, alias="to"),
    timezone: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    config = await _get_config(session, config_id)
    capabilities = _capabilities_for(config.provider)
    observations = await _load_observations(session, config_id)
    resolved, spec = _resolve_metric(capabilities, observations, metric)
    if resolved is None:
        raise HTTPException(status_code=404, detail="No analytics data for this provider")

    metric_type = _spec_metric_type(spec)
    now = datetime.now(UTC)
    end = _as_aware(to_) if to_ is not None else now
    start = _as_aware(from_) if from_ is not None else end - timedelta(days=DEFAULT_RANGE_DAYS)

    metric_obs = [obs for obs in observations if obs.metric == resolved]
    daily = bucketize(metric_obs, metric=resolved, interval="day", tz=timezone, start=start, end=end)
    hourly = bucketize(metric_obs, metric=resolved, interval="hour", tz=timezone, start=start, end=end)

    # Peak hour per day from hourly delta consumption (or point value).
    peak_by_day: dict[datetime, tuple[int, float]] = {}
    for bucket in hourly:
        day_key = bucket.start.replace(hour=0, minute=0, second=0, microsecond=0)
        value = bucket.total if bucket.delta_samples else (bucket.value or 0)
        if day_key not in peak_by_day or value > peak_by_day[day_key][1]:
            peak_by_day[day_key] = (bucket.start.hour, value)

    rows: list[AnalyticsDailyRow] = []
    for index, bucket in enumerate(daily):
        primary = _primary_value(bucket, metric_type)
        previous = _primary_value(daily[index - 1], metric_type) if index > 0 else None
        change = None
        if primary is not None and previous is not None and previous != 0:
            change = round((primary - previous) / abs(previous) * 100, 1)
        peak = peak_by_day.get(bucket.start)
        rows.append(
            AnalyticsDailyRow(
                date=bucket.start.date().isoformat(),
                start=bucket.start,
                usage=bucket.total if bucket.delta_samples else None,
                value=bucket.value,
                peak_hour=peak[0] if peak else None,
                change_pct=change,
                samples=bucket.samples + bucket.delta_samples,
            )
        )
    return rows


@router.get(
    "/providers/{config_id}/hourly",
    response_model=list[AnalyticsHourlyRow],
    dependencies=[Depends(require_scope("analytics:read"))],
)
async def hourly_breakdown(
    config_id: int,
    metric: str | None = None,
    date: str | None = None,
    timezone: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    config = await _get_config(session, config_id)
    capabilities = _capabilities_for(config.provider)
    observations = await _load_observations(session, config_id)
    resolved, spec = _resolve_metric(capabilities, observations, metric)
    if resolved is None:
        raise HTTPException(status_code=404, detail="No analytics data for this provider")

    metric_type = _spec_metric_type(spec)
    metric_obs = [obs for obs in observations if obs.metric == resolved]
    zone = aggregation.resolve_tz(timezone)

    day_start = None
    day_end = None
    if date:
        try:
            day_start = datetime.fromisoformat(date).replace(tzinfo=zone)
        except ValueError:
            raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD")
        day_end = day_start + timedelta(days=1)
    else:
        if not metric_obs:
            day_start = datetime.now(UTC).astimezone(zone).replace(hour=0, minute=0, second=0, microsecond=0)
        else:
            latest = max(obs.observed_at for obs in metric_obs).astimezone(zone)
            day_start = latest.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)

    hourly = bucketize(metric_obs, metric=resolved, interval="hour", tz=timezone, start=day_start, end=day_end)
    hourly = fill_buckets(hourly, interval="hour", start=day_start, end=day_end, tz=timezone)
    return [
        AnalyticsHourlyRow(
            hour=bucket.start.astimezone(zone).hour,
            start=bucket.start,
            value=bucket.value,
            total=bucket.total if bucket.delta_samples else None,
            samples=bucket.samples + bucket.delta_samples,
        )
        for bucket in hourly
    ]


@router.get(
    "/providers/{config_id}/forecast",
    dependencies=[Depends(require_scope("analytics:read"))],
)
async def forecast(
    config_id: int,
    metric: str | None = None,
    timezone: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> dict:
    config = await _get_config(session, config_id)
    capabilities = _capabilities_for(config.provider)
    observations = await _load_observations(session, config_id)
    resolved, spec = _resolve_metric(capabilities, observations, metric)
    if resolved is None:
        raise HTTPException(status_code=404, detail="No analytics data for this provider")

    metric_type = _spec_metric_type(spec)
    unit = _spec_unit(spec, observations)
    metric_obs = [obs for obs in observations if obs.metric == resolved]

    reset_at = _latest_reset_at(metric_obs)
    now = datetime.now(UTC)
    window_start = _window_start(spec, reset_at, now)

    payload = forecast_for_metric(
        metric_obs,
        metric_type=metric_type,
        now=now,
        reset_at=reset_at,
        window_start=window_start,
        capacity=spec.get("maximum") if spec else None,
    )
    payload["metric"] = resolved
    payload["unit"] = unit
    payload["confidence"] = confidence_level(metric_obs)
    payload["coverage"] = series_coverage(metric_obs)
    payload["rates"] = rates_from_deltas(metric_obs, now=now)
    return payload


@router.get(
    "/providers/{config_id}/comparison",
    response_model=AnalyticsComparison,
    dependencies=[Depends(require_scope("analytics:read"))],
)
async def comparison(
    config_id: int,
    metric: str | None = None,
    window: str = "day",
    timezone: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    config = await _get_config(session, config_id)
    capabilities = _capabilities_for(config.provider)
    observations = await _load_observations(session, config_id)
    resolved, spec = _resolve_metric(capabilities, observations, metric)
    if resolved is None:
        raise HTTPException(status_code=404, detail="No analytics data for this provider")

    durations = {"day": timedelta(days=1), "week": timedelta(days=7), "month": timedelta(days=30)}
    if window not in durations:
        raise HTTPException(status_code=400, detail="window must be day, week, or month")
    duration = durations[window]

    metric_type = _spec_metric_type(spec)
    metric_obs = [obs for obs in observations if obs.metric == resolved]
    now = datetime.now(UTC)

    def window_total(start: datetime, end: datetime) -> float | None:
        if metric_type in ("counter", "rate_limit"):
            total = sum(obs.value for obs in metric_obs if obs.kind == "delta" and start <= obs.observed_at < end)
            return round(total, 6)
        points = [obs.value for obs in metric_obs if obs.kind == "point" and start <= obs.observed_at < end]
        return points[-1] if points else None

    current = window_total(now - duration, now)
    previous = window_total(now - 2 * duration, now - duration)
    change = None
    if current is not None and previous is not None and previous != 0:
        change = round((current - previous) / abs(previous) * 100, 1)

    return AnalyticsComparison(
        metric=resolved,
        current=current,
        previous=previous,
        change_pct=change,
        current_window={"start": (now - duration).isoformat(), "end": now.isoformat()},
        previous_window={"start": (now - 2 * duration).isoformat(), "end": (now - duration).isoformat()},
    )


@router.get(
    "/summary",
    response_model=AnalyticsSummary,
    dependencies=[Depends(require_scope("analytics:read"))],
)
async def summary(session: AsyncSession = Depends(get_session)):
    configs = (
        await session.execute(select(ProviderConfig).order_by(asc(ProviderConfig.display_order), asc(ProviderConfig.id)))
    ).scalars().all()

    now = datetime.now(UTC)
    cards: list[AnalyticsSummaryCard] = []
    for config in configs:
        capabilities = _capabilities_for(config.provider)
        observations = await _load_observations(session, config.id)
        resolved, spec = _resolve_metric(capabilities, observations, None)
        if resolved is None:
            continue
        metric_type = _spec_metric_type(spec)
        unit = _spec_unit(spec, observations)
        metric_obs = [obs for obs in observations if obs.metric == resolved]

        def deltas_since(since: datetime) -> float:
            return sum(obs.value for obs in metric_obs if obs.kind == "delta" and obs.observed_at >= since)

        usage_today = deltas_since(now - timedelta(days=1))
        usage_week = deltas_since(now - timedelta(days=7))
        prev_week = sum(
            obs.value
            for obs in metric_obs
            if obs.kind == "delta" and now - timedelta(days=14) <= obs.observed_at < now - timedelta(days=7)
        )
        rates = rates_from_deltas(metric_obs, now=now)
        trend = None
        if usage_week is not None and prev_week:
            trend = round((usage_week - prev_week) / prev_week * 100, 1)

        projected = None
        if metric_type in ("remaining", "rate_limit") and spec:
            reset_at = _latest_reset_at(metric_obs)
            window_start = _window_start(spec, reset_at, now)
            fc = forecast_for_metric(
                metric_obs, metric_type=metric_type, now=now, reset_at=reset_at,
                window_start=window_start, capacity=spec.get("maximum"),
            )
            projected = fc.get("projected_at_reset")

        cov = series_coverage(metric_obs)
        cards.append(
            AnalyticsSummaryCard(
                provider_config_id=config.id,
                provider=config.provider,
                label=config.label,
                metric=resolved,
                metric_type=metric_type,
                unit=unit,
                usage_today=round(usage_today, 4),
                usage_week=round(usage_week, 4),
                avg_per_day=round(usage_week / 7, 4),
                current_rate=rates["current_24h"],
                projected_at_reset=projected,
                trend_pct=trend,
                coverage=cov["coverage"],
                confidence=confidence_level(metric_obs, coverage=cov["coverage"])["level"],
            )
        )
    return AnalyticsSummary(providers=cards)


def _metric_delta_sum(observations: list[Observation], metric: str, start: datetime, end: datetime) -> float:
    return sum(
        obs.value for obs in observations
        if obs.kind == "delta" and obs.metric == metric and start <= obs.observed_at < end
    )


def _activity_series(
    observations: list[Observation],
    labels: list[str],
    *,
    interval: str,
    tz: str | None,
    start: datetime,
    end: datetime,
) -> list[AnalyticsBucket]:
    """Bucketize combined delta observations across multiple metric labels.

    Disjoint token classes (input/output/cache) are relabelled to a synthetic
    metric and summed by the shared ``bucketize``/``fill_buckets`` path so gaps
    remain explicit and missing data is not read as zero usage.
    """
    combined = [
        Observation(
            metric="_activity",
            value=obs.value,
            unit=obs.unit,
            observed_at=obs.observed_at,
            kind="delta",
            source=obs.source,
            window_start=obs.window_start,
            window_end=obs.window_end,
            reset_at=obs.reset_at,
        )
        for obs in observations
        if obs.kind == "delta" and obs.metric in labels
    ]
    buckets = bucketize(combined, metric="_activity", interval=interval, tz=tz, start=start, end=end)
    return fill_buckets(buckets, interval=interval, start=start, end=end, tz=tz)


def _delta_sums_by_metric(observations: list[Observation], start: datetime, end: datetime) -> dict[str, float]:
    totals: dict[str, float] = {}
    for obs in observations:
        if obs.kind != "delta" or not (start <= obs.observed_at < end):
            continue
        totals[obs.metric] = totals.get(obs.metric, 0.0) + obs.value
    return {metric: round(value, 4) for metric, value in sorted(totals.items()) if value}


def _provider_total_for_hermes_metric(observations: list[Observation], metric: str, start: datetime, end: datetime) -> float | None:
    labels = provider_metric_labels(metric)
    total = sum(_metric_delta_sum(observations, label, start, end) for label in labels)
    return round(total, 4) if total else None


def _attribution_rows(provider_observations: list[Observation], hermes_activity: dict[str, float], start: datetime, end: datetime) -> list[dict]:
    rows: list[dict] = []
    for metric, hermes_value in hermes_activity.items():
        if metric not in {name for name, _ in ATTRIBUTION_METRICS}:
            continue
        provider_total = _provider_total_for_hermes_metric(provider_observations, metric, start, end)
        result = attribute(provider_total, hermes_value)
        result["metric"] = metric
        result["unit"] = _ATTRIBUTION_UNITS.get(metric)
        rows.append(result)
    return rows


async def _load_mapped_hermes_observations(
    session: AsyncSession,
    provider: str,
    *,
    start: datetime,
    end: datetime,
) -> list[Observation]:
    rows = (
        await session.execute(
            select(UsageObservation).where(
                UsageObservation.source == "hermes",
                UsageObservation.observed_at >= start,
                UsageObservation.observed_at < end,
                (UsageObservation.provider_mapping == provider) | (UsageObservation.provider == provider),
            )
        )
    ).scalars().all()
    return [_orm_to_observation(row) for row in rows]


def _hermes_overlay_series(
    observations: list[Observation],
    metrics: list[str],
    *,
    interval: str,
    tz: str | None,
    start: datetime,
    end: datetime,
) -> list[aggregation.Bucket]:
    """Bucketize mapped Hermes delta observations into one aligned series.

    Multiple token classes are relabelled to a synthetic metric and summed by
    the shared ``bucketize``/``fill_buckets`` path so gaps stay explicit and
    missing data is never read as zero usage.
    """
    combined = [
        Observation(
            metric="_hermes_overlay",
            value=obs.value,
            unit=obs.unit,
            observed_at=obs.observed_at,
            kind="delta",
            source=obs.source,
            window_start=obs.window_start,
            window_end=obs.window_end,
            reset_at=obs.reset_at,
        )
        for obs in observations
        if obs.kind == "delta" and obs.metric in metrics
    ]
    buckets = bucketize(combined, metric="_hermes_overlay", interval=interval, tz=tz, start=start, end=end)
    return fill_buckets(buckets, interval=interval, start=start, end=end, tz=tz)


async def _hermes_overlay(
    session: AsyncSession,
    provider: str,
    metric_type: str,
    spec: dict | None,
    *,
    interval: str,
    tz: str | None,
    start: datetime,
    end: datetime,
) -> HermesOverlay:
    """Build the Hermes-observed series aligned to a provider's native metric.

    Returns ``compatible=False`` with a ``reason`` when the metric has no
    comparable Hermes counterpart or there is no mapped Hermes data in range,
    so the frontend never draws a misleading overlay.
    """
    dimension = comparison_dimension(spec)
    if dimension is None:
        if spec and spec.get("utilization"):
            reason = "native metric is a utilization percentage"
        elif metric_type not in ("counter", "rate_limit"):
            reason = "native metric is a point/state value, not consumption"
        else:
            reason = "no comparable Hermes metric for this unit"
        return HermesOverlay(compatible=False, reason=reason)

    hermes_metrics = _HERMES_METRICS_BY_DIMENSION[dimension]
    unit = _HERMES_OVERLAY_UNITS[dimension]
    hermes_observations = await _load_mapped_hermes_observations(session, provider, start=start, end=end)
    has_data = any(obs.kind == "delta" and obs.metric in hermes_metrics for obs in hermes_observations)
    if not has_data:
        return HermesOverlay(
            compatible=False,
            metric=dimension,
            hermes_metrics=hermes_metrics,
            unit=unit,
            reason="no mapped Hermes data for the selected range",
        )

    buckets = _hermes_overlay_series(
        hermes_observations, hermes_metrics, interval=interval, tz=tz, start=start, end=end,
    )
    return HermesOverlay(
        compatible=True,
        metric=dimension,
        hermes_metrics=hermes_metrics,
        unit=unit,
        buckets=[AnalyticsBucket(**asdict(bucket)) for bucket in buckets],
    )


def _period_trend(observations: list[Observation], metric: str | None, start: datetime, end: datetime) -> float | None:
    if metric is None:
        return None
    span = end - start
    current = _metric_delta_sum(observations, metric, start, end)
    previous = _metric_delta_sum(observations, metric, start - span, start)
    if previous:
        return round((current - previous) / previous * 100, 1)
    return None


def _latest_point(observations: list[Observation], metric: str, *, end: datetime | None = None) -> Observation | None:
    points = [obs for obs in observations if obs.metric == metric and obs.kind == "point" and (end is None or obs.observed_at <= end)]
    return max(points, key=lambda obs: obs.observed_at) if points else None


def _overview_value(observations: list[Observation], metric: str | None, spec: dict | None, start: datetime, end: datetime) -> float | None:
    if metric is None:
        return None
    metric_type = (spec or {}).get("type", "gauge")
    if metric_type in ("counter", "rate_limit"):
        value = _metric_delta_sum(observations, metric, start, end)
        has_delta = any(obs.kind == "delta" and obs.metric == metric and start <= obs.observed_at < end for obs in observations)
        return value if has_delta else None
    latest = _latest_point(observations, metric, end=end)
    return latest.value if latest is not None else None


def _utilization_trend(current: float | None, previous: float | None) -> float | None:
    if current is None or previous is None:
        return None
    return round(current - previous, 1)


def _observation_sources(observations: list[Observation]) -> list[str]:
    return sorted({obs.source for obs in observations if obs.source})


def _quality_state(*, has_observations: bool, has_utilization: bool, native_history: bool, supported: bool, coverage: float) -> tuple[str, str, str | None]:
    if not has_observations:
        return "unavailable", "unavailable", "No current analytics observations"
    if coverage and coverage < 0.5:
        return "stale", "stale", "Analytics data coverage is low"
    if has_utilization and native_history:
        return "full", "measurable", None
    if has_utilization:
        return "partial", "measurable", None
    if supported:
        return "limited", "native-only", "No normalizable quota/capacity metric"
    return "limited", "native-only", "Provider does not expose advanced analytics"


def _risk_state(utilization_pct: float) -> str:
    if utilization_pct >= 95:
        return "exhausted"
    if utilization_pct >= 85:
        return "critical"
    if utilization_pct >= 70:
        return "warning"
    return "normal"


@router.get(
    "/overview",
    response_model=AnalyticsOverview,
    dependencies=[Depends(require_scope("analytics:read"))],
)
async def overview(
    from_: datetime | None = Query(default=None, alias="from"),
    to_: datetime | None = Query(default=None, alias="to"),
    interval: str = "day",
    timezone: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    if interval not in aggregation.INTERVALS:
        raise HTTPException(status_code=400, detail=f"Unsupported interval: {interval}")

    configs = (
        await session.execute(select(ProviderConfig).order_by(asc(ProviderConfig.display_order), asc(ProviderConfig.id)))
    ).scalars().all()

    now = datetime.now(UTC)
    end = _as_aware(to_) if to_ is not None else now
    start = _as_aware(from_) if from_ is not None else end - timedelta(days=DEFAULT_RANGE_DAYS)

    totals: dict[str, float] = {}
    providers: list[OverviewProvider] = []
    comparison: list[OverviewComparisonSeries] = []
    risks: list[OverviewRisk] = []
    current_utilizations: list[float] = []
    previous_utilizations: list[float] = []
    providers_with_history = 0
    providers_with_forecasts = 0
    stale_or_unavailable = 0
    span = end - start
    activity_rows: list[tuple[ProviderConfig, list[Observation], dict[str, list[str]]]] = []

    for config in configs:
        capabilities = _capabilities_for(config.provider)
        observations = await _load_observations(session, config.id)
        activity_labels = activity_metric_labels(activity_dimensions(capabilities))
        if activity_labels:
            activity_rows.append((config, observations, activity_labels))
        hermes_observations = await _load_mapped_hermes_observations(session, config.provider, start=start, end=end)
        hermes_activity = _delta_sums_by_metric(hermes_observations, start, end)
        attribution_rows = _attribution_rows(observations, hermes_activity, start, end)
        provider_cost_estimate = estimate_cost(hermes_observations)
        estimated_cost = round(provider_cost_estimate["total_cost"], 4) if provider_cost_estimate["total_cost"] else None
        estimated_cost_source = (
            f"pricing {provider_cost_estimate['pricing_version']}"
            if estimated_cost is not None
            else None
        )
        cov = series_coverage(observations)
        conf = confidence_level(observations + hermes_observations, coverage=cov["coverage"])["level"]
        if bool(capabilities.get("native_history")):
            providers_with_history += 1

        # Headline is the single explicitly declared overview metric - never a
        # sum of same-unit metrics, so overlapping windows (e.g. daily/weekly/
        # monthly counters) can't inflate the value or its share.
        headline = overview_metric(capabilities) if capabilities else None
        headline_metric_name: str | None = None
        headline_spec: dict | None = None
        headline_unit: str | None = None
        headline_value: float | None = None
        if headline:
            headline_metric_name, headline_spec = headline
            headline_unit = headline_spec.get("unit")
            headline_value = _overview_value(observations, headline_metric_name, headline_spec, start, end)
            if headline_unit and headline_unit != "%" and headline_value is not None:
                totals[headline_unit] = totals.get(headline_unit, 0.0) + headline_value

        util_metric_name: str | None = None
        util_pct: float | None = None
        previous_util_pct: float | None = None
        remaining_pct: float | None = None
        reset_at: datetime | None = None
        util_buckets = None
        latest_util_source: str | None = None
        forecast_pct: float | None = None
        util = utilization_metric(capabilities) if capabilities else None
        quota_impact = None
        if util:
            util_metric_name, util_spec = util
            point_obs = [obs for obs in observations if obs.metric == util_metric_name]
            capacity_obs = (
                [obs for obs in observations if obs.metric == util_spec.get("capacity_metric")]
                if util_spec.get("capacity_metric")
                else None
            )
            util_obs = utilization_observations(
                point_obs, metric=util_metric_name, spec=util_spec, capacity_observations=capacity_obs,
            )
            if util_obs:
                providers_with_forecasts += 1
                latest = max(util_obs, key=lambda obs: obs.observed_at)
                util_pct = latest.value
                latest_util_source = latest.source
                remaining_pct = round(max(0.0, 100.0 - util_pct), 4)
                overage_pct = round(max(0.0, util_pct - 100.0), 4)
                reset_at = latest.reset_at or _latest_reset_at(point_obs)
                current_utilizations.append(util_pct)
                previous_points = [obs for obs in util_obs if start - span <= obs.observed_at < start]
                if previous_points:
                    previous_util_pct = max(previous_points, key=lambda obs: obs.observed_at).value
                    previous_utilizations.append(previous_util_pct)
                util_buckets = fill_buckets(
                    bucketize(util_obs, metric=util_metric_name, interval=interval, tz=timezone, start=start, end=end),
                    interval=interval, start=start, end=end, tz=timezone,
                )
                # Quota-impact correlation over long history (not the 30d range).
                impact_hermes = await _load_mapped_hermes_observations(
                    session, config.provider, start=now - timedelta(days=365), end=now,
                )
                quota_impact = estimate_quota_impact(util_obs, impact_hermes)

        if util_pct is None:
            overage_pct = None

        headline_obs = [obs for obs in observations if headline_metric_name and obs.metric == headline_metric_name]
        util_source_obs = [obs for obs in observations if util_metric_name and obs.metric == util_metric_name]
        source_pool = util_source_obs + headline_obs + hermes_observations
        sources = _observation_sources(source_pool or observations)
        authoritative = latest_util_source or authoritative_source(_observation_sources(headline_obs)) or authoritative_source(_observation_sources(observations))
        corroborating_sources = [source for source in sources if source != authoritative]

        quality, data_state, exclusion_reason = _quality_state(
            has_observations=bool(observations),
            has_utilization=util_pct is not None,
            native_history=bool(capabilities.get("native_history")),
            supported=bool(capabilities.get("supported")),
            coverage=cov["coverage"],
        )
        if quality in {"stale", "unavailable"}:
            stale_or_unavailable += 1

        # --- Source reconciliation (issue #165 §4) -------------------------
        # Capacity: authoritative utilization has no direct %-corroboration, but
        # Hermes activity fresher than the authoritative reading flags staleness.
        capacity_recon = reconcile(
            authoritative_source_name=authoritative if util_pct is not None else None,
            authoritative_value=util_pct,
            authoritative_at=latest.observed_at if util_pct is not None else None,
            corroborating_sources=corroborating_sources,
            corroborating_times=[obs.observed_at for obs in hermes_observations],
            is_percent=True,
        )
        # Activity: provider-native headline vs Hermes-observed same-metric total
        # (relative disagreement). Hermes is corroborating, never summed.
        activity_authoritative = authoritative_source(_observation_sources(headline_obs))
        activity_latest = _latest_point(headline_obs, headline_metric_name) if headline_metric_name else None
        hermes_headline_value = hermes_activity.get(headline_metric_name) if headline_metric_name else None
        activity_recon = reconcile(
            authoritative_source_name=activity_authoritative,
            authoritative_value=headline_value,
            authoritative_at=activity_latest.observed_at if activity_latest is not None else None,
            corroborating=[{"source": "hermes", "value": hermes_headline_value}],
            corroborating_sources=corroborating_sources,
            corroborating_times=[obs.observed_at for obs in hermes_observations],
            is_percent=headline_unit == "%",
        )
        confidence_impact = capacity_recon["confidence_impact"] + activity_recon["confidence_impact"]
        conf = degrade_confidence(conf, confidence_impact)

        provider = OverviewProvider(
            config_id=config.id,
            provider=config.provider,
            label=config.label,
            metric=headline_metric_name,
            unit=headline_unit,
            value=round(headline_value, 4) if headline_value is not None else None,
            utilization_metric=util_metric_name,
            utilization_pct=round(util_pct, 4) if util_pct is not None else None,
            remaining_pct=remaining_pct,
            overage_pct=overage_pct,
            reset_at=reset_at,
            trend_pct=_period_trend(observations, headline_metric_name, start, end),
            utilization_trend_pct=_utilization_trend(util_pct, previous_util_pct),
            forecast_pct=forecast_pct,
            quality=quality,
            data_state=data_state,
            exclusion_reason=exclusion_reason if util_pct is None else None,
            coverage=cov["coverage"],
            confidence=conf,
            authoritative_source=authoritative,
            corroborating_sources=corroborating_sources,
            sources=sources,
            hermes_activity=hermes_activity,
            attribution=attribution_rows,
            audit={
                "capacity": {
                    "metric": util_metric_name,
                    "value": round(util_pct, 4) if util_pct is not None else None,
                    "unit": "%" if util_pct is not None else None,
                    "authoritative_source": authoritative if util_pct is not None else None,
                    "window_start": latest.window_start.isoformat() if util_pct is not None and latest.window_start else None,
                    "window_end": latest.window_end.isoformat() if util_pct is not None and latest.window_end else None,
                    "reset_at": reset_at.isoformat() if reset_at else None,
                    "confidence": conf,
                    "reconciliation": capacity_recon,
                },
                "activity": {
                    "metric": headline_metric_name,
                    "value": round(headline_value, 4) if headline_value is not None else None,
                    "unit": headline_unit,
                    "authoritative_source": activity_authoritative,
                    "hermes_activity": hermes_activity,
                    "attribution": attribution_rows,
                    "estimated_cost": estimated_cost,
                    "estimated_cost_source": estimated_cost_source,
                    "reconciliation": activity_recon,
                    "note": "Hermes activity is corroborating telemetry and is not added to provider-authoritative totals.",
                },
                "corroborating_sources": corroborating_sources,
                "quota_impact": quota_impact,
            },
            estimated_cost=estimated_cost,
            estimated_cost_source=estimated_cost_source,
        )
        providers.append(provider)

        if util_pct is not None:
            state = _risk_state(util_pct)
            if state != "normal":
                reason = f"{round(util_pct, 1)}% used"
                if util_pct > 100:
                    reason += f" · {round(util_pct - 100, 1)}% over allowance"
                if reset_at is not None:
                    reason += f" · resets {reset_at.isoformat()}"
                risks.append(
                    OverviewRisk(
                        config_id=config.id,
                        provider=config.provider,
                        label=config.label,
                        utilization_pct=round(util_pct, 4),
                        remaining_pct=remaining_pct,
                        overage_pct=overage_pct,
                        reset_at=reset_at,
                        forecast_pct=forecast_pct,
                        confidence=conf,
                        state=state,
                        reason=reason,
                    )
                )

        if util_buckets is not None and util_metric_name is not None:
            comparison.append(
                OverviewComparisonSeries(
                    config_id=config.id,
                    provider=config.provider,
                    label=config.label,
                    metric=util_metric_name,
                    source=latest_util_source,
                    confidence=conf,
                    buckets=[AnalyticsBucket(**asdict(bucket)) for bucket in util_buckets],
                )
            )

    # Share % is scoped to like-unit groups so "95% of tokens" is honest.
    for provider in providers:
        if provider.unit and provider.unit != "%" and provider.value is not None:
            total = totals.get(provider.unit, 0.0)
            if total > 0:
                provider.share_pct = round(provider.value / total * 100, 2)

    highest = max((provider for provider in providers if provider.utilization_pct is not None), key=lambda row: row.utilization_pct, default=None)
    provider_pressure_pct = round(sum(current_utilizations) / len(current_utilizations), 4) if current_utilizations else None
    previous_pressure_pct = round(sum(previous_utilizations) / len(previous_utilizations), 4) if previous_utilizations else None
    pressure_trend_pct = _utilization_trend(provider_pressure_pct, previous_pressure_pct)
    coverage = OverviewCoverage(
        measurable_provider_count=len(current_utilizations),
        total_provider_count=len(configs),
        providers_with_history=providers_with_history,
        providers_with_forecasts=providers_with_forecasts,
        stale_or_unavailable_provider_count=stale_or_unavailable,
    )
    pressure = OverviewPressure(
        provider_pressure_pct=provider_pressure_pct,
        measurable_provider_count=len(current_utilizations),
        total_provider_count=len(configs),
        trend_pct=pressure_trend_pct,
        coverage=coverage,
    )

    # --- Activity dimensions (§7/§8) ---------------------------------------
    # Group providers into compatible activity dimensions (tokens/requests/cost/
    # credits), sum disjoint deltas per provider, compute share within each
    # dimension, and build a combined multi-provider series.
    _DIMENSION_UNITS = {"tokens": "tokens", "requests": "requests", "cost": "USD", "credits": "credits"}
    activity: list[OverviewActivityDimension] = []
    for dimension in ("tokens", "requests", "cost", "credits"):
        dimension_unit = _DIMENSION_UNITS[dimension]
        entries: list[OverviewActivityProvider] = []
        for config, observations, labels in activity_rows:
            labels_in_dimension = labels.get(dimension)
            if not labels_in_dimension:
                continue
            value = sum(
                _metric_delta_sum(observations, label, start, end)
                for label in labels_in_dimension
            )
            value = round(value, 4)
            if not value:
                continue
            sources = _observation_sources(
                [obs for obs in observations if obs.metric in labels_in_dimension]
            )
            metric_obs = [obs for obs in observations if obs.metric in labels_in_dimension]
            entries.append(
                OverviewActivityProvider(
                    config_id=config.id,
                    provider=config.provider,
                    label=config.label,
                    metric=",".join(labels_in_dimension),
                    unit=dimension_unit,
                    value=value,
                    source=authoritative_source(sources) if sources else None,
                    confidence=confidence_level(metric_obs)["level"],
                    buckets=[AnalyticsBucket(**asdict(bucket)) for bucket in _activity_series(
                        observations, labels_in_dimension, interval=interval, tz=timezone, start=start, end=end,
                    )],
                )
            )
        if not entries:
            continue
        dimension_total = sum(entry.value for entry in entries if entry.value is not None)
        for entry in entries:
            if entry.value is not None and dimension_total > 0:
                entry.share_pct = round(entry.value / dimension_total * 100, 2)
        entries.sort(key=lambda entry: (entry.value or 0), reverse=True)
        activity.append(
            OverviewActivityDimension(
                dimension=dimension,
                unit=dimension_unit,
                total=round(dimension_total, 4),
                providers=entries,
            )
        )

    return AnalyticsOverview(
        period={"start": start.isoformat(), "end": end.isoformat()},
        totals={unit: round(value, 4) for unit, value in totals.items()},
        provider_pressure_pct=provider_pressure_pct,
        measurable_provider_count=len(current_utilizations),
        total_provider_count=len(configs),
        pressure=pressure,
        highest_utilization=highest,
        coverage=coverage,
        risks=sorted(risks, key=lambda risk: risk.utilization_pct, reverse=True),
        providers=providers,
        comparison=comparison,
        activity=activity,
    )


# ---------------------------------------------------------------------------
# Hermes telemetry attribution & breakdown.
# ---------------------------------------------------------------------------

_ATTRIBUTION_UNITS = {
    "cost": "USD",
    "input_tokens": "tokens",
    "output_tokens": "tokens",
    "requests": "count",
}
_TOKEN_METRICS = frozenset(
    {"input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens", "reasoning_tokens"}
)

# Hermes observation metrics that back each native comparison dimension, and
# the unit the summed series is reported in.
_HERMES_METRICS_BY_DIMENSION = {
    "tokens": sorted(_TOKEN_METRICS),
    "requests": ["requests"],
    "cost": ["cost"],
}
_HERMES_OVERLAY_UNITS = {
    "tokens": "tokens",
    "requests": "count",
    "cost": "USD",
}


async def _load_hermes_rows(session: AsyncSession, start: datetime, end: datetime) -> list[UsageObservation]:
    return (
        await session.execute(
            select(UsageObservation).where(
                UsageObservation.source == "hermes",
                UsageObservation.observed_at >= start,
                UsageObservation.observed_at < end,
            )
        )
    ).scalars().all()


def _round_or_none(value: float) -> float | None:
    return round(value, 4) if value else None


def _source_status(source: DataSourceConfig) -> str:
    if source.last_attempt_at is None:
        return "never_connected"
    if source.consecutive_failures == 0 and source.last_success_at is not None:
        return "healthy"
    return "error"


async def _hermes_source_summaries(
    session: AsyncSession,
    *,
    start: datetime,
    end: datetime,
) -> list[HermesSourceSummary]:
    sources = (
        await session.execute(
            select(DataSourceConfig)
            .where(DataSourceConfig.kind == "hermes")
            .order_by(asc(DataSourceConfig.id))
        )
    ).scalars().all()
    configured_providers = set(
        (
            await session.execute(select(ProviderConfig.provider).where(ProviderConfig.is_enabled.is_(True)))
        ).scalars().all()
    )
    summaries: list[HermesSourceSummary] = []
    for source in sources:
        base_query = select(UsageObservation).where(
            UsageObservation.source == "hermes",
            UsageObservation.data_source_id == source.id,
        )
        total_observations = await session.scalar(
            select(func.count(UsageObservation.id)).where(
                UsageObservation.source == "hermes",
                UsageObservation.data_source_id == source.id,
            )
        ) or 0
        observations_in_range = await session.scalar(
            select(func.count(UsageObservation.id)).where(
                UsageObservation.source == "hermes",
                UsageObservation.data_source_id == source.id,
                UsageObservation.observed_at >= start,
                UsageObservation.observed_at < end,
            )
        ) or 0
        latest_observation_at = await session.scalar(
            select(UsageObservation.observed_at)
            .where(UsageObservation.source == "hermes", UsageObservation.data_source_id == source.id)
            .order_by(desc(UsageObservation.observed_at), desc(UsageObservation.id))
            .limit(1)
        )
        provider_rows = (await session.execute(base_query.with_only_columns(UsageObservation.provider).distinct())).scalars().all()
        observed = sorted({str(provider or "unknown") for provider in provider_rows})
        mappings = dict((source.extra or {}).get("provider_mappings") or {})
        unmapped = sorted(
            provider
            for provider in observed
            if configured_providers and str(mappings.get(provider, provider)).strip().lower() not in configured_providers
        )
        summaries.append(
            HermesSourceSummary(
                id=source.id,
                name=source.name,
                status=_source_status(source),
                is_enabled=source.is_enabled,
                base_url=source.base_url,
                last_success_at=source.last_success_at,
                last_attempt_at=source.last_attempt_at,
                latest_error=source.latest_error,
                latest_observation_at=_aware(latest_observation_at) if latest_observation_at else None,
                observations_in_range=observations_in_range,
                total_observations=total_observations,
                profiles=list((source.extra or {}).get("profiles") or []),
                provider_mappings=mappings,
                providers_observed=observed,
                providers_unmapped=unmapped,
                mute_unmapped_provider_alerts=bool((source.extra or {}).get("mute_unmapped_provider_alerts", False)),
            )
        )
    return summaries


def _hermes_diagnostics(*, sources: list[HermesSourceSummary], rows: list[UsageObservation], start: datetime, end: datetime) -> list[HermesDiagnostic]:
    diagnostics: list[HermesDiagnostic] = []
    if not sources:
        return [HermesDiagnostic(severity="info", message="No Hermes data source is configured. Connect Hermes Agent in Settings → Data sources.")]
    enabled = [source for source in sources if source.is_enabled]
    if not enabled:
        diagnostics.append(HermesDiagnostic(severity="warning", message="All Hermes data sources are disabled."))
    for source in sources:
        if source.status == "error":
            detail = f": {source.latest_error}" if source.latest_error else ""
            diagnostics.append(HermesDiagnostic(severity="error", message=f"{source.name} sync is failing{detail}."))
        elif source.status == "never_connected":
            diagnostics.append(HermesDiagnostic(severity="info", message=f"{source.name} has not synced successfully yet."))
        if source.profiles:
            diagnostics.append(HermesDiagnostic(severity="info", message=f"{source.name} is filtered to profiles: {', '.join(source.profiles)}."))
        if source.providers_unmapped and not source.mute_unmapped_provider_alerts:
            diagnostics.append(HermesDiagnostic(severity="warning", message=f"{source.name} observed unmapped providers: {', '.join(source.providers_unmapped)}."))
        if source.total_observations and source.observations_in_range == 0 and source.latest_observation_at:
            diagnostics.append(HermesDiagnostic(severity="info", message=f"{source.name} has stored Hermes observations, but the latest ({source.latest_observation_at.isoformat()}) is outside the selected range."))
    if not rows and any(source.last_success_at for source in sources):
        diagnostics.append(HermesDiagnostic(severity="info", message=f"No Hermes observations between {start.date().isoformat()} and {end.date().isoformat()}. Try a wider range, inspect recent observations, or sync now."))
    return diagnostics


@router.get(
    "/providers/{config_id}/attribution",
    response_model=Attribution,
    dependencies=[Depends(require_scope("analytics:read"))],
)
async def provider_attribution(
    config_id: int,
    from_: datetime | None = Query(default=None, alias="from"),
    to_: datetime | None = Query(default=None, alias="to"),
    session: AsyncSession = Depends(get_session),
):
    config = await _get_config(session, config_id)
    now = datetime.now(UTC)
    end = _as_aware(to_) if to_ is not None else now
    start = _as_aware(from_) if from_ is not None else end - timedelta(days=DEFAULT_RANGE_DAYS)

    provider_obs = await _load_observations(session, config_id, start=start, end=end)
    hermes_rows = (
        await session.execute(
            select(UsageObservation).where(
                UsageObservation.source == "hermes",
                UsageObservation.provider_mapping == config.provider,
                UsageObservation.observed_at >= start,
                UsageObservation.observed_at < end,
            )
        )
    ).scalars().all()

    metrics: list[AttributionMetric] = []
    for hermes_metric, aliases in ATTRIBUTION_METRICS:
        hermes_observed = sum(r.value for r in hermes_rows if r.metric == hermes_metric) or None
        provider_total = (
            sum(o.value for o in provider_obs if o.kind == "delta" and o.metric in aliases) or None
        )
        if hermes_observed is None and provider_total is None:
            continue
        att = attribute(provider_total, hermes_observed)
        metrics.append(
            AttributionMetric(
                metric=hermes_metric,
                unit=_ATTRIBUTION_UNITS.get(hermes_metric),
                provider_total=att["provider_total"],
                hermes_observed=att["hermes_observed"],
                attributed=att["attributed"],
                unattributed=att["unattributed"],
                overage=att["overage"],
                attribution_pct=att["attribution_pct"],
                status=att["status"],
            )
        )

    return Attribution(
        provider_config_id=config.id,
        provider=config.provider,
        label=config.label,
        period={"start": start.isoformat(), "end": end.isoformat()},
        metrics=metrics,
    )


@router.get(
    "/hermes",
    response_model=HermesBreakdown,
    dependencies=[Depends(require_scope("analytics:read"))],
)
async def hermes_breakdown(
    from_: datetime | None = Query(default=None, alias="from"),
    to_: datetime | None = Query(default=None, alias="to"),
    session: AsyncSession = Depends(get_session),
):
    now = datetime.now(UTC)
    end = _as_aware(to_) if to_ is not None else now
    start = _as_aware(from_) if from_ is not None else end - timedelta(days=DEFAULT_RANGE_DAYS)

    rows = await _load_hermes_rows(session, start, end)
    sources = await _hermes_source_summaries(session, start=start, end=end)

    totals: list[HermesTotal] = []
    for metric in ("cost", "input_tokens", "output_tokens", "requests"):
        value = sum(r.value for r in rows if r.metric == metric) or None
        totals.append(HermesTotal(metric=metric, unit=_ATTRIBUTION_UNITS.get(metric), value=_round_or_none(value) if value else None))
    tokens = sum(r.value for r in rows if r.metric in _TOKEN_METRICS) or None
    totals.append(HermesTotal(metric="tokens", unit="tokens", value=_round_or_none(tokens) if tokens else None))

    sessions = len({r.session_id for r in rows if r.session_id})

    cost_estimate = estimate_cost(rows)
    est_by_provider: dict[str, float] = {}
    est_by_model: dict[str, float] = {}
    for group in cost_estimate["groups"]:
        provider_key = group["provider"]
        est_by_provider[provider_key] = est_by_provider.get(provider_key, 0.0) + group["cost"]
        model_key = normalize_model(group["model"])
        if model_key:
            est_by_model[model_key] = est_by_model.get(model_key, 0.0) + group["cost"]

    def _grouped(attribute: str) -> list[HermesGroupRow]:
        groups: dict[str, dict[str, float]] = {}
        for row in rows:
            key = getattr(row, attribute) or "unknown"
            bucket = groups.setdefault(key, {"cost": 0.0, "tokens": 0.0, "requests": 0.0})
            if row.metric == "cost":
                bucket["cost"] += row.value
            elif row.metric in _TOKEN_METRICS:
                bucket["tokens"] += row.value
            elif row.metric == "requests":
                bucket["requests"] += row.value
        rows_out: list[HermesGroupRow] = []
        for key, bucket in sorted(groups.items()):
            estimated = None
            if attribute == "provider_mapping":
                estimated = est_by_provider.get(str(key).strip().lower())
            elif attribute == "model":
                estimated = est_by_model.get(normalize_model(str(key)))
            rows_out.append(
                HermesGroupRow(
                    key=key,
                    cost=_round_or_none(bucket["cost"]),
                    tokens=_round_or_none(bucket["tokens"]),
                    requests=_round_or_none(bucket["requests"]),
                    estimated_cost=_round_or_none(estimated),
                )
            )
        return rows_out

    daily_groups: dict[str, dict[str, float]] = {}
    for row in rows:
        day = _aware(row.observed_at).date().isoformat()
        bucket = daily_groups.setdefault(day, {"cost": 0.0, "tokens": 0.0, "requests": 0.0})
        if row.metric == "cost":
            bucket["cost"] += row.value
        elif row.metric in _TOKEN_METRICS:
            bucket["tokens"] += row.value
        elif row.metric == "requests":
            bucket["requests"] += row.value
    daily = [
        HermesBreakdownDaily(
            date=day,
            cost=_round_or_none(bucket["cost"]),
            tokens=_round_or_none(bucket["tokens"]),
            requests=_round_or_none(bucket["requests"]),
        )
        for day, bucket in sorted(daily_groups.items())
    ]

    return HermesBreakdown(
        period={"start": start.isoformat(), "end": end.isoformat()},
        totals=totals,
        sessions=sessions,
        by_provider=_grouped("provider_mapping"),
        by_model=_grouped("model"),
        by_profile=_grouped("profile"),
        daily=daily,
        sources=sources,
        diagnostics=_hermes_diagnostics(sources=sources, rows=rows, start=start, end=end),
        cost_estimate=cost_estimate,
    )
