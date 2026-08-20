# Docker images

To build local images instead of using the GHCR-published ones, run explicit
builds with the Dockerfiles:

```bash
docker build -t usage-dashboard-backend:local -f backend/Dockerfile .
docker build -t usage-dashboard-frontend:local -f frontend/Dockerfile .
BACKEND_IMAGE=usage-dashboard-backend:local FRONTEND_IMAGE=usage-dashboard-frontend:local docker compose up -d
```

## Image layout

- `backend/Dockerfile` - the FastAPI service, multi-stage with a runtime target.
- `frontend/Dockerfile` - builds the Vite app, then serves it with nginx as the
  static frontend **and** API proxy. The nginx entrypoint renders
  `/runtime-config.js` from environment variables (e.g. `EXTENSION_TARGET_*_ID`).

CI builds and publishes both images to
`ghcr.io/skulldorom/usage-dashboard-{backend,frontend}` on merge to `main` and on
version tags.
