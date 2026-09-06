# OpenCode Go

## Endpoint and credential

Usage Dashboard queries `GET /zen/go/v1/usage` with an OpenCode Go API key.
The default base URL is `https://opencode.ai`.

## Metrics

The adapter supports independent 5-hour, weekly, and monthly windows, including
used/remaining percentages, USD-denominated allowance usage and remaining
amounts, limits, and reset timestamps when returned. It also surfaces plan type,
exhaustion, balance-fallback state, and per-model usage/request limits.

When the provider omits known per-model limits, the adapter can enrich supported
model identifiers with its built-in documented limits. Unknown models remain
unknown.

## Billing

OpenCode Go is a subscription service. Configure its actual plan commitment
under **Settings → Connected providers → Billing**. Window amounts are allowance
state and are not treated as historical PAYG billed spend.

Quota windows overlap and are displayed independently. See
[Understanding quotas](../using/quotas.md).
