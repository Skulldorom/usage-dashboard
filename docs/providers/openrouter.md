# OpenRouter

Usage Dashboard supports two monitoring modes: **Individual API key** and **Account-wide credits**. Existing configurations remain individual-key configurations.

## Modes and switching

Individual-key mode uses a normal OpenRouter API key and supports a custom compatible endpoint. Account-wide mode uses a Management API key and sends it only to `https://openrouter.ai/api/v1`. New connections select a mode during setup. Existing connections can switch in either direction from Settings; switching requires a replacement credential and submits the credential, mode, and effective endpoint atomically. Switching to account-wide clears an incompatible custom endpoint; supported individual-key endpoints are preserved. Canceling leaves the connection unchanged.

Snapshots and observations are isolated by configuration revision. History from a previous credential or mode is not shown as current after rotation.

## Individual API key

The dashboard calls `GET /api/v1/key` and shows key-level limit, remaining limit, and rolling daily, weekly, and monthly usage. These are not account credit balances, and overlapping rolling windows are not added together.

## Account-wide credits and Activity

The dashboard calls `GET https://openrouter.ai/api/v1/credits` and the documented Activity endpoint. Credits provide point-in-time balance; valid completed UTC-day Activity rows provide scoped historical spend and request/token dimensions. Current-day, future, invalid, and out-of-window rows are excluded. Rejected rows do not claim complete coverage.

Analytics metadata distinguishes available, genuinely empty, malformed/failed, and stale compatible analytics. Unavailable analytics are not presented as zero. Credit balance remains visible when Activity parsing fails.

`account_credit_balance` is `total_credits - total_usage`; lifetime purchased and used credits are not workload or historical spending. The credits endpoint does not provide reliable account-wide daily, weekly, or monthly totals, so unavailable values are not estimated from snapshots or individual-key data.

Workspace-wide analytics and complete arbitrary-period reporting remain unsupported under issue #242.

Management keys are elevated credentials. The dashboard uses read-only GET requests, encrypts credentials at rest, never returns them to the frontend, and sends them only to the fixed OpenRouter origin. Create an expiring key and rotate it if exposed. OpenRouter does not offer a read-only Management API key permission.

## Alerts and aggregation

Account balance supports low-credit alerts, including zero and negative values; recovery clears the alert after replenishment. Credit balance is excluded from workload/spend aggregation, including Hermes attribution. Account-wide and individual-key activity are not silently combined, preventing overlap.

## Manual smoke tests

1. Add an individual-key connection and verify key-level metrics and custom endpoint behavior.
2. Rotate its credential and verify no old-revision observations appear as current.
3. Switch individual-key to account-wide and back; verify instructions, endpoint payload, and incompatible-history warning.
4. Poll with a Management key, then simulate malformed Activity; credits must remain visible while analytics shows failure.
5. Test low-credit alerts at positive, zero, and negative balances, then verify recovery.
6. Confirm Dashboard and Homepage output contains no credential material.

Unsupported native workspace analytics and complete period totals remain tracked under issue #242.
