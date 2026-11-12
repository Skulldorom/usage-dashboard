# Agent Guidelines

## Scope

These instructions apply to the whole repository. Read the relevant source, tests, documentation, and recent history before changing behavior. Keep each change focused on the issue or pull request being worked on.

Usage Dashboard is a self-hosted provider-usage application:

- `backend/`: FastAPI, async SQLAlchemy, PostgreSQL, Alembic, and encrypted provider credentials.
- `frontend/`: Vite, React, MUI, and React Router.
- The application tracks provider quota/health, usage history, cost/value analytics, Hermes workload attribution, alerts, and background provider polling.

## Working principles

- Identify and explain the root cause before editing code.
- Preserve existing behavior and API contracts unless the issue explicitly requires a change.
- Prefer existing adapters, services, hooks, utilities, and shared components over introducing duplicates.
- Keep changes scoped; do not perform unrelated refactors, dependency upgrades, formatting sweeps, or generated-file changes.
- Do not weaken assertions, skip tests, or hide errors to make a check pass.
- Never commit credentials, tokens, encryption keys, provider responses containing secrets, or local databases.
- Never log provider credentials, decrypted secrets, authorization headers, or sensitive usage payloads.
- Do not merge or close issues/PRs unless the user explicitly authorizes that action.

## Provider and credential safety

- Treat provider credentials as secrets throughout their lifecycle. Keep encryption-at-rest and redaction behavior intact.
- Validate credentials and custom base URLs at the boundary, and preserve the distinction between management/account-wide and individual-key modes.
- Provider adapters should fail clearly and safely. Do not silently convert an authentication, quota, parsing, or transport failure into a successful zero-value result.
- Preserve provider-specific semantics, units, timestamps, and pricing provenance. Add coverage when a provider has unusual response formats or partial data.
- New providers or provider configurations must integrate with the normal polling lifecycle. Check initial polling, background polling, manual refresh, retries, failure handling, and UI status.

## Polling and refresh behavior

- Keep polling bounded and observable. Preserve existing retry limits, deadlines, intervals, cancellation, and backoff semantics unless the issue changes them.
- A newly added provider must not remain unpolled merely because it was created after an existing polling loop started.
- Prevent duplicate concurrent polls and stale responses from overwriting newer state.
- When polling or refresh state is keyed by a provider set, account, or revision, make the key and invalidation rules explicit. Do not let an old request restart a deadline or clear state belonging to a newer request.
- Manual refresh and background refresh must coordinate without creating request storms or allowing background work to overwrite an active manual operation.
- Add regression tests for timing, concurrency, stale responses, provider additions, and partial failures when those behaviors are affected.

## Analytics, persistence, and migrations

- Analytics state is persisted and may be rebuilt or revised. Preserve revision isolation: data from an older revision must not contaminate a newer one.
- Use transactions and explicit ownership/identity checks for state transitions, claims, deduplication, and concurrent updates.
- Every schema change requires an Alembic migration with a safe upgrade path and, where supported by project conventions, a downgrade path.
- Migrations must work from a fresh database and from the previous production head. Never edit an already-applied migration to change its historical meaning.
- Preserve the latest valid observation when deduplicating native/provider data; do not rely on accidental row order.
- For API changes, update backend tests and the corresponding frontend behavior or contract coverage. Keep error shapes and compatibility in mind.

## Frontend conventions

- Follow the existing React and MUI patterns, theme system, accessibility behavior, and responsive layout.
- Reuse existing API/client and error-handling utilities. Do not add a second request, auth, polling, or notification abstraction for a local need.
- Keep loading, retry, empty, partial-data, and error states explicit.
- Clean up timers, intervals, event listeners, and abortable requests on unmount or superseding work.
- Guard asynchronous results so an older response cannot overwrite current state.
- Do not expose secrets in rendered content, browser storage, logs, URLs, or copied diagnostic data.

## Validation

See the repository's [local development documentation](https://skulldorom.github.io/usage-dashboard/docs/development/local-development.html) for setup details.

Run the checks relevant to the change and report exact results:

```bash
# Backend: activate or create the project's virtual environment first.
PYTHONPATH=backend python -m pytest -q backend
python -m ruff check backend
python -m ruff format --check backend

# Frontend
cd frontend
npm test
npm run lint
npm run build
```

If the project's virtual environment is not active or does not exist, create or activate it according to the development documentation before treating a missing Python module or command as a genuine validation failure.

For database or PostgreSQL behavior, also run the repository's PostgreSQL/Docker-backed tests when available. For frontend behavior, add focused regression coverage before relying only on the production build. Use `git diff --check` before committing.

If a command cannot run, state why. Investigate failures rather than masking them, and distinguish pre-existing failures from regressions.

## GitHub workflow

- Work on a dedicated branch based on the current default branch.
- Keep commits small and descriptive. Do not force-push, reset, or discard uncommitted work without explicit authorization.
- Open or update a draft PR when requested; include the root cause, behavioral changes, tests run, and remaining risks.
- Review the complete diff for unrelated changes, secrets, generated artifacts, and migration mistakes.
- Never claim a check passed unless it actually ran and passed.
