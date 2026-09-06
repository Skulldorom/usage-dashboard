# Anthropic / Claude

## Endpoint

Usage Dashboard queries
`GET /api.anthropic.com/v1/organizations/usage_report/messages` for the last 24
hours. It also requests `GET /v1/organizations/cost_report` for best-effort
daily cost enrichment.

## Credential

This requires an **Anthropic Admin API key**, created under
**Console → Settings → Organization → Admin API Keys** - not a normal inference
key.

## Metrics

- `input_tokens`
- `output_tokens`
- `cache_creation_tokens`
- `cache_read_tokens`
- `num_requests`
- `daily_cost` (USD, when the cost request succeeds)

## Notes

- The adapter requests a 1-hour bucket width and totals every record in the
  report.
- Cost failure does not discard successful usage. Anthropic's cost endpoint
  does not include Priority Tier costs, so those can be absent from the result.
- A 403 usually means the key lacks admin access to the organization.
