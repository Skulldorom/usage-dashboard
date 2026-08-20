# Automatic polling

Usage Dashboard polls each enabled provider on a fixed interval so the dashboard
and Homepage widget stay current without manual refreshes.

## Settings

| Variable | Description |
| --- | --- |
| `AUTO_POLL_ENABLED` | Enables background polling. Defaults to `true`. |
| `AUTO_POLL_INTERVAL_MINUTES` | Minutes between polls. Defaults to `60`. |

## How it works

- Only enabled provider configurations are polled.
- Polls run concurrently across providers.
- Each poll snapshots usage into history, subject to `SNAPSHOT_RETENTION_DAYS`.

## Manual polling

You can also poll on demand from the API:

- `POST /api/v1/poll` — poll all enabled providers.
- `POST /api/v1/configs/{id}/poll` — poll a single provider.
- `GET /api/v1/poll/status` — read the last poll status.

The browser extension calls these endpoints when you trigger a refresh.
