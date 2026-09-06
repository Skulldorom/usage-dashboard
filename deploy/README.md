# Production deployment assets

These files are the supported examples used by the
[Native Linux installation guide](../docs/getting-started/native-linux.md):

- `systemd/usage-dashboard-migrate.service` runs Alembic before the API starts.
- `systemd/usage-dashboard-backend.service` runs the FastAPI application with
  Uvicorn and restarts it after failures.
- `nginx/usage-dashboard.conf` serves the built frontend and proxies `/api/`
  and `/health` to the backend on `127.0.0.1:8000`.
- `backend.env.example` documents the native backend environment contract.

The paths assume installation at `/opt/usage-dashboard` and configuration in
`/etc/usage-dashboard/backend.env`.
