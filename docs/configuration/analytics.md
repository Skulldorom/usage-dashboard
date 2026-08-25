# Usage analytics

The **Usage** page turns the provider snapshots collected by Usage Dashboard
into historical analytics: trends, daily/hourly breakdowns, peak-usage windows,
previous-period comparisons, and pace-based forecasts.

Analytics are built as a normalization layer on top of the existing
`UsageSnapshot` history - not a separate tracking system. Nothing about the
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

- **Summary cards** - usage this week, average per day, trend vs. last week.
- **Historical chart** - the selected metric over time (hourly / daily / weekly).
- **Daily breakdown** - per-day usage, peak hour, day-over-day change, and status.
- **Time-of-day heatmap** - when usage concentrates across the day and week.
- **Previous-period comparison** - current period vs. the equivalent prior period.
- **Forecast** - rate-based projections, estimated exhaustion, and a sustainable
  daily pace, with a `high` / `medium` / `low` confidence indicator.
- **All providers comparison** - a cross-provider view with like-unit totals,
  a per-provider share table, and a quota-utilization overlay.

Forecasts are deterministic and rate-based; they are scoped to the relevant
reset window and never extrapolate a rolling total (like OpenAI's 30-day cost)
as if it were a simple counter. Confidence reflects observation count, history
span, data coverage, and whether data is provider-native or snapshot-derived.
Missing samples are reported as gaps, not zero usage.

The chart defaults to a **30-day** window regardless of how much history is
retained.

## Provider health & stale data

Each configured provider exposes a **health state** derived from its most recent
collection attempts, so the dashboard can tell fresh data apart from stale
last-known-good data and outright failures:

| State | Meaning |
| --- | --- |
| `healthy` | The most recent refresh succeeded and displayed data is current. |
| `stale` | The latest refresh failed, but a recent successful snapshot exists. The dashboard keeps showing the last-known-good values and marks them stale. |
| `error` | The provider cannot currently be queried and there is no useful (or no recent enough) successful value. |
| `never_connected` | The provider has not yet produced a successful collection. |

A failed refresh **never** replaces useful values with zero or an empty state.
The last successful snapshot is retained and returned as `last_good`, and a
failed collection does not create a zero-usage observation for analytics (it is
treated as missing data, not zero usage).

Staleness is determined from the polling interval (a provider expected to
refresh hourly becomes stale after missing roughly two expected refreshes)
rather than a single hard-coded duration.

### Health in the API

`GET /api/v1/usage` now returns, per provider, a `health` object alongside the
existing `latest` snapshot:

```json
{
  "health": {
    "status": "stale",
    "last_attempt_at": "2026-08-22T11:55:00+00:00",
    "last_success_at": "2026-08-22T09:40:00+00:00",
    "last_failure_at": "2026-08-22T11:55:00+00:00",
    "consecutive_failures": 3,
    "latest_error": "connect timeout",
    "age_seconds": 8100,
    "is_stale": true
  }
}
```

`last_good` is populated only while the last-known-good value is still within
policy (`status == "stale"`). The browser extension and other API consumers can
read `health` to represent provider state consistently without independently
guessing whether data is stale. Error text is sanitized and never includes
credentials.

## Analytics API

The `GET /api/v1/usage` endpoint remains focused on current/latest state.
Historical analytics live under `GET /api/v1/analytics/*` and require the
`analytics:read` scope (admin sessions are always allowed):

```
GET /api/v1/analytics/summary
GET /api/v1/analytics/overview?interval=&from=&to=&timezone=
GET /api/v1/analytics/providers/{config_id}
GET /api/v1/analytics/providers/{config_id}/timeseries?metric=&interval=&from=&to=&timezone=
GET /api/v1/analytics/providers/{config_id}/daily?metric=&from=&to=&timezone=
GET /api/v1/analytics/providers/{config_id}/hourly?metric=&date=&timezone=
GET /api/v1/analytics/providers/{config_id}/forecast?metric=&timezone=
GET /api/v1/analytics/providers/{config_id}/comparison?metric=&window=day|week|month&timezone=
```

`interval` is one of `hour`, `day`, or `week`. Day and hour grouping honor the
requested `timezone` (IANA name); the frontend passes the user's local timezone.

## Source reconciliation & data audit

Because provider-reported and Hermes-observed data describe the *same* underlying
usage, the dashboard never blindly sums them. Each provider's analytics value is
built from an **authoritative** source with other compatible observations used as
**corroboration**:

- **Authoritative priority** — `native` provider data &gt; `snapshot`-derived &gt;
  `hermes`-observed &gt; `estimated`.
- **Material disagreement** — when a corroborating source differs from the
  authoritative value by more than a tolerance (15 percentage points for
  capacity, 50% relative for activity), it is flagged as a disagreement rather
  than silently blended in.
- **Staleness guard** — a corroborating source fresher than the authoritative
  reading (by more than 6 hours) marks the authoritative data as potentially
  stale, so lagging primary data cannot silently win on priority alone.
- **Confidence degradation** — disagreements and staleness each reduce the
  provider's confidence by one step (`high → medium → low`).

### "Why this number?" audit

Each provider row in the comparison table exposes a **"Why this number?"**
button. It opens a panel showing, per value:

- the authoritative source and value;
- the quota/window and reset timestamp (capacity);
- corroborating sources and Hermes activity/estimated cost (activity);
- the confidence level; and
- any reconciliation warnings (disagreements, staleness).

This makes unexpected analytics diagnosable without inspecting the database or
API directly. The same reconciliation metadata is available under `audit.*.reconciliation`
in the `/analytics/overview` response.

## Estimated cost (Hermes-derived)

When a Hermes data source supplies **model + token-class** telemetry for a mapped
provider, the dashboard derives a supplementary **estimated cost** by pricing
those token classes against a maintained catalogue of provider/model list prices.

The estimate is intentionally distinct from provider-reported cost:

- Token classes — `input`, `output`, `cache read`, `cache write`, and
  `reasoning` — are priced **separately** where the catalogue lists them.
- Rates are selected **by effective date**, so historical usage is priced with
  the rate in effect on each observation's date rather than today's price.
- The result is always labelled **Estimated cost** and carries the catalogue
  version (`pricing_version`) used, so a number can be traced to its rate set.
- Unknown models, and token classes with no listed rate, are surfaced as
  **unpriced** — never silently priced at zero.
- `requests` and provider-reported `cost` are never token-priced; the estimate
  is never added to provider-authoritative totals.

### Pricing catalogue

Prices live in `backend/app/analytics/pricing.py`. Entries are keyed by
(provider, model) with an `effective_from` date and per-token-class USD rates
per 1M tokens. Bump `PRICING_VERSION` whenever you edit an entry so existing
dashboards can tell which rate set produced a stored number. Seed values are
representative list prices and should be reviewed against current provider
pricing pages.

## Cross-provider comparison

Because providers report different units (tokens, USD, credits, percentages),
the "All providers" view compares along two honest axes:

- **Like-unit totals and share** - consumption is summed only within matching
  units, and each provider's share is its fraction of its own unit group (so
  "95% of tokens" is real, never tokens blended with USD).
- **Quota utilization** - each quota-tracking provider's fraction of its own
  quota consumed (0–100%), overlaid on one chart. Providers without a declared
  quota (token/balance/cost providers) simply don't appear on the overlay.

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

- **Anthropic** - token/request counters with native hourly history.
- **OpenAI** - rolling 30-day cost plus native daily cost buckets.
- **Codex** - session/weekly remaining percentages with reset windows.
- **OpenRouter** - credit counters and remaining limit.
- **DeepSeek** - account balance.
- **Firecrawl** - credits and usage percent with a billing window.
- **Custom HTTP** - generic point history; advanced analytics (forecasts,
  pacing) are unavailable because metric semantics are unknown.
