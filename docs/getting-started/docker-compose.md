# Docker Compose (recommended)

Docker Compose is the simplest supported production installation. It runs
PostgreSQL, the backend, and the nginx frontend/proxy with persistent database
storage and health-aware startup ordering.

## Requirements

- Git
- Docker Engine with the Compose plugin
- A host or upstream reverse proxy for TLS when exposed beyond a trusted network

## Install

1. Clone the repository and create the environment file:

   ```bash
   git clone https://github.com/Skulldorom/usage-dashboard.git
   cd usage-dashboard
   cp .env.example .env
   openssl rand -base64 32 | tr '+/' '-_'
   ```

2. Put the generated Fernet key in `ENCRYPTION_KEY` and set a strong, URL-safe
   `POSTGRES_PASSWORD`. Leave `DATABASE_URL` blank to let Compose derive it from
   that password; set it only for an external database. Keep `.env` private and
   backed up.

3. Optionally pin `IMAGE_TAG` to a release, then start the stack:

   ```bash
   docker compose pull
   docker compose up -d
   docker compose ps
   docker compose logs backend
   ```

The backend waits for PostgreSQL health, runs `alembic upgrade head`, and then
starts Uvicorn on port `8000`. The frontend waits for backend health, listens on
host port `3000` by default, serves the Vite production build, and proxies
`/api/` and `/health`. PostgreSQL is not published on the host.

Open `http://localhost:3000` and complete [First-run setup](/getting-started/first-run).
Change the host port with `NGINX_HTTP_PORT`.

## Operations

```bash
# Status and logs
docker compose ps
docker compose logs -f backend frontend db

# Restart
docker compose restart backend frontend

# Stop without deleting PostgreSQL data
docker compose down
```

Do not add `--volumes` to `docker compose down` unless you intend to delete the
database. Store TLS termination in a host reverse proxy or load balancer in
front of the published frontend port.

## Backups

Back up `.env` securely and create PostgreSQL dumps regularly:

```bash
docker compose exec -T db pg_dump -U usage_dashboard -d usage_dashboard -Fc > usage-dashboard.dump
```

Test restores separately. A database backup without the original
`ENCRYPTION_KEY` cannot recover encrypted provider credentials.

## Upgrade

1. Back up PostgreSQL and `.env`.
2. If pinned, change `IMAGE_TAG` to the target release.
3. Pull and recreate the application containers:

   ```bash
   docker compose pull
   docker compose up -d
   docker compose ps
   docker compose logs backend
   ```

The recreated backend applies migrations before serving traffic. Keep the
database on its existing PostgreSQL major version unless the PostgreSQL upgrade
is planned separately; changing `POSTGRES_IMAGE` across major versions requires
the PostgreSQL-supported upgrade or dump/restore procedure.
