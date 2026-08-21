# Usage analytics

The **Usage** page turns the provider snapshots collected by Usage Dashboard
into historical analytics: trends, daily/hourly breakdowns, peak-usage windows,
previous-period comparisons, and pace-based forecasts.

Analytics are built as a normalization layer on top of the existing
`UsageSnapshot` history — not a separate tracking system. Nothing about the
Dashboard's current-usage view changes.

## How it works

Each poll stores a snapshot of provider state. A normalizer then derives a
normalized observation per metric, including:

- **point readings** for gauges, balances, and remaining-quota values, and
- **interval deltas** for counters (usage consumed between observations).

Where a provider already returns historical buckets (Anthropic hourly usage,
OpenAI daily costs, Firecrawl historical periods), that native history is
ingested directly rather than derived from polling cadence.

Quota resets are detected from known reset timestamps first and a heuristic
second, so a quota rollover (e.g. `5% → 98% remaining`) is never reported as
negative usage.

## What you can see

- **Summary cards** — usage this week, average per day, trend vs. last week.
- **Historical chart** — the selected metric over time (hourly / daily / weekly).
- **Daily breakdown** — per-day usage, peak hour, day-over-day change, and status.
- **Time-of-day heatmap** — when usage concentrates across the day and week.
- **Previous-period comparison** — current period vs. the equivalent prior period.
- **Forecast** — rate-based projections, estimated exhaustion, and a sustainable
  daily pace, with a `high` / `medium` / `low` confidence indicator.

Forecasts are deterministic and rate-based; they are scoped to the relevant
reset window and never extrapolate a rolling total (like OpenAI's 30-day cost)
as if it were a simple counter. Confidence reflects observation count, history
span, data coverage, and whether data is provider-native or snapshot-derived.
Missing samples are reported as gaps, not zero usage.

The chart defaults to a **30-day** window regardless of how much history is
retained.

## Analytics API

The `GET /api/v1/usage` endpoint remains focused on current/latest state.
Historical analytics live under `GET /api/v1/analytics/*` and require the
`analytics:read` scope (admin sessions are always allowed):

```
GET /api/v1/analytics/summary
GET /api/v1/analytics/providers/{config_id}
GET /api/v1/analytics/providers/{config_id}/timeseries?metric=&interval=&from=&to=&timezone=
GET /api/v1/analytics/providers/{config_id}/daily?metric=&from=&to=&timezone=
GET /api/v1/analytics/providers/{config_id}/hourly?metric=&date=&timezone=
GET /api/v1/analytics/providers/{config_id}/forecast?metric=&timezone=
GET /api/v1/analytics/providers/{config_id}/comparison?metric=&window=day|week|month&timezone=
```

`interval` is one of `hour`, `day`, or `week`. Day and hour grouping honor the
requested `timezone` (IANA name); the frontend passes the user's local timezone.

## Retention

| Data | Retention |
| --- | --- |
| Raw snapshots | 180 days (`SNAPSHOT_RETENTION_DAYS`) |
| Hourly observations | 365 days (`ANALYTICS_HOURLY_RETENTION_DAYS`) |
| Daily aggregates | Indefinitely (materialized in a follow-up) |

Retention is decoupled from the default chart range, which is 30 days.

## Provider support

Analytics capability is declared per provider through reusable metadata rather
than provider-specific conditionals. Providers expose the metric semantics the
analytics engine needs:

- **Anthropic** — token/request counters with native hourly history.
- **OpenAI** — rolling 30-day cost plus native daily cost buckets.
- **Codex** — session/weekly remaining percentages with reset windows.
- **OpenRouter** — credit counters and remaining limit.
- **DeepSeek** — account balance.
- **Firecrawl** — credits and usage percent with a billing window.
- **Custom HTTP** — generic point history; advanced analytics (forecasts,
  pacing) are unavailable because metric semantics are unknown.
