# Understanding cost & value

Cost & Value keeps three questions separate:

1. What did you commit to pay for the plan?
2. What cost belongs to the selected analytics range?
3. What would the observed workload cost at maintained API list prices?

## Terms

| Term | Meaning |
| --- | --- |
| Subscription commitment | The configured plan price for its full cadence, such as USD 20/month. |
| Subscription allocation | The share of that commitment overlapping the selected range. The economics API returns this as `cost_basis`. |
| PAYG cost | Spend for a pay-as-you-go provider, from one authoritative or safe fallback source. |
| Provider-reported cost | A monetary counter/delta returned by the provider. |
| Provider billing history | Dated monetary buckets returned by a native billing/cost endpoint. |
| Pricing estimate | Reconstructed cost from model, token class, timestamp, and the maintained pricing catalogue. |
| Hermes-observed cost/workload | Cost metadata, tokens, requests, and sessions seen by Hermes; it may cover only part of account activity. |
| API-equivalent value | List-price estimate for the Hermes-observed model/token workload. |
| Tokens/$ | Observed attributed tokens divided by the selected cost basis. |
| Requests/$ | Observed attributed requests divided by the selected cost basis. |
| Cost/1M tokens | Selected cost basis divided by attributed tokens, scaled to one million. |
| Value multiplier | API-equivalent value divided by cost basis. |

## PAYG source precedence

The dashboard selects exactly one cost representation:

1. provider-reported spend;
2. provider-native billing history;
3. pricing estimate with at least **80%** token pricing coverage;
4. unavailable.

The selected representations are never added or averaged. This prevents a
provider's rolling spend, billing buckets, and reconstructed price from counting
the same purchase multiple times. When actual spend and a reconstruction both
exist, actual spend is authoritative and the reconstruction is corroborating;
a material disagreement is returned in analytics API reconciliation metadata.

An estimate at 80–94.99% coverage is marked partial but may be used. Below 80%,
it remains diagnostic API-equivalent data and cannot be the PAYG cost basis or a
whole-workload efficiency denominator. Unknown or unpriced tokens are never
silently assigned zero cost.

## Subscription allocation and the current UI

Subscription cost is allocated by the real overlap between the selected range
and billing periods. Month lengths, leap years, monthly/yearly cadence, and an
optional billing anchor are respected. Without an anchor, allocation is aligned
to the selected range and explicitly marked estimated.

The configured USD 20/month remains the commitment; the economics API calculates
only the overlapping portion as its selected-range `cost_basis`. The current
Usage Overview and Cost & Value table display the full commitment and use it for
their subscription efficiency ratios. The allocated value is currently API
detail rather than a separate value in the table.

## Examples

| Connection | Billing configuration | Interpretation |
| --- | --- | --- |
| OpenAI Codex | Subscription, USD 20/month | Display the USD 20 commitment; the API also computes selected-range allocation. Compare only mapped Hermes-observed workload. |
| OpenCode Go | Subscription, USD 10/month | Treat quota-window dollar figures as allowance, not PAYG billed spend. The UI displays the USD 10 commitment. |
| DeepSeek | PAYG | Prefer provider monetary spend when available. The standard balance endpoint is not spend history, so sufficiently covered Hermes token pricing can provide an estimated cost basis. |

Free connections use a zero configured cost basis. When required billing,
attribution, pricing, or compatible currency data is absent, efficiency is
unavailable instead of fabricated. No foreign-exchange conversion is performed.

See [Billing configuration](../configuration/billing.md) and
[Cost accounting](../concepts/cost-accounting.md).
