# Installation

Usage Dashboard ships as a Docker Compose stack with published images on GitHub
Container Registry. You only need Docker (with the Compose plugin) to get running.

## Quick start

```bash
cp .env.example .env
openssl rand -base64 32 | tr '+/' '-_'
# paste that value into ENCRYPTION_KEY in .env
docker compose pull
docker compose up -d
# open the frontend, copy the one-time setup code from backend logs, and create the admin password
```

## Accessing the stack

Open the frontend container, which also proxies API traffic to the backend:

- **Frontend**: `http://localhost:3000`
- **Backend health**: `http://localhost:3000/health`
- **Homepage payload**: `http://localhost:3000/api/v1/homepage` (requires a login session/scoped bearer token unless `HOMEPAGE_ALLOWED_HOSTS` allows the request host)

Set `NGINX_HTTP_PORT` in `.env` to change the external HTTP port. PostgreSQL is
intentionally internal-only and is not published on the host.

## Images

The default Compose stack pulls published images from GitHub Container Registry.
Set `IMAGE_TAG`, `BACKEND_IMAGE`, or `FRONTEND_IMAGE` to pin or override them.

To build local images instead, see [Docker images](/development/docker-images).
