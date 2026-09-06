# OpenRouter

## Endpoint

Usage Dashboard queries `GET /openrouter.ai/api/v1/key` with the same bearer
token used for inference.

## Credential

Your OpenRouter API key.

## Metrics

- `limit_remaining` - credits remaining against your limit.
- `usage_daily` - credits used today.
- `usage_weekly` - credits used this week.
- `usage_monthly` - credits used this month.
- `limit` - your configured credit limit.

## Notes

- The summary surfaces remaining credit, with daily/weekly/monthly usage
  available as secondary metrics.
- These windows overlap and are not added together. The adapter does not expose
  arbitrary-range native billing history; credit state is not assumed to be USD
  spend.
