# Provider health & errors

Every connection has a health state derived from collection attempts and the
age of its last success.

| State | Meaning | Display behavior |
| --- | --- | --- |
| Healthy | Latest refresh succeeded. | Current data is shown. |
| Stale | Latest refresh failed, but a recent last-known-good snapshot exists. | The saved value remains visible and is marked stale. |
| Error | The provider cannot be queried and no sufficiently recent usable value exists. | Error guidance is shown; no zero is invented. |
| Never connected | No refresh has ever succeeded. | Setup/retry guidance is shown. |

Staleness follows the connection's polling interval: approximately two missed
expected refreshes, rather than one universal duration. A failed refresh does
not create a zero analytics observation or erase successful history.

## Error details and retry

**Settings → Connected providers** shows a warning below affected connections,
including a safe action, HTTP status and collection stage when available, last
attempt, and last successful sync. Use **Retry** to poll that connection again.
Authentication failures normally require replacing or reauthorizing the
credential; network and rate-limit failures may succeed after the cause clears.

Provider errors are sanitized before storage/API display. Credentials, request
headers, query secrets, response bodies, and credential-like text are redacted.

## Common cases

- **No usage:** confirm API is enabled, the credential has the required scope,
  then retry. Some providers expose balances or quotas rather than token usage.
- **Usage but no cost:** usage access does not imply historical billing access.
  Configure billing and inspect pricing coverage/Hermes mappings.
- **Stale data:** check provider reachability, rate limits, and polling status;
  the displayed reading is last-known-good.
- **Partial pricing:** map the provider/model correctly and inspect unknown
  models or missing token classes.
- **Hermes not attributed:** sync the source, widen the selected range, and fix
  unmapped aliases under **Settings → Data sources**.

See [Troubleshooting](/troubleshooting) for provider-specific checks.
