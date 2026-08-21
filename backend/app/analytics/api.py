"""Analytics API endpoints (scope ``analytics:read``).

Reads the normalized ``UsageObservation`` layer and serves historical
timeseries, daily/hourly breakdowns, previous-period comparisons, forecasts,
and a cross-provider summary. Kept separate from the live ``/usage`` endpoint.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import asc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics import aggregation
from app.analytics.aggregation import bucketize, fill_buckets, series_coverage
from app.analytics.confidence import confidence_level
from app.analytics.forecast import forecast_for_metric, rates_from_deltas
from app.analytics.schemas import (
    AnalyticsBucket,
    AnalyticsComparison,
    AnalyticsDailyRow,
    AnalyticsHourlyRow,
    AnalyticsMetricInfo,
    AnalyticsProviderInfo,
    AnalyticsSummary,
    AnalyticsSummaryCard,
    AnalyticsTimeseries,
    CoverageInfo,
)
from app.analytics.types import Observation
from app.core.auth import require_scope
from app.database import get_session
from app.models import ProviderConfig, UsageObservation
from app.providers.registry import get_adapter_class
from app.schemas import ProviderConfigRead

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

    return AnalyticsTimeseries(
        metric=resolved,
        metric_type=metric_type,
        unit=unit,
        interval=interval,
        timezone=timezone or "UTC",
        buckets=[AnalyticsBucket(**asdict(bucket)) for bucket in buckets],
        coverage=CoverageInfo(**cov),
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
