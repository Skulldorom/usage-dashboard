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
