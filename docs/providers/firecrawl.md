# Firecrawl

## Endpoints

Usage Dashboard queries two Firecrawl endpoints:

- `GET /api.firecrawl.dev/v2/team/credit-usage` — current remaining and plan credits.
- `GET /api.firecrawl.dev/v2/team/credit-usage/historical` — usage consumed in the
  billing period.

## Credential

A Firecrawl API key.

## Metrics

- `credits_remaining` — credits left on the current plan.
- `credits_used` — credits consumed this billing period.
- `usage_percent` — percent of the plan consumed.
- `plan_credits` — the plan's total credit allotment.
- `billing_period_end` — when the plan credits refresh.

## Notes

- `usage_percent` is derived from `credits_used / plan_credits`.
- The summary includes the plan name and refresh date when available.
