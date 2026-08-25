# Data sources

Usage Dashboard separates two concepts that are easy to conflate:

- **Providers** - the accounts/services whose usage, quotas, balances and
  limits are being measured. Provider-reported numbers are **authoritative**
  where available.
- **Data sources** - applications, gateways, or agents that supply additional
  **observed** telemetry about usage flowing through them. Data sources
  supplement provider-reported metrics and are **never** counted as separate
  usage.

[Hermes Agent](https://github.com/NousResearch/hermes-agent) is the first data
source. It can report detailed, per-request usage (tokens, cache, reasoning,
cost) for the portion of your AI usage that passes through it - which is
especially useful for providers that expose little or no detailed usage
information on their own.

## How it works

Usage Dashboard polls a read-only Hermes usage endpoint on an interval,
normalizes the records into the analytics history with a `hermes` provenance
tag, and then attributes that observed usage to your configured providers where
the identifiers line up.

A Hermes outage never deletes previously persisted history: the last
successful sync is retained and the data source reports an error state.

### Providers vs. data sources

```text
provider_total   = authoritative account usage reported by the provider
hermes_observed  = usage observed flowing through Hermes
unattributed     = provider_total - hermes_observed
```

Attribution reports `hermes_observed` as a **subset** of `provider_total`.
It never computes `provider_total + hermes_observed` - that would double-count.

Where the provider exposes an authoritative total, Hermes answers *"where did
this usage come from?"*. Where the provider exposes incomplete metrics, Hermes
provides a detailed view of the usage it can observe while the dashboard
clearly labels the figures as **Hermes-observed only**.

## Connecting Hermes

Usage Dashboard connects to Hermes Agent through the supported
[Hermes Usage Sidecar](./hermes-usage-sidecar.md#install-and-run-locally). Stock
Hermes does not expose this dashboard's `/usage` contract directly; install the
sidecar on the machine running Hermes, then configure the dashboard to poll it.

1. In **Settings → Data sources**, click **Add Hermes source**.
2. In **Install with Hermes**, click **Copy installation prompt**.
3. Paste the copied prompt into Hermes Agent on the machine that runs Hermes.
4. Let Hermes inspect the current sidecar documentation, install the sidecar,
   generate and store a bearer token, enable startup, and verify `/healthz` and
   `/usage` without revealing the token in chat.
5. Hermes will report where the bearer token is stored and the exact command you
   can run to retrieve/copy it.
6. Return to Usage Dashboard and enter the sidecar **base URL** and **bearer
   token** (stored encrypted at rest).
7. Optionally restrict ingestion to specific **profiles**.
8. Set the **poll interval** and click **Connect**, then **Test connection**.

The copied prompt is deliberately scoped to sidecar installation only. It does
not configure Usage Dashboard, providers, provider mappings, or the Hermes data
source form for you.

### Provider mapping

Hermes reports a raw provider identifier per observation (for example `auto`,
`openai-codex`, or `unknown`) that may not match a Usage Dashboard provider id.
Map these raw identifiers to your configured providers so attribution and
analytics use the right provider:

1. In **Settings → Data sources**, click the **Edit provider mappings** (tune)
   icon on a connected Hermes source.
2. Each distinct observed raw provider shows its aggregate cost, tokens,
   requests, and last-observed time.
3. Choose the configured provider each raw identifier belongs to, or leave it
   unmapped. Multiple raw identifiers may map to the same provider.
4. Changes apply immediately and persist. A mapping whose target provider is
   later deleted or disabled is shown as invalid so you can repair it.
5. If you intentionally leave a raw provider unmapped, enable **Mute unmapped
   provider alerts**. The provider remains visible in this dialog, but sync
   result warnings stop prompting you to map it.

Mapping is an attribution layer - the raw Hermes identifier is never rewritten
in stored observations.

The dashboard will then poll `{base_url}/usage` and sync observed usage into the
analytics history. See
[Installing the Hermes Usage Sidecar](./hermes-usage-sidecar.md#add-it-to-usage-dashboard) for the
end-to-end setup steps, multi-profile behavior, token configuration,
verification commands, and Docker networking notes.

### HTTP contract

The Hermes endpoint must return JSON in one of two shapes:

```json
{
  "observations": [
    {
      "timestamp": "2026-08-22T12:00:00Z",
      "session_id": "abc123",
      "profile": "coder",
      "provider": "anthropic",
      "model": "claude-sonnet-4",
      "event_id": "evt_01J5...",
      "input_tokens": 1234,
      "output_tokens": 567,
      "cache_read_tokens": 100,
      "cache_write_tokens": 50,
      "reasoning_tokens": 0,
      "requests": 1,
      "cost": 0.0123,
      "cost_type": "estimated"
    }
  ]
}
```

or a bare array of those records. Recognized metric fields are `input_tokens`,
`output_tokens`, `cache_read_tokens`, `cache_write_tokens`, `reasoning_tokens`,
`requests`, and `cost` (`USD`). `cost_type` may be `estimated`, `actual`, or
`unavailable`. `timestamp` accepts an ISO-8601 string or epoch.

Each record may include an `event_id` (or `id`) - a stable identifier for that
source event. The dashboard stores it and enforces uniqueness per data source so
re-syncing identical data is idempotent. Records without an event ID get a
deterministic identity derived from their full provenance (provider, timestamp,
session, profile, model, cost type, metric, value, unit), so re-fetching the
same data still deduplicates while genuinely distinct observations are
preserved.

> **Hermes Usage Sidecar.** Hermes Agent does **not** currently ship a native
> Usage Dashboard REST endpoint. For Hermes Agent, the supported implementation
> is the standalone
> [Hermes Usage Sidecar](./hermes-usage-sidecar.md), which reads Hermes usage
> metadata read-only and serves the contract above. The dashboard remains
> contract-compatible with any future native Hermes endpoint that returns the
> same shape.

## Privacy

This integration collects **usage metadata only**: timestamps, session ids,
profile, provider, model, token counts, and cost. It does **not** import or
persist prompts, responses, memory contents, tool arguments, or message bodies.

## API

Data source configuration and sync are admin-only. Reading status and
analytics requires the `datasources:read` / `analytics:read` scopes.

```
GET    /api/v1/datasources                          # data source catalog
GET    /api/v1/datasources/configs                  # configured sources
POST   /api/v1/datasources/configs                  # create (admin)
PATCH  /api/v1/datasources/configs/{id}             # update (admin)
DELETE /api/v1/datasources/configs/{id}             # delete (admin)
POST   /api/v1/datasources/configs/{id}/test        # test connection (admin)
POST   /api/v1/datasources/configs/{id}/sync        # sync now (admin)
GET    /api/v1/datasources/configs/{id}/status      # sync/health status

GET    /api/v1/analytics/hermes                     # global Hermes breakdown
GET    /api/v1/analytics/providers/{id}/attribution # provider attribution
```

## Provenance

Metrics carry a source/confidence type so Hermes-observed data is never
confused with provider-reported totals:

| Type | Meaning |
| --- | --- |
| `provider_reported` | Authoritative account-level usage from the provider. |
| `hermes_observed` | Usage observed flowing through Hermes. |
| `derived` / `estimated` | Computed or inferred values. |
| `unavailable` | No data available for this metric. |

The Usage page surfaces this with labels such as **Provider reported**,
**Hermes observed**, **Estimated**, and **Unattributed**.
