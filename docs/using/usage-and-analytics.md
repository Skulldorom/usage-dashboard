# Usage & analytics

The **Usage** page combines provider state, billing configuration, and optional
Hermes telemetry. Use the provider filter to show all connections or focus on
one, and use the range control to choose the period being analyzed.

## Overview

Four cards answer the quickest questions:

- **Cost** combines configured subscription commitments with known PAYG cost
  bases. It warns when some PAYG cost is unavailable. Mixed currencies are not
  converted or added.
- **Tokens**, **Requests**, and **Sessions** are Hermes-observed totals for the
  selected range (with compatible provider activity as a fallback for tokens or
  requests where available).

When one provider is selected, the cards are scoped to it. If several
connections share that provider, Hermes workload cannot be assigned safely to
one configuration; the page asks you to select **All providers** for the shared
provider-level total.

For subscriptions, the Overview displays the full configured commitment, not
the backend's selected-range allocation. See [Understanding cost & value](./cost-and-value.md).

## Provider usage & quota

Each connection card shows billing type, observed tokens and requests, cost,
and every provider-native quota window the adapter can normalize. Every window
has its own used percentage, status, optional remaining percentage, provenance,
and reset time.

PAYG connections without quotas show the selected spend source. Subscription
providers without a quota say so rather than displaying 0%. Stale or unavailable
provider readings are labelled on the card.

See [Understanding quotas](./quotas.md) and
[Provider health & errors](./provider-health.md).

## Usage over time

This chart shows daily **Hermes-observed** workload. Choose tokens, observed
cost, requests, or sessions, and group by provider or model.

Observed cost here is Hermes telemetry. It is not subscription commitment,
provider-reported spend, or the Cost & Value cost basis. Missing dates are gaps;
a reported zero is shown as an observed zero. These states are deliberately not
interchangeable.

## Cost & value

The table shows each provider's billing model, displayed cost, Hermes-observed
tokens and requests, Tokens/$, Requests/$, Cost/1M tokens, and share of observed
tokens. Hover the cost to see its source, pricing coverage, and catalogue
version.

For PAYG, displayed cost follows the safe source precedence. For subscriptions,
the active page displays and uses the full configured commitment for these table
ratios. The economics API separately calculates a real-period allocation in
`cost_basis`; that allocation is not currently surfaced by this table. Compare
ranges with this distinction in mind.

The line below the table reports the API-equivalent estimate and global Hermes
pricing coverage. An unavailable result means no workload could be priced
safely; a partial result identifies incomplete coverage.

## Breakdown

Tabs group Hermes-observed cost, tokens, requests, sessions, and token share by:

- provider;
- model; or
- Hermes profile.

These totals describe only workload observed by Hermes. They are not added to
provider-native totals. See [Hermes attribution](../concepts/hermes-attribution.md).

## Data sources & quality

This collapsed section summarizes healthy Hermes sources, stale/unavailable
provider snapshots, pricing coverage, and unpriced models. Expand it to see each
source's health, latest observation, number of observations in range, unresolved
provider aliases, pricing catalogue version, unpriced token count, and
diagnostic messages.

For deeper API-level information—including reconciliation, confidence,
forecast, capacity, and attribution endpoints not currently rendered in this
page—see [Analytics configuration and behavior](../configuration/analytics.md)
and the [API reference](../reference/api.md).
