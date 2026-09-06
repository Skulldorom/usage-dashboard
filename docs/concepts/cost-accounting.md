# Cost accounting

Usage Dashboard separates payment, spend, observed workload, and reconstructed
list price so the same economic event is not counted twice.

## Cost basis

The backend economics result defines its comparison denominator as:

- the selected range's allocated subscription commitment;
- zero for a configured free connection; or
- one PAYG source selected by the precedence in
  [Understanding cost & value](../using/cost-and-value.md#payg-source-precedence).

Rolling provider cost, native billing buckets, Hermes cost, and token pricing
can overlap. They are evidence about the same spend/workload, not separate line
items to sum.

## Efficiency formulas

```text
value multiplier = API-equivalent value / cost basis
tokens per dollar = attributed tokens / cost basis
requests per dollar = attributed requests / cost basis
effective cost per 1M = cost basis / attributed tokens × 1,000,000
```

These require compatible currencies, positive cost where division is needed,
attributed workload, at least 80% pricing coverage, and medium/high attribution
confidence. Otherwise the provider is excluded with a reason.

The current Usage table independently presents subscription efficiency using
the full configured commitment rather than the backend's allocated
`cost_basis`. PAYG rows use the selected PAYG cost basis. This difference is
important when interpreting a range shorter than the billing cadence.

Multiple configurations of one provider make provider-level Hermes workload
ambiguous. The workload is reported once at provider level and is not copied
into every configuration's economics.
