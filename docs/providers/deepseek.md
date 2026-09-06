# DeepSeek

## Endpoint

Usage Dashboard queries `GET /api.deepseek.com/user/balance`.

## Credential

A standard DeepSeek API key.

## Metrics

- `total_balance` - combined balance.
- `granted_balance` - granted (free) balance.
- `topped_up_balance` - balance you topped up.
- `available` - whether the account balance API is currently available.

## Notes

- The adapter prefers the `USD` balance entry when the response lists multiple
  currencies.
- If the account is unavailable, the provider reports `degraded` rather than
  `healthy`.
- A standard DeepSeek API key exposes balance, but not safe historical billing
  records. Usage Dashboard does not scrape console sessions or store browser
  credentials to work around that limitation.
- For PAYG economics, provider monetary observations remain authoritative. When
  those are unavailable and Hermes supplies a model, timestamp, input/cache-miss,
  cache-hit, and output token classes, cost is estimated from DeepSeek's
  [official pricing](https://api-docs.deepseek.com/quick_start/pricing/).
- DeepSeek V4 estimates apply the exact 2026-08-16 16:00 UTC effective time and
  the provider's two weekday peak windows. Unknown models or missing token
  classes remain unpriced, and partial estimates are labelled with coverage.
