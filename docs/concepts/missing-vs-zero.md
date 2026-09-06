# Missing data vs zero

Zero is an observation: the provider or data source reported no usage in a
period. Missing means no trustworthy observation exists for that period.

Usage Dashboard preserves this distinction:

- an observed zero can be plotted at zero;
- a missed poll, failed refresh, absent native bucket, or unavailable metric is
  a gap;
- failed refreshes retain last-known-good state but do not create zero history;
- providers without a quota are excluded from capacity totals rather than
  counted as 0% used.

Replacing gaps with zero would understate usage, distort burn rate and
forecasts, and falsely improve coverage. A line crossing a chart gap should not
be interpreted as confirmed inactivity.
