# Standalone containers

Use this contract when your container platform manages individual containers
instead of Docker Compose. The commands below are a reference implementation;
Portainer, Unraid, Synology Container Manager, and other systems should create
equivalent resources rather than requiring product-specific templates.

## Published images and ports

| Image | Container port | State | Startup behavior |
| --- | --- | --- | --- |
| `ghcr.io/skulldorom/usage-dashboard-backend:<tag>` | `8000` | Stateless; data is in PostgreSQL | Runs `alembic upgrade head`, then Uvicorn |
| `ghcr.io/skulldorom/usage-dashboard-frontend:<tag>` | `80` | Stateless production Vite build | nginx serves the SPA and proxies to `backend:8000` |

Use the same release tag for both images. `latest` follows the current default
branch; a version tag is safer for production.

The examples below use `IMAGE_TAG=v1.2.0`; replace it with an existing release.

The frontend nginx configuration requires the backend to resolve as the DNS
name **`backend`** on a shared user-defined network. It proxies `/api/` and
`/health`; browsers should access the frontend only. `VITE_API_BASE_URL=/api` is
baked into the published image and is not a runtime override.

## Database and persistence

PostgreSQL is required. Supply an existing PostgreSQL service or run a
PostgreSQL 18 container. Persist PostgreSQL at `/var/lib/postgresql` (the parent
directory required by the `postgres:18-alpine` image), and never publish its
port unless your network design requires it.

This example creates the same topology as Compose:

```bash
docker network create usage-dashboard
docker volume create usage-dashboard-postgres
IMAGE_TAG=v1.2.0

docker run -d --name db --network usage-dashboard --restart unless-stopped \
  -e POSTGRES_DB=usage_dashboard \
  -e POSTGRES_USER=usage_dashboard \
  -e POSTGRES_PASSWORD='<strong-url-safe-password>' \
  -v usage-dashboard-postgres:/var/lib/postgresql \
  --health-cmd='pg_isready -U usage_dashboard -d usage_dashboard' \
  --health-interval=10s --health-timeout=5s --health-retries=5 \
  postgres:18-alpine
```

Wait until PostgreSQL is healthy before starting the backend.

## Backend contract

Required environment variables:

- `DATABASE_URL`: async SQLAlchemy URL, for example
  `postgresql+asyncpg://usage_dashboard:<password>@db:5432/usage_dashboard`.
- `ENCRYPTION_KEY`: stable Fernet key of at least 32 characters. Generate it
  with the command in `.env.example` and back it up securely.

Optional backend variables include `BACKEND_CORS_ORIGINS`, authentication
expiry, polling, retention, and allowed-host settings listed in
[Environment variables](/configuration/environment). The backend image has a
health check at `http://127.0.0.1:8000/health` and needs outbound HTTPS access
to configured providers.

```bash
docker run -d --name backend --network usage-dashboard --restart unless-stopped \
  --env-file backend.env \
  "ghcr.io/skulldorom/usage-dashboard-backend:${IMAGE_TAG}"
```

Store `DATABASE_URL`, `ENCRYPTION_KEY`, and optional backend settings in the
permission-restricted `backend.env` file; do not put secrets directly in the
container command or a platform field that exposes them.

```dotenv
DATABASE_URL=postgresql+asyncpg://usage_dashboard:replace-with-url-safe-password@db:5432/usage_dashboard
ENCRYPTION_KEY=replace-with-generated-fernet-key
BACKEND_CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
```

Restrict the file before starting the container: `chmod 0600 backend.env`.

No backend volume is required. Its entrypoint applies all pending migrations;
if migration fails, Uvicorn does not start. Inspect the logs before starting
the frontend:

```bash
docker logs backend
docker inspect --format '{{.State.Health.Status}}' backend
```

## Frontend contract

The frontend image has a health check at `/health`, which passes only when the
backend route is reachable. Publish container port `80` and ensure `backend`
resolves on the same network:

```bash
docker run -d --name frontend --network usage-dashboard --restart unless-stopped \
  -p 3000:80 \
  "ghcr.io/skulldorom/usage-dashboard-frontend:${IMAGE_TAG}"
```

The only supported runtime frontend variables are the optional
`EXTENSION_TARGET_*_ID` values. They rewrite `/runtime-config.js` at container
startup; they do not change API routing. Terminate TLS in a host proxy or load
balancer in front of port `3000`.

Open `http://localhost:3000` and follow [First-run setup](/getting-started/first-run).

## Upgrade

1. Back up PostgreSQL and the secret containing `ENCRYPTION_KEY`.
2. Pull the same target tag for both images.
3. Stop and remove the frontend, then the backend. Do not remove PostgreSQL or
   its volume.
4. Recreate the backend with the unchanged environment and network identity
   `backend`; wait for migrations and health to succeed.
5. Recreate the frontend, then verify `/health` through its published port.

```bash
IMAGE_TAG=v1.2.0
docker pull "ghcr.io/skulldorom/usage-dashboard-backend:${IMAGE_TAG}"
docker pull "ghcr.io/skulldorom/usage-dashboard-frontend:${IMAGE_TAG}"
docker stop frontend backend
docker rm frontend backend
# Re-run the backend command above with the new tag; wait for healthy.
# Re-run the frontend command above with the matching tag.
curl --fail http://127.0.0.1:3000/health
```

Container platforms should perform the equivalent ordered replacement. Do not
upgrade PostgreSQL across major versions by merely changing its image tag; use
the PostgreSQL-supported major-upgrade or dump/restore procedure.
