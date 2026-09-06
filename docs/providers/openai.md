# OpenAI

## Endpoint

Usage Dashboard queries `GET /api.openai.com/v1/organization/costs` over the
last 30 days and totals the spend.

## Credential

This endpoint **requires an organization admin key** - a project or user API key
will not have access. Create one under your OpenAI organization settings.

## Metrics

- `cost_30d` - total spend over the last 30 days, in your org's currency.
- `daily_cost` - native dated cost buckets used by analytics.

## Notes

- The adapter requests a 1-day bucket width and sums all results.
- The rolling 30-day total is state; it is not extrapolated as a cumulative
  activity counter. Native daily buckets provide the PAYG billing-history cost
  source for matching selected ranges.
- A 401/403 usually means the key is not an admin key.
