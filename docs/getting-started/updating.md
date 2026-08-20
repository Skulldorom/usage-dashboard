# Updating

Updates are shipped as new images on GitHub Container Registry.

## Update to the latest release

```bash
docker compose pull
docker compose up -d
```

Compose recreates any containers whose image changed. Database migrations run
automatically when the backend starts.

## Pin a version

By default the stack tracks the `latest` image tag. To pin a specific release,
set `IMAGE_TAG` in `.env`:

```bash
IMAGE_TAG=v1.2.0
```

## Custom image references

If you publish under a different registry or name, override the full image
references instead of the tag:

```bash
BACKEND_IMAGE=ghcr.io/your-org/usage-dashboard-backend:latest
FRONTEND_IMAGE=ghcr.io/your-org/usage-dashboard-frontend:latest
```

See the [environment variable reference](/configuration/environment) for all
image-related settings.
