# Using Usage Dashboard

Usage Dashboard has two complementary views:

- **Dashboard** shows the latest state of each visible provider: current balance,
  quota, usage windows, refresh time, and warnings.
- **Usage** explains history and economics: what was consumed, when it was
  consumed, what it cost, and how confidently it can be attributed.

Start with [Dashboard](./dashboard.md) for day-to-day monitoring. Use
[Usage & analytics](./usage-and-analytics.md) when you need trends, comparisons,
cost analysis, or Hermes attribution.

The application deliberately preserves uncertainty. Missing observations are
not converted to zero, incompatible units are not combined, and provider totals
are not added to Hermes observations of the same workload.
