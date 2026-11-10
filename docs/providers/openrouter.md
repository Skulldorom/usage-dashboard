# OpenRouter

Usage Dashboard supports two independent monitoring modes. Existing OpenRouter
configurations remain **Individual API key** configurations; no migration or
credential replacement is required.

## Individual API key

Use a standard OpenRouter API key. The dashboard calls `GET /api/v1/key` and
shows that key's configured limit, remaining limit, and rolling daily, weekly,
and monthly usage. These are **key-level limits**, not the account credit
balance. The rolling windows overlap and are not added together.

## Account-wide credits

Select **Account-wide credits** and provide an OpenRouter **Management API
key**. The dashboard calls only `GET https://openrouter.ai/api/v1/credits` and
shows:

- `account_credit_balance`: `total_credits - total_usage`, the available account balance.
- `account_credits_used`: lifetime credits used.
- `account_credits_purchased`: lifetime purchased credits.

Purchased credits are not a monthly spending limit and are never treated as
workload, token cost, or historical spending. OpenRouter's documented credits
endpoint does not supply reliable account-wide daily, weekly, or monthly totals,
so those metrics remain unavailable rather than being estimated from snapshots
or individual key data.

Management keys are elevated administrative credentials. OpenRouter applies
the credential's organization or workspace scope to account data. Usage
Dashboard uses only read-only GET requests, encrypts the credential at
rest, never returns it to the frontend, and sends it only to the fixed
`https://openrouter.ai/api/v1` origin. Create an expiring key and rotate it if
exposed. OpenRouter does not offer a read-only Management API key permission.

## Analytics and alerts

Account credit balance is a point-in-time state metric and can be used for a
low-credit alert. It is excluded from workload/spend aggregation, including
Hermes attribution. Individual key rolling usage remains separate and retains
its existing behavior. Configure one account-wide connection per OpenRouter
account; Usage Dashboard does not aggregate account-wide and individual-key
usage, preventing overlapping data from silently being counted as spending.
