# Analytics configuration and behavior

This page is the operator-oriented analytics reference. For the product tour,
start with [Usage & analytics](../using/usage-and-analytics.md).

Analytics normalize saved provider snapshots, provider-native dated buckets,
and optional Hermes observations. They do not form a second collection system.
The default selected range is 30 days; retention is configured separately.

## Metric behavior

- Counters can produce interval consumption deltas.
- Gauges, balances, and rolling totals are point-in-time state and are not
  summed as activity.
- Remaining/rate-limit values can produce consumption only when the adapter
  declares safe capacity and reset semantics.
- Native dated buckets are used directly where available; otherwise history is
  derived from polling snapshots.
- Known reset timestamps take priority over reset heuristics. A rollover is not
  reported as negative usage.

Aggregation can be hourly, daily, or weekly. Day/hour grouping honors the IANA
`timezone` parameter; the frontend uses the browser's timezone.

## Forecasts, confidence, and reconciliation

Forecasts are deterministic rate projections scoped to a meaningful reset
window. Confidence considers observation count, time span, coverage, and source.
Provider-native observations have priority over snapshot-derived, Hermes, and
estimated evidence. Material disagreement and stale authoritative data reduce
confidence and are returned in analytics API audit metadata.

These capabilities are available from the analytics API. The active Usage page
focuses on the simpler workload, quota, cost, breakdown, and data-quality views;
it does not currently render every advanced analytics response.

## Related guides

- [Understanding quotas](../using/quotas.md)
- [Understanding cost & value](../using/cost-and-value.md)
- [Data sources & provenance](../concepts/data-provenance.md)
- [Missing data vs zero](../concepts/missing-vs-zero.md)
- [API reference](../reference/api.md)
