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

## Provider reports "degraded" or errors

- **OpenAI**: ensure the key is an **organization admin** key.
- **Anthropic**: ensure the key is an **Admin API key**, not an inference key.
- **Codex**: a 401/403 means the OAuth token was rejected — re-authorize from
  Settings.
- **Custom HTTP**: the host must be public; private/internal addresses are
  rejected to prevent SSRF.

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
