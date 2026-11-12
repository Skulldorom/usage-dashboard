# Agent Guidelines

## Repository map

Usage Dashboard is a self-hosted provider-usage application:

- `backend/`: FastAPI, async SQLAlchemy, Alembic, provider adapters, polling, and analytics.
- `frontend/`: Vite, React, MUI, Vitest, and the shared API client.
- `docs/`: the user and development documentation; prefer linking to it over duplicating setup details.
- `deploy/`, Dockerfiles, `docker-compose.yml`, nginx configuration, and `frontend/docker-entrypoint.d/`: production deployment contracts.

Read the relevant implementation, tests, and documentation before changing behavior. Keep changes scoped to the issue and preserve existing API and persistence contracts.

## Analytics correctness

The analytics system intentionally preserves uncertainty and provenance:

- Missing is not zero. A failed poll, unavailable metric, absent native bucket, or untrusted observation is a gap; only an explicitly observed zero may become zero-valued history.
- A polling failure must preserve last-known-good usage and history while exposing the current error/stale state. Do not replace the last good result with fabricated zeros or delete prior observations.
- Preserve source, provenance, confidence, coverage, units, timestamps, and source priority. The reconciliation rules in `backend/app/analytics/reconciliation.py` and the concepts documentation are part of the behavior, not presentation-only metadata.
- Provider-native/account-level totals are authoritative where available. Hermes observations describe the subset seen through Hermes and must never be added to the same provider total. Keep unattributed activity visible.
- Preserve observation identity and idempotency. Stable source event IDs, deterministic fallback identities, `config_revision`, provider mappings, and raw Hermes identifiers prevent re-ingestion, attribution drift, and double counting.
- Configuration or credential changes increment the usage revision. Do not mix observations, native backfill state, or analytics state across revisions.
- Counters, gauges, balances, rolling totals, native buckets, snapshots, and estimates have different semantics. Do not sum a point-in-time value or treat an estimate as an authoritative observation.

Relevant implementation and tests include `backend/app/analytics/`, `backend/app/models.py`, `backend/app/datasources/service.py`, `backend/tests/test_analytics.py`, `backend/tests/test_reconciliation.py`, `backend/tests/test_analytics_api.py`, and the data-source tests. See [Missing data vs zero](docs/concepts/missing-vs-zero.md), [Data sources & provenance](docs/concepts/data-provenance.md), and [Hermes attribution](docs/concepts/hermes-attribution.md).

## Authentication and security

There are two distinct bearer-authentication paths:

- Admin sessions are created by password login, stored as hashed entries in `AdminCredential.session_tokens`, expire according to `ADMIN_SESSION_EXPIRE_HOURS`, and may be revoked by logout or password reset.
- Scoped API tokens are separate `ApiToken` records with a `udt_` prefix, hashed storage, scopes, expiry, last-use tracking, and revocation. Preserve route-level scope checks and admin-only boundaries; do not broaden a scoped token into admin access.

The browser intentionally stores the current admin session token through `frontend/src/api.js` using `localStorage`. Preserve the shared client, its `401` cleanup, and its `UNAUTHORIZED_EVENT` behavior unless the issue explicitly changes the session design. Do not confuse this admin session token with encrypted provider credentials or with scoped integration tokens.

Keep the following behavior intact:

- Provider credentials and data-source tokens are encrypted at rest and must never be returned, logged, or exposed in URLs.
- The one-time first-run setup code and password-reset code are intentionally emitted to backend logs for the operator; preserve that narrow behavior without adding broader secret logging.
- Custom HTTP validation must reject credential-looking URLs/paths, absolute URLs in the relative path field, localhost, and hosts resolving to loopback, link-local, private, reserved, unspecified, or multicast addresses. Preserve the explicit `CUSTOM_HTTP_ALLOWED_HOSTS` allowlist behavior and review DNS-resolution changes as SSRF-sensitive.
- `HOMEPAGE_ALLOWED_HOSTS` is a deliberate host-based exception for the homepage payload; other routes still require admin or the required scoped token.

For changes to auth, token handling, provider secrets, host allowlists, SSRF controls, or unauthorized-session behavior, add focused regression coverage in the relevant auth, API, adapter, and frontend tests. See [Authentication](docs/configuration/authentication.md), [API tokens](docs/configuration/api-tokens.md), and [Custom HTTP](docs/providers/custom-http.md).

## Provider architecture

Provider integrations are registry-driven:

- `backend/app/providers/base.py` defines `Metric`, `ProviderUsage`, `ProviderAdapter`, and the optional `native_observations` and analytics capability contracts.
- `backend/app/providers/registry.py` owns `ADAPTERS` and the provider catalog. Current adapters live under `backend/app/providers/` for Firecrawl, Codex, DeepSeek, OpenAI, Anthropic, OpenRouter, OpenCode Go, MiniMax Token Plan, and Custom HTTP.
- `backend/app/providers/icons.py` supplies catalog icons. `backend/app/api/routes.py` validates provider IDs and exposes the catalog. `frontend/src/api.js` and `frontend/src/pages/SettingsPage.jsx` consume that catalog rather than maintaining a second provider list.
- When adding or changing a provider, update the adapter contract, registry, icon/catalog behavior where needed, credential and monitoring-mode handling, analytics capability/native history, provider documentation, and focused adapter/API/frontend tests. Check both initial/manual polling and automatic background polling.
- Preserve provider-specific credential modes, units, limits, reset windows, billing semantics, error categories, degraded states, and unsupported/unavailable metrics. Do not normalize distinct provider meanings into generic zeroes.
- Data sources are separate from providers. Hermes uses `backend/app/datasources/registry.py`, `base.py`, `service.py`, and its scheduler; its raw observations and provider mappings must remain editable without rewriting stored source identifiers.

## Polling and asynchronous refresh

- Backend polling is coordinated in `backend/app/api/routes.py`, including the shared auto-poll lock, manual poll routes, status reporting, and the `AUTO_POLL_ENABLED`/`AUTO_POLL_INTERVAL_MINUTES` settings.
- Preserve bounded requests, cancellation/locking, last-good state, health/error details, stale detection, and the distinction between a successful degraded result and a failed collection.
- A newly created provider must be picked up by the normal polling lifecycle; do not capture a provider list only once at startup.
- Frontend refreshes use the shared API client and generation/loading guards. Clean up timers and abortable work, prevent stale responses from overwriting newer state, and keep manual refresh from racing background refresh.
- Add regression coverage for provider additions, duplicate/concurrent polls, stale responses, timeout/error paths, and partial failures when affected.

## Database and migrations

Local development defaults to SQLite through `backend/app/core/config.py`; production deployments use PostgreSQL. Do not assume SQLite behavior proves PostgreSQL compatibility.

The Alembic history under `backend/alembic/versions/` is an ordered chain through the current head, including auth, API tokens, data sources, observation identity, revision isolation, and analytics state. Never rewrite an applied migration or remove historical columns/data to make a test pass. Schema and persistence changes require a new migration, a safe upgrade path, protection of existing data, and regression coverage.

The PostgreSQL migration CI procedure is defined in `.github/workflows/docker-images.yml`:

```bash
alembic upgrade head
alembic downgrade base
alembic upgrade head
pytest tests/test_postgres_migrations.py
```

That job uses a PostgreSQL 18 service, `DATABASE_URL`, `ENCRYPTION_KEY`, and `POSTGRES_MIGRATION_TEST=1`. Run the equivalent checks for migration or PostgreSQL-specific changes.

## Frontend conventions

- Reuse `frontend/src/api.js`; it owns the API base URL, bearer header, JSON/error parsing, unauthorized-session cleanup, and endpoint paths.
- Keep loading, missing, partial-data, stale, empty, and error states explicit. Missing data must not be rendered as confirmed zero.
- Preserve React/MUI theme, accessibility, responsive layout, and existing component patterns. Add Vitest regression tests beside affected utilities/components.
- Treat API response shapes, error statuses, and `VITE_API_BASE_URL`/nginx routing as contracts. Avoid duplicating request or authentication logic.

## Application update notifications

- Release checks are frontend-only in `frontend/src/lib/releaseCheck.js` and `useUpdateStatus.js`. GitHub requests deliberately bypass the authenticated API client: omit credentials and referrers, use the fixed public endpoint, reject redirects, bound timeout/body size, and log only bounded diagnostic codes.
- Preserve release validation and exact frontend/backend build compatibility. `/auth/status` exposes running backend `APP_VERSION`; frontend `VITE_APP_VERSION` is embedded at build time. Package-tooling versions are not installed application versions.
- Cache only normalized verified metadata for 15 minutes and failures as separate one-minute retry deadlines. No polling loop. Recheck on dashboard load/visibility; hide expired/invalid/failed claims quietly. Web Locks are optional cross-tab deduplication, with localStorage sharing results/backoff and memory fallback.
- Preserve semantic stable ordering, unknown/placeholder suppression, development alternatives without newer-version claims, trusted release links, and per-release/type dismissals. Do not restore the removed backend release endpoint/cache or expose release diagnostics in the footer.
- See [notification architecture](docs/development/update-notifications.md) and the colocated service/component regression tests. Release/image workflow integrity checks remain independent and unchanged.

## Deployment and documentation

- Docker Compose runs PostgreSQL, the backend, and the nginx frontend/proxy with health-aware startup. `backend/Dockerfile` runs Alembic then Uvicorn; `frontend/Dockerfile` builds the Vite app and serves it through nginx.
- `frontend/nginx.conf` owns SPA fallback and `/api`/`/health` proxying. `VITE_API_BASE_URL` is a build-time value; `frontend/docker-entrypoint.d/40-runtime-config.sh` only renders supported runtime extension configuration.
- Native Linux uses the shipped systemd migration/backend units and operator-managed nginx. Standalone containers use the frontend proxy and an operator-managed PostgreSQL/TLS boundary.
- When deployment contracts, image commands, routes, environment variables, nginx/systemd assets, or runtime configuration change, run `sh scripts/check-deployment-assets.sh`.
- Update the relevant documentation for API, configuration, provider, analytics, authentication, or deployment behavior. Start with [Local development](docs/development/local-development.md), [Testing](docs/development/testing.md), [Installation options](docs/getting-started/installation.md), and the linked topic pages rather than copying large sections into this file.

## Validation and CI

Use an active Python environment, or create the project environment described in the development documentation. Do not assume a root-level `.venv` exists, and do not report a missing executable/module as an application test failure before checking setup.

```bash
# Backend
cd backend
# If needed: python -m venv .venv && . .venv/bin/activate
# Then install requirements according to docs/development/local-development.md.
pytest
cd ..
ruff check backend
ruff format --check backend

# Frontend
cd frontend
npm ci
npm run test
npm run lint
npm run build
cd ..

# Deployment-contract checks when relevant
sh scripts/check-deployment-assets.sh

# Before committing
git diff --check
```

Report exact results: passed, failed, skipped, and unrun checks, including why a check could not run. Do not weaken tests or claim validation that did not execute.

The workflows use path filters. `.github/workflows/docker-images.yml` covers backend/frontend/Docker Compose changes; `.github/workflows/docs-ci.yml` covers documentation and deployment-asset paths. A documentation-only change such as `AGENTS.md` may intentionally trigger no workflow check. Use workflow dispatch or local validation when appropriate, and report checks as unrun rather than implying success.

## GitHub workflow

- Work on a dedicated branch and keep commits focused.
- Review the complete diff for unrelated files, secrets, generated artifacts, and migration mistakes.
- Do not force-push, reset, discard uncommitted work, merge PRs, or close issues/PRs without explicit authorization.
- PR descriptions should state the root cause or purpose, changed behavior, validation performed, and remaining concerns.
