# OpenRouter

Usage Dashboard supports two monitoring modes: **Individual API key** and **Account-wide credits**. Existing configurations remain individual-key configurations.

## Modes and switching

Individual-key mode uses a normal OpenRouter API key and supports a custom compatible endpoint. Account-wide mode uses a Management API key and sends it only to `https://openrouter.ai/api/v1`. New connections select a mode during setup. Existing connections can switch in either direction from Settings; switching requires a replacement credential and submits the credential, mode, and effective endpoint atomically. Switching to account-wide clears an incompatible custom endpoint; supported individual-key endpoints are preserved. Canceling leaves the connection unchanged.

Snapshots and observations are isolated by configuration revision. History from a previous credential or mode is not shown as current after rotation.

## Individual API key

The dashboard calls `GET /api/v1/key` and shows key-level limit, remaining limit, and rolling daily, weekly, and monthly usage. These are not account credit balances, and overlapping rolling windows are not added together.

## Account-wide credits and analytics

The dashboard calls `GET https://openrouter.ai/api/v1/credits`, then prefers the official Analytics Query API. `GET /analytics/meta` validates available metrics, dimensions, granularities, and operators. `POST /analytics/query` requests only metadata-advertised metrics at daily granularity. It uses `request_count` and `date__day` from the Query API response, and requests workspace, model, or upstream-provider dimensions only when metadata advertises them.

The Usage page supports 7-, 30-, 90-, and 365-day ranges plus the current calendar month. Queries and persisted totals use UTC boundaries. Account rows are authoritative; workspace, model, and provider rows are persisted and returned only as separate breakdowns, never added to account totals. The current UTC day, future days, and invalid rows are excluded from completed-day observations. Polling uses a bounded range, so it does not issue an annual historical request on every refresh.

The query response must contain complete `data.data` rows and `data.metadata` (`query_time_ms`, `row_count`, and `truncated`). Truncated, malformed, inconsistent, or unavailable results are rejected. On failure, the documented Activity endpoint remains the fallback. Valid Query rows replace—not add to—Activity fallback rows; native persistence upserts each day within the active configuration revision, preventing repeat-poll double counting.

Credits provide point-in-time balance; valid completed UTC-day native rows provide scoped historical spend and request/token dimensions. `account_credit_balance` is `total_credits - total_usage`; lifetime purchased and used credits are financial state, not workload or historical spend. The credits endpoint does not provide reliable account-wide daily, weekly, or monthly totals, so unavailable values are not estimated from snapshots or individual-key data.

Analytics metadata distinguishes available, genuinely empty, malformed/failed, and stale compatible analytics. Unavailable analytics are not presented as zero. Credit balance remains visible when Analytics Query and Activity parsing fail. The implementation uses a fixed origin, disabled redirects, and the configured bounded request timeout for Management credentials.

## Alerts and aggregation

Account balance supports low-credit alerts, including zero and negative values; recovery clears the alert after replenishment. Credit balance is excluded from workload/spend aggregation, including Hermes attribution. Account-wide and individual-key activity are not silently combined, preventing overlap.

## Manual smoke tests

1. Add an individual-key connection and verify key-level metrics and custom endpoint behavior.
2. Rotate its credential and verify no old-revision observations appear as current.
3. Switch individual-key to account-wide and back; verify instructions, endpoint payload, and incompatible-history warning.
4. Poll with a Management key. Compare `/credits` values with OpenRouter; verify balance and lifetime values remain separate from period spend.
5. When Analytics Query is available, compare a completed UTC daily range and supported model/workspace grouping with OpenRouter. Verify a current day is marked live/incomplete rather than completed.
6. Test an empty scope, unavailable capability, rate-limited response, and a truncated response. None may display as an authoritative zero or overwrite a complete prior range.
7. Change workspace/date selections quickly and confirm a stale response cannot replace the current selection.
8. Verify account totals are not added to individual-key or Hermes totals and model/workspace breakdowns do not inflate their account total.
9. Test low-credit alerts at positive, zero, and negative balances, then verify recovery.
10. Confirm Dashboard and Homepage output contains no credential material.

Live upstream verification was not performed without an authorized Management credential. The integration relies on the published beta contract and its capability metadata.
