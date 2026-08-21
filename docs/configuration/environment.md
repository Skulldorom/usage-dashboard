# Environment variables

The backend reads its configuration from environment variables. The Compose
stack supplies them through `.env`. Values with a default are optional.

## Core

| Variable | Description |
| --- | --- |
| `DATABASE_URL` | Async SQLAlchemy URL. Defaults to the Compose PostgreSQL service. |
| `ENCRYPTION_KEY` | Required Fernet key used to encrypt API credentials at rest. Generate with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`. |

## Database (Compose)

| Variable | Description |
| --- | --- |
| `POSTGRES_DB` | PostgreSQL database name. Defaults to `usage_dashboard`. |
| `POSTGRES_USER` | PostgreSQL user. Defaults to `usage_dashboard`. |
| `POSTGRES_PASSWORD` | PostgreSQL password. Defaults to `change-me` (change it). |
| `POSTGRES_IMAGE` | PostgreSQL image used by Compose. Defaults to `postgres:18-alpine`; the Compose volume is mounted at `/var/lib/postgresql` for the 18+ image layout. |

## Authentication

| Variable | Description |
| --- | --- |
| `ADMIN_SESSION_EXPIRE_HOURS` | Hours before password-login session tokens expire. Defaults to `24`. |
| `ADMIN_RECOVERY_CODE_EXPIRE_MINUTES` | Minutes before setup/reset codes printed in backend logs expire. Defaults to `30`. |

## API access

| Variable | Description |
| --- | --- |
| `BACKEND_CORS_ORIGINS` | Comma-separated allowed origins for the FastAPI API. |
| `HOMEPAGE_ALLOWED_HOSTS` | Comma-separated hostnames that may access `GET /api/v1/homepage` without a bearer token; ports are ignored. All other API routes still require a valid admin session or scoped API token. |
| `CUSTOM_HTTP_ALLOWED_HOSTS` | Comma-separated hostnames the Custom HTTP provider is allowed to reach. Blank allows any host. |

## Images and networking (Compose)

| Variable | Description |
| --- | --- |
| `IMAGE_TAG` | Tag for the default GHCR backend/frontend images. Defaults to `latest`. |
| `BACKEND_IMAGE` | Optional full backend image override. Defaults to `ghcr.io/skulldorom/usage-dashboard-backend:${IMAGE_TAG}`. |
| `FRONTEND_IMAGE` | Optional full frontend image override. Defaults to `ghcr.io/skulldorom/usage-dashboard-frontend:${IMAGE_TAG}`. |
| `NGINX_HTTP_PORT` | Host port published by the frontend/proxy container. Defaults to `3000`. |
| `VITE_API_BASE_URL` | Frontend API base path baked into the published frontend image. Defaults to `/api`. |

## Polling and retention

| Variable | Description |
| --- | --- |
| `AUTO_POLL_ENABLED` | Enables background provider polling. Defaults to `true`. |
| `AUTO_POLL_INTERVAL_MINUTES` | Minutes between automatic provider polls. Defaults to `60`. |
| `SNAPSHOT_RETENTION_DAYS` | Days of raw usage snapshots to retain. Defaults to `180`. |
| `ANALYTICS_HOURLY_RETENTION_DAYS` | Days of normalized hourly analytics observations to retain. Defaults to `365`. Daily aggregates are kept indefinitely once materialized. |
| `REQUEST_TIMEOUT_SECONDS` | Seconds before an upstream provider request times out. Defaults to `20`. |

## Browser extension targets

| Variable | Description |
| --- | --- |
| `EXTENSION_TARGET_CHROME_ID` | Optional runtime Chrome extension ID used by one-click setup. |
| `EXTENSION_TARGET_EDGE_ID` | Optional runtime Edge extension ID. |
| `EXTENSION_TARGET_OPERA_ID` | Optional runtime Opera extension ID. |
| `EXTENSION_TARGET_FIREFOX_ID` | Optional runtime Firefox extension ID. |
| `EXTENSION_TARGET_SAFARI_ID` | Optional runtime Safari extension ID. |

These override the published extension IDs at runtime (loaded through
`/runtime-config.js`), which is useful for testing unpacked/dev builds without
rebuilding the GHCR image. See
[Browser Extension](/integrations/browser-extension) for details.
