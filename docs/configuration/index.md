# Configuration

Usage Dashboard is configured almost entirely through environment variables,
passed to the backend and frontend containers via `.env` and `docker-compose.yml`.

- [Environment variables](/configuration/environment) - the full reference.
- [Authentication](/configuration/authentication) - admin password, sessions, and setup/reset codes.
- [API tokens](/configuration/api-tokens) - scoped tokens for integrations.
- [Connected providers](/configuration/connected-providers) - connections, labels, visibility, ordering, and health.
- [Billing](/configuration/billing) - PAYG, subscription, free, currency, cadence, and billing anchors.
- [Automatic polling](/configuration/polling) - background usage polling.
- [Analytics behavior](/configuration/analytics) - normalization and operator reference.
- [Data sources](/configuration/data-sources) - Hermes telemetry and mappings.

## Where variables live

Copy `.env.example` to `.env` and edit it. Compose interpolates `.env` into the
`backend` and `frontend` service environments. The backend reads the same names
directly (via pydantic-settings), so a non-Compose deployment can set them
straight in the environment.
