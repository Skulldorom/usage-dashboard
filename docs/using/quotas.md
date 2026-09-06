# Understanding quotas

A quota window is an allowance measured over a provider-defined period. Several
windows may apply to the same request at once, so Usage Dashboard displays them
independently and never adds their percentages.

| Provider | Windows shown when reported |
| --- | --- |
| OpenAI Codex | Session (5-hour) and weekly; code-review session/weekly metrics may also be present |
| OpenCode Go | Session/5-hour, weekly, and monthly |
| Firecrawl | Billing-period credits and utilization |
| OpenRouter | Credit remaining plus daily, weekly, and monthly usage |

## Remaining and consumed

Providers may report either side of the same quota:

- **Remaining %** is capacity still available.
- **Consumed %** or **capacity used %** is the portion already used.

The dashboard normalizes supported remaining metrics to consumed capacity for
comparison. A provider value of 64% remaining corresponds to 36% consumed. It
does not rewrite the provider's raw metric.

## Reset times and overlapping windows

Each window has its own reset time. Using the session allowance does not imply
that the weekly allowance resets. When a reset timestamp is unavailable, the
window remains useful but no reset is invented. A detected rollover is treated
as a reset rather than negative consumption.

## Capacity, overage, and pace

- **Capacity %** is the normalized percent consumed in one window.
- **Overage** is the amount above 100% when a provider permits or reports usage
  beyond the nominal allowance.
- **Pace ratio** compares actual burn rate with even use through the window.
- **Burn/forecast** is available through the analytics API and projects from
  observed history to the window reset. It is unavailable when there is
  insufficient history or no meaningful reset window; the active Usage page
  does not currently render this advanced forecast.

## Missing windows

Providers and plans do not always return every possible window. Missing means
not observed, not zero. The Dashboard homepage summary includes only the windows
present in the latest provider response.
