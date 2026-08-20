# Configuration

Usage Dashboard is configured almost entirely through environment variables,
passed to the backend and frontend containers via `.env` and `docker-compose.yml`.

- [Environment variables](/configuration/environment) — the full reference.
- [Authentication](/configuration/authentication) — admin password, sessions, and setup/reset codes.
- [API tokens](/configuration/api-tokens) — scoped tokens for integrations.
- [Automatic polling](/configuration/polling) — background usage polling.

## Where variables live

Copy `.env.example` to `.env` and edit it. Compose interpolates `.env` into the
`backend` and `frontend` service environments. The backend reads the same names
directly (via pydantic-settings), so a non-Compose deployment can set them
straight in the environment.
