# Billing configuration

Billing configuration tells analytics how you pay for a connection. It does not
change provider billing and does not purchase, cancel, or modify a plan.

Open the `$` action on a connected-provider row, or set billing while adding a
provider.

## Pricing models

| Model | Configure | Cost & Value behavior |
| --- | --- | --- |
| PAYG | No subscription amount | Uses one provider spend source or, when unavailable, a sufficiently covered pricing estimate. |
| Subscription | Amount, three-letter currency, monthly/yearly cadence, optional billing anchor | Allocates the commitment across the selected range using real billing-period overlap. |
| Free | No amount | Uses a zero configured cost basis. |

The billing anchor is a known boundary of your provider billing period. Adding
it makes allocation line up with actual renewals. Without it, allocation is
still calculated but marked estimated.

## Recommended examples

```text
OpenAI Codex   Subscription   20 USD   Monthly
OpenCode Go   Subscription   10 USD   Monthly
DeepSeek      PAYG
```

For subscriptions, quota dollar values describe allowances and are not treated
as billed PAYG spend. For DeepSeek, the balance is account state rather than
historical spend; a Hermes-derived pricing estimate may be used only when its
pricing coverage reaches the safe threshold.

If billing information is missing or incompatible with the observed currency,
Cost & Value leaves comparisons unavailable and explains why. It does not guess
an amount or perform currency conversion.

For formulas, source precedence, and coverage rules, see
[Understanding cost & value](../using/cost-and-value.md).
