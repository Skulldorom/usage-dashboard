# Pricing & coverage

The pricing catalogue maps provider/model identifiers and effective dates to
per-million-token rates for supported input, output, cache-read, cache-write,
and reasoning classes.

Historical observations use the price effective at their timestamp. Each
result identifies its pricing catalogue version. An unknown model or unsupported
token class remains unpriced instead of receiving a zero rate.

## Coverage levels

Pricing coverage is priced tokens divided by all attributed tokens:

- **High:** at least 95%.
- **Partial:** at least 80% but below 95%.
- **Insufficient:** below 80%, or no token workload.

Partial results carry their unpriced token count. At least 80% is required for a
pricing estimate to become a PAYG cost basis and for whole-workload efficiency
comparisons. Attribution confidence must also be medium or high.

To improve coverage, verify Hermes provider mappings, inspect unknown models in
**Data sources & quality**, and ensure the source emits separate token classes
and accurate timestamps.
