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

## Published channels

Both `ghcr.io/skulldorom/usage-dashboard-{backend,frontend}` use the same policy:

| Tag | Purpose |
| --- | --- |
| `latest`, `stable` | Recommended stable channel and equivalent alias |
| `main` | Development build from main |
| `sha-<commit>` | Development revision for debugging |
| `v1.0.1` | Immutable exact release |
| `v1.0`, `v1` | Latest stable patch/minor within that series |

Main pushes run deployment tests, then publish only development tags with
`v0.0.0-dev.<full-SHA>` metadata. `release:none` never promotes stable aliases.
The serialized Application release planner reserves a draft and immutable source
commit, tests that commit including PostgreSQL migrations, and builds exact tags.
Retries verify and reuse existing exact tags; mismatches fail rather than overwrite.
Only after both registry images have matching OCI version/revision labels does
promotion copy their verified digests to moving aliases, verify every destination,
and publish the GitHub Release. Promotion never rebuilds either image.

GitHub Releases are the authoritative published stable record. GHCR writes across
repositories are not atomic: aliases can briefly disagree or precede GitHub
publication. Publication failure leaves a reserved draft; resume Application
release to roll forward, never roll back aliases. The shared workflow lock and
checks of published releases, newer reservations, and existing channel metadata
prevent delayed workflows from rolling tags backward. Manual registry writers
must not bypass these controls.

After merging, an authorized maintainer can initialize existing channels using
**Stable channels** on `main`: first dispatch with `confirm=false` (default),
review the dynamically selected newest published stable release and digests,
then dispatch with `confirm=true`. It never rebuilds or alters an exact release.
A newer pending reservation blocks bootstrap; resume Application release instead.
Completed promotion retries verify everything but perform no writes.

Compose keeps `IMAGE_TAG=latest`. Existing installations need no channel edit:
run `docker compose pull` followed by `docker compose up -d` after promotion.
To retain development behavior, explicitly select `IMAGE_TAG=main`. For production
pinning or recovery, select the same published exact version for both images.
Compose never pulls while running; automation requires an explicitly configured
updater. See [updating and recovery](/getting-started/updating#channel-promotion-and-recovery).
