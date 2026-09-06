# Troubleshooting

## Backend won't start: missing encryption key

Compose fails fast when `ENCRYPTION_KEY` is unset. Generate one and add it to
`.env`:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## Frontend shows a blank screen or can't reach the API

The frontend container proxies `/api` to the backend. Confirm:

- The backend container is healthy (`docker compose ps`).
- `VITE_API_BASE_URL` matches your proxy layout (default `/api`).
- `BACKEND_CORS_ORIGINS` includes your frontend origin if you hit the API from a
  different origin.

## Homepage widget returns 401/403

`GET /api/v1/homepage` requires either:

- the request host in `HOMEPAGE_ALLOWED_HOSTS`, or
- a bearer token with the `usage:read` scope.

See [Homepage Dashboard](/integrations/homepage).

## Provider shows no usage

Confirm the connection's **API** switch is enabled, inspect its health warning,
and use **Retry**. Verify that the credential type is correct. Some providers
only expose balance or quota state; they cannot provide native token history.

## Provider shows usage but no cost

Usage permission does not imply billing-history permission. Configure the
correct billing model, then inspect **Value / Cost Efficiency** and **Data
sources & quality**. For PAYG estimates, Hermes needs mapped provider/model and
token-class telemetry with at least 80% pricing coverage. See
[Understanding cost & value](/using/cost-and-value).

## Provider is stale or reports an error

Stale means a recent last-known-good value is still displayed after a failed
refresh. Error means no sufficiently recent usable result exists. Settings shows
the safe error category/stage, last attempt, last success, and a retry action.

- **OpenAI**: ensure the key is an **organization admin** key.
- **Anthropic**: ensure the key is an **Admin API key**, not an inference key.
- **Codex**: a 401/403 means the OAuth token was rejected - re-authorize from
  Settings.
- **Custom HTTP**: the host must be public; private/internal addresses are
  rejected to prevent SSRF.

## Hermes data is missing or unattributed

1. Test and sync the Hermes source under **Settings → Data sources**.
2. Inspect recent observations and widen the Usage date range.
3. Map each raw provider alias to an enabled configured provider.
4. Check profile filters and unknown models.
5. If multiple configurations share a provider, expect workload to appear once
   at provider level rather than being guessed onto one configuration.

## Pricing is partial or unavailable

Open **Data sources & quality** and inspect unknown models, unpriced token
classes, and coverage. Below 80%, an estimate cannot become a PAYG cost basis.
Balances and provider credits are not automatically treated as historical money.
See [Pricing & coverage](/concepts/pricing-coverage).

## Extension can't connect

- Confirm the dashboard URL and token in the extension Options page.
- The token needs `usage:read` and `poll:write` scopes for full functionality.
- For unpacked builds, set the matching `EXTENSION_TARGET_*_ID` and restart the
  frontend.

## Port already in use

Set `NGINX_HTTP_PORT` in `.env` to a different host port:

```bash
NGINX_HTTP_PORT=8080
```
