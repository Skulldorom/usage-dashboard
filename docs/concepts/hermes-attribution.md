# Hermes attribution

Hermes contributes request-level observations: timestamp, session, profile,
provider identifier, model, token classes, requests, and optional cost metadata.
The provider contributes account-level usage, balance, quota, or billing data.

When both describe the same workload:

```text
provider total = authoritative account activity
Hermes observed = the subset seen flowing through Hermes
unattributed = provider total minus the compatible Hermes subset
```

They are never added. If a provider lacks detailed native usage, the dashboard
can still show Hermes-only workload, explicitly labelled as observed rather than
complete account usage.

## Mapping and attribution

Hermes provider identifiers such as `auto` or `openai-codex` may not match a
configured adapter ID. Provider mappings translate those identifiers without
rewriting stored raw observations. Profile and model fields power the Breakdown
views; session IDs provide session counts.

An unresolved alias remains visible in diagnostics. When multiple dashboard
configurations share one provider, Hermes data cannot be assigned safely to a
specific connection, so it is presented once at provider level.

## Pricing and reconciliation

Model, timestamp, and token class can be priced using the versioned catalogue to
produce API-equivalent value. Unknown models and unsupported token classes are
unpriced and reduce coverage. Hermes-provided or reconstructed cost does not
replace higher-priority provider spend and is never added to it.

See [Data sources](../configuration/data-sources.md) for setup and
[Pricing & coverage](./pricing-coverage.md) for completeness rules.
